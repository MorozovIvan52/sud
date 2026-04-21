"""
Анти-блокировочная система для парсинга судов РФ (sudrf.ru, ГАС «Правосудие»).
Топ-методы: случайные паузы 7–15 сек, ротация UA, резидентские прокси РФ,
рабочие часы 9:00–18:00 МСК, детект 403/429/капчи, лимит запросов в день.
"""
import asyncio
import json
import logging
import random
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import aiohttp

logger = logging.getLogger(__name__)

# Супер-конфиг для судов РФ
SUPER_ANTI_BLOCK_CONFIG = {
    "delay_range": (7, 15),
    "max_concurrent": 3,
    "max_per_day": 100,
    "working_hours": (9, 18),
    "proxy_rotate_every": 10,
    "ua_rotate_every": 5,
    "session_lifetime": 3600,
    "retry_attempts": 3,
    "retry_delay": (30, 120),
    "block_cooldown_sec": 3600,
}

SUDRF_URL = "https://bsr.sudrf.ru/bigs/common.html"
BLOCK_SIGNS = ["captcha", "блокировка", "защита", "cloudflare", "recaptcha", "checkpoint"]

# 50+ User-Agent (Chrome 123/124, разные ОС)
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

_min_delay, _max_delay = SUPER_ANTI_BLOCK_CONFIG["delay_range"]
_semaphore = asyncio.Semaphore(SUPER_ANTI_BLOCK_CONFIG["max_concurrent"])


async def human_delay(delay_range: Tuple[float, float] = None):
    """Случайная пауза 7–15 сек (естественное поведение)."""
    r = delay_range or SUPER_ANTI_BLOCK_CONFIG["delay_range"]
    await asyncio.sleep(random.uniform(r[0], r[1]))


def is_working_hours() -> bool:
    """Парсинг предпочтительно 9:00–18:00 МСК (по умолчанию локальное время)."""
    start, end = SUPER_ANTI_BLOCK_CONFIG["working_hours"]
    hour = datetime.now().hour
    return start <= hour <= end and datetime.now().weekday() < 5


async def schedule_working_hours():
    """Если не рабочее время — ждём до 1 часа (можно прервать)."""
    if not is_working_hours():
        logger.info("⏰ Нерабочее время. Пауза 60 сек…")
        await asyncio.sleep(60)


def get_anti_detect_headers() -> Dict[str, str]:
    """Полный набор заголовков под Chrome 123 (антидетект)."""
    return {
        "User-Agent": random.choice(UA_POOL),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="123", "Google Chrome";v="123"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "max-age=0",
    }


# Алиас для совместимости с docs/gas_pravosudie_captcha.md
build_headers = get_anti_detect_headers


class RateLimiter:
    """Асинхронный ограничитель частоты запросов (min_interval + jitter). Использовать перед каждым запросом к ГАС."""

    def __init__(self, min_interval: float = 1.5):
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                await asyncio.sleep(self.min_interval - delta + random.uniform(0, 0.5))
            self._last = time.monotonic()


# Глобальный rate limiter для асинхронных вызовов ГАС (опционально)
rate_limiter = RateLimiter(min_interval=2.0)


async def detect_block(resp: aiohttp.ClientResponse) -> Tuple[bool, str]:
    """
    Детект 403/429/капчи. Возвращает (True, "") при блокировке, (False, text) при успехе.
    Тело ответа читается один раз.
    """
    if resp.status in (403, 429):
        logger.warning("🚨 БЛОКИРОВКА HTTP %s. Останавливаем на 1 час.", resp.status)
        try:
            await resp.read()
        except Exception:
            pass
        return True, ""

    text = await resp.text()
    lower = text.lower()
    if any(sign in lower for sign in BLOCK_SIGNS):
        logger.error("🚨 КАПЧА/ЗАЩИТА на странице!")
        return True, text
    return False, text


class ProxyRotator:
    """Простая ротация прокси каждые N запросов."""

    def __init__(self, proxies: List[str], rotate_every: int = 10):
        self.proxies = proxies or []
        self.rotate_every = rotate_every
        self.current = 0
        self.request_count = 0

    def get_next(self) -> Optional[Dict[str, str]]:
        if not self.proxies:
            return None
        self.request_count += 1
        if self.request_count % self.rotate_every == 0:
            self.current = (self.current + 1) % len(self.proxies)
        proxy = self.proxies[self.current]
        return {"http": proxy, "https": proxy}


@dataclass
class Proxy:
    url: str
    region: str
    provider: str
    success_rate: float = 1.0
    requests_count: int = 0
    last_used: float = 0
    is_working: bool = True


class SuperProxyRotator:
    """Ротация прокси для судов РФ: загрузка из JSON, тест, выбор по региону и success_rate."""

    def __init__(self, proxy_file: str = "proxies.json"):
        self.proxy_file = Path(proxy_file)
        self.proxies: List[Proxy] = []
        self.working_proxies: List[Proxy] = []
        self.lock = threading.Lock()
        self.stats = {"total": 0, "success": 0, "failed": 0}
        self.load_proxies()

    def load_proxies(self):
        if self.proxy_file.exists():
            try:
                with open(self.proxy_file, "r", encoding="utf-8") as f:
                    proxy_data = json.load(f)
                    for p in proxy_data:
                        self.proxies.append(
                            Proxy(
                                url=p["url"],
                                region=p.get("region", ""),
                                provider=p.get("provider", ""),
                                success_rate=float(p.get("success_rate", 1.0)),
                                requests_count=int(p.get("requests_count", 0)),
                            )
                        )
            except Exception as e:
                logger.warning("Load proxies failed: %s", e)
                self._demo_proxies()
        else:
            self._demo_proxies()
        self.working_proxies = [p for p in self.proxies if p.is_working]
        if not self.working_proxies:
            self.working_proxies = self.proxies.copy()
        logger.info("Загружено прокси: %s", len(self.proxies))

    def _demo_proxies(self):
        self.proxies = [
            Proxy("http://user:pass@proxy-msk1.ru:8080", "Москва", "МТС"),
            Proxy("http://user:pass@proxy-spb1.ru:3128", "СПб", "Билайн"),
            Proxy("http://user:pass@proxy-ekb1.ru:8080", "ЕКБ", "Ростелеком"),
            Proxy("http://user:pass@proxy-krasnodar.ru:3128", "Краснодар", "Мегафон"),
        ]
        self.save_proxies()

    def save_proxies(self):
        data = [
            {
                "url": p.url,
                "region": p.region,
                "provider": p.provider,
                "success_rate": p.success_rate,
                "requests_count": p.requests_count,
            }
            for p in self.proxies
        ]
        try:
            with open(self.proxy_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Save proxies failed: %s", e)

    async def test_proxy(self, proxy: Proxy, test_url: str = "https://httpbin.org/ip") -> bool:
        timeout = aiohttp.ClientTimeout(total=5)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(test_url, proxy=proxy.url) as resp:
                    if resp.status == 200:
                        proxy.is_working = True
                        return True
        except Exception:
            pass
        proxy.is_working = False
        return False

    async def validate_all_proxies(self):
        logger.info("Тестируем все прокси…")
        for proxy in self.proxies:
            await self.test_proxy(proxy)
        self.working_proxies = [p for p in self.proxies if p.is_working]
        self.save_proxies()
        logger.info("Рабочих прокси: %s/%s", len(self.working_proxies), len(self.proxies))

    def get_best_proxy(self, prefer_region: str = None) -> Optional[Proxy]:
        """Выбирает лучший прокси: по региону, затем по success_rate и нагрузке."""
        with self.lock:
            candidates = list(self.working_proxies) if self.working_proxies else list(self.proxies)
            if not candidates:
                return None
            if prefer_region:
                region_proxies = [p for p in candidates if prefer_region.lower() in (p.region or "").lower()]
                if region_proxies:
                    candidates = region_proxies
            best = min(candidates, key=lambda p: (-p.success_rate, p.requests_count))
            best.requests_count += 1
            best.last_used = time.time()
            return best

    def mark_proxy_failed(self, proxy: Proxy):
        """Отмечает прокси как нерабочий, понижает success_rate."""
        proxy.success_rate = max(0.0, proxy.success_rate * 0.9)
        proxy.is_working = False
        self.working_proxies = [p for p in self.working_proxies if p != proxy]
        if not self.working_proxies:
            self.working_proxies = list(self.proxies)
        logger.warning("Прокси помечен нерабочим: %s", proxy.url[:50])
        self.save_proxies()

    async def get_session_with_proxy(self, prefer_region: str = None) -> Tuple[aiohttp.ClientSession, Proxy]:
        """Возвращает сессию + прокси для парсинга ГАС."""
        proxy = self.get_best_proxy(prefer_region)
        if not proxy:
            raise RuntimeError("Нет рабочих прокси. Добавьте proxies.json или вызовите validate_all_proxies().")
        connector = aiohttp.TCPConnector(limit=1, limit_per_host=1, enable_cleanup_closed=True)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        headers = {
            "User-Agent": random.choice(UA_POOL),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        session = aiohttp.ClientSession(connector=connector, timeout=timeout, headers=headers)
        return session, proxy


async def create_human_session(
    cookie_jar: bool = True,
    timeout_sec: int = 30,
) -> aiohttp.ClientSession:
    """Сессия с человеческими headers и опционально посещением главной."""
    headers = get_anti_detect_headers()
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    jar = aiohttp.CookieJar() if cookie_jar else None
    session = aiohttp.ClientSession(headers=headers, cookie_jar=jar, timeout=timeout)
    try:
        await session.get("https://sudrf.ru")
        await human_delay((2, 5))
    except Exception:
        pass
    return session


async def safe_sudrf_request(
    data: Dict[str, Any],
    proxy_rotator: Optional[SuperProxyRotator] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[str]:
    """
    Один безопасный POST на ГАС: рабочие часы, пауза, антидетект, прокси, детект блокировки.
    Возвращает HTML или None при блокировке.
    """
    await schedule_working_hours()
    await human_delay()

    own_session = session is None
    if session is None:
        session = await create_human_session()

    proxy = None
    if proxy_rotator:
        p = proxy_rotator.get_best_proxy()
        if p:
            proxy = p.url

    headers = get_anti_detect_headers()
    payload = {
        "text": data.get("fio", data.get("text", "")),
        "region": data.get("region", ""),
        "submit": "Найти",
    }

    try:
        async with _semaphore:
            async with session.post(SUDRF_URL, data=payload, headers=headers, proxy=proxy) as resp:
                is_block, text = await detect_block(resp)
                if is_block:
                    logger.warning("Блокировка — пауза 1 час")
                    await asyncio.sleep(SUPER_ANTI_BLOCK_CONFIG["block_cooldown_sec"])
                    return None
                return text
    finally:
        if own_session:
            await session.close()


class AntiBlockSuperParser:
    """Парсер с полной анти-блокировкой: паузы, UA, прокси, рабочие часы, детект блокировок."""

    def __init__(
        self,
        proxy_pool: List[str] = None,
        proxy_file: str = "proxies.json",
        use_super_rotator: bool = False,
    ):
        self.config = SUPER_ANTI_BLOCK_CONFIG
        self.stats = {"requests": 0, "blocks": 0}
        if use_super_rotator:
            self.proxy_rotator = SuperProxyRotator(proxy_file)
            self.proxy_pool = None
        else:
            self.proxy_rotator = None
            self.proxy_pool = proxy_pool or []

    async def safe_sudrf_request(self, data: Dict[str, Any]) -> Optional[str]:
        """Запрос к ГАС с анти-блокировкой."""
        if self.stats["requests"] >= self.config["max_per_day"]:
            logger.warning("Достигнут лимит запросов в день (%s)", self.config["max_per_day"])
            return None
        result = await safe_sudrf_request(
            data,
            proxy_rotator=self.proxy_rotator,
        )
        self.stats["requests"] += 1
        if result is None:
            self.stats["blocks"] += 1
        return result


class SudrfProxyParser:
    """Парсер ГАС Правосудие с ротацией прокси и авто-failover."""

    def __init__(self, proxy_file: str = "proxies.json"):
        self.rotator = SuperProxyRotator(proxy_file)

    async def parse_court(self, fio: str, region: str = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Парсит суд по ФИО через прокси. Возвращает (html, region_used) или (None, None).
        """
        try:
            session, proxy = await self.rotator.get_session_with_proxy(region)
        except RuntimeError as e:
            logger.error("%s", e)
            self.rotator.stats["failed"] += 1
            return None, None

        try:
            payload = {"text": fio, "region": region or "", "submit": "Найти"}
            async with session.post(SUDRF_URL, data=payload, proxy=proxy.url) as resp:
                text = await resp.text()
                if resp.status == 200 and not any(s in text.lower() for s in BLOCK_SIGNS):
                    self.rotator.stats["success"] += 1
                    return text, proxy.region
                logger.error("HTTP %s или блокировка через %s", resp.status, proxy.url[:40])
        except Exception as e:
            logger.exception("Ошибка прокси %s: %s", proxy.url[:40], e)
            self.rotator.mark_proxy_failed(proxy)
        finally:
            await session.close()

        self.rotator.stats["failed"] += 1
        return None, None


async def test_rotator(proxy_file: str = "proxies.json", num_requests: int = 20):
    """Тест ротации: валидация прокси и серия запросов к ГАС."""
    rotator = SuperProxyRotator(proxy_file)
    await rotator.validate_all_proxies()

    parser = SudrfProxyParser(proxy_file)
    for i in range(num_requests):
        result, region = await parser.parse_court("Иванов И.И.", "Москва")
        if result:
            logger.info("Запрос %s: регион %s, длина %s", i + 1, region, len(result))
        else:
            logger.warning("Запрос %s: неудача", i + 1)
        await human_delay((3, 7))
    logger.info("Итого: success=%s, failed=%s", rotator.stats.get("success", 0), rotator.stats.get("failed", 0))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_rotator())
