"""
Превенция и обход капчи при парсинге сайтов судов РФ (sudrf.ru, ГАС «Правосудие»).

Рекомендация: использовать легальные API (DaData) и открытые данные.
При необходимости резервного парсинга — паузы 12–20 сек, человеческие headers, резидентские прокси.
Для полной анти-блокировочной системы (рабочие часы, прокси-ротация, лимит в день) см. anti_block.py.
"""

import asyncio
import logging
import random
import time
from typing import List, Optional, Callable, Any

import aiohttp

logger = logging.getLogger(__name__)

# Паузы в секундах (имитация человека)
MIN_DELAY = 12
MAX_DELAY = 20

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

CAPTCHA_SIGNS = [
    "captcha", "recaptcha", "hcaptcha", "cf-browser",
    "cloudflare", "защита", "проверка", "бот",
    "js-challenge", "checkpoint", "captcha-form",
]


def human_headers() -> dict:
    """Headers как у Chrome 123+ (снижает вероятность капчи)."""
    return {
        "User-Agent": random.choice(UA_POOL),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Google Chrome";v="123", "Not:A-Brand";v="8"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


def detect_captcha(html: str) -> bool:
    """Детект капчи/защиты на странице (sudrf.ru и аналоги)."""
    if not html:
        return False
    lower = html.lower()
    return any(sign in lower for sign in CAPTCHA_SIGNS)


class AntiCaptchaParser:
    """
    Имитация человека: случайные паузы 12–20 сек, ротация User-Agent.
    Рекомендуется для резервного парсинга ГАС «Правосудие».
    """

    def __init__(
        self,
        min_delay: float = MIN_DELAY,
        max_delay: float = MAX_DELAY,
        proxy_pool: Optional[List[str]] = None,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.proxy_pool = proxy_pool or []
        self._proxy_index = 0

    def _next_proxy(self) -> Optional[str]:
        if not self.proxy_pool:
            return None
        p = self.proxy_pool[self._proxy_index % len(self.proxy_pool)]
        self._proxy_index += 1
        return p

    async def human_delay(self):
        """Случайная пауза перед запросом."""
        delay = random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(delay)

    async def human_like_get(
        self,
        session: aiohttp.ClientSession,
        url: str,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """GET с человеческими паузами и headers."""
        await self.human_delay()
        headers = kwargs.pop("headers", {})
        headers = {**human_headers(), **headers}
        proxy = kwargs.pop("proxy", None) or self._next_proxy()
        return await session.get(url, headers=headers, proxy=proxy, **kwargs)

    async def human_like_post(
        self,
        session: aiohttp.ClientSession,
        url: str,
        data: Optional[dict] = None,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """POST с человеческими паузами и headers."""
        await self.human_delay()
        headers = kwargs.pop("headers", {})
        headers = {**human_headers(), **headers}
        proxy = kwargs.pop("proxy", None) or self._next_proxy()
        return await session.post(url, data=data, headers=headers, proxy=proxy, **kwargs)


async def captcha_bypass_strategy(
    html: str,
    session: aiohttp.ClientSession,
    url: str,
) -> Optional[str]:
    """
    Стратегия обхода: при признаках Cloudflare — пауза и повтор с Sec-Ch-Ua.
    При ReCaptcha возвращаем None (рекомендуется 2captcha или отказ от парсинга).
    """
    if "cloudflare" in html.lower():
        await asyncio.sleep(10)
        headers = human_headers()
        headers["Sec-Ch-Ua"] = '"Google Chrome";v="123"'
        try:
            async with session.get(url, headers=headers) as resp:
                return await resp.text()
        except Exception as e:
            logger.warning("Cloudflare retry failed: %s", e)
            return None
    if "recaptcha" in html.lower() or "hcaptcha" in html.lower():
        logger.warning("ReCaptcha/HCaptcha — используйте 2captcha или DaData/открытые данные.")
        return None
    return html


class MassSudrfParser:
    """
    Пакетный парсинг с анти-капчей: паузы 12–20 сек, ротация прокси,
    детект капчи и пропуск при её появлении.
    """

    def __init__(
        self,
        parser: Optional[AntiCaptchaParser] = None,
        parse_court_data: Optional[Callable[[str], Any]] = None,
    ):
        self.parser = parser or AntiCaptchaParser()
        self.parse_court_data = parse_court_data or (lambda html: {"raw": html[:500]})

    async def parse_batch(
        self,
        fio_list: List[str],
        sudrf_url: str,
        build_payload: Optional[Callable[[str], dict]] = None,
    ) -> List[Any]:
        """Пакетный запрос по списку ФИО с паузами и детектом капчи."""
        results = []
        timeout = aiohttp.ClientTimeout(total=30)

        def default_payload(fio: str) -> dict:
            return {"is_utf8": "1", "court_type": "ms", "fio": fio}

        build = build_payload or default_payload

        async with aiohttp.ClientSession(timeout=timeout) as session:
            for i, fio in enumerate(fio_list):
                try:
                    html = None
                    async with self.parser.human_like_post(
                        session, sudrf_url, data=build(fio)
                    ) as resp:
                        html = await resp.text()

                    if detect_captcha(html):
                        logger.warning("Капча на запросе %s: %s", i + 1, fio[:30])
                        results.append(None)
                        continue

                    results.append(self.parse_court_data(html))
                except Exception as e:
                    logger.exception("Ошибка парсинга для %s: %s", fio[:30], e)
                    results.append(None)

        return results


class CaptchaSolver:
    """
    Решение ReCaptcha v2/v3 через 2captcha.com.
    Использовать только при необходимости; предпочтительно DaData + локальная БД.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.submit_url = "https://2captcha.com/in.php"
        self.result_url = "https://2captcha.com/res.php"

    def solve_recaptcha_v2(
        self,
        site_key: str,
        page_url: str,
        max_wait_sec: int = 120,
        poll_interval: int = 5,
    ) -> Optional[str]:
        """ReCaptcha v2: отправка капчи и ожидание токена."""
        import requests as req

        data = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
        }
        try:
            r = req.post(self.submit_url, data=data, timeout=10)
            r.raise_for_status()
            if "OK|" not in r.text:
                logger.warning("2captcha submit: %s", r.text)
                return None
            captcha_id = r.text.split("|", 1)[1].strip()
        except Exception as e:
            logger.exception("2captcha submit error: %s", e)
            return None

        for _ in range(max_wait_sec // poll_interval):
            time.sleep(poll_interval)
            try:
                res = req.get(
                    self.result_url,
                    params={"key": self.api_key, "action": "get", "id": captcha_id},
                    timeout=10,
                )
                text = res.text.strip()
                if "CAPCHA_NOT_READY" in text:
                    continue
                if "OK|" in text:
                    return text.split("|", 1)[-1].strip()
                logger.warning("2captcha result: %s", text)
                return None
            except Exception as e:
                logger.warning("2captcha poll: %s", e)
        return None
