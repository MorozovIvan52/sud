# kad_arbitr_compliance.py — соблюдение правил использования kad.arbitr.ru:
# robots.txt, rate limit, User-Agent, прокси, капча, юридические ограничения.

import asyncio
import os
import random
import time
from typing import Optional, Tuple

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

KAD_ARBITR_BASE = "https://kad.arbitr.ru"
KAD_ARBITR_ROBOTS_URL = "https://kad.arbitr.ru/robots.txt"

# Рекомендуемые задержки между запросами (сек) — соблюдение rate limit
DEFAULT_DELAY_MIN = 2.0
DEFAULT_DELAY_MAX = 5.0
# При 429/503 — пауза по умолчанию (сек)
RATE_LIMIT_BACKOFF = 60

# Признаки капчи в HTML
CAPTCHA_SIGNS = [
    "captcha",
    "recaptcha",
    "reCAPTCHA",
    "подтвердите, что вы не робот",
    "человек",
    "cloudflare",
    "checkpoint",
    "blocked",
    "доступ ограничен",
]

# Юридическая оговорка и ссылки
LEGAL_DISCLAIMER = (
    "Использование данных с kad.arbitr.ru должно соответствовать правилам сервиса и законодательству РФ. "
    "При массовом парсинге рекомендуется использовать официальные API и механизмы, предоставляемые сервисом. "
    "Данные носят справочный характер."
)
OFFICIAL_DOCS_URL = "https://kad.arbitr.ru/"
TERMS_URL = "https://kad.arbitr.ru/"


def get_user_agent() -> str:
    """User-Agent из переменной окружения или корректный браузерный по умолчанию."""
    ua = os.getenv("KAD_ARBITR_USER_AGENT", "").strip()
    if ua:
        return ua
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
        "(ParserSud; +https://parsrsud.ru; compliance)"
    )


def get_proxy() -> Optional[str]:
    """URL прокси из окружения для массового парсинга (например http://user:pass@host:port)."""
    return os.getenv("KAD_ARBITR_PROXY", "").strip() or None


def get_delay_range() -> Tuple[float, float]:
    """Минимальная и максимальная задержка между запросами (сек) из env или по умолчанию."""
    min_d = os.getenv("KAD_ARBITR_DELAY_MIN", "")
    max_d = os.getenv("KAD_ARBITR_DELAY_MAX", "")
    try:
        mi = float(min_d) if min_d else DEFAULT_DELAY_MIN
        ma = float(max_d) if max_d else DEFAULT_DELAY_MAX
        if mi <= ma:
            return (mi, ma)
    except ValueError:
        pass
    return (DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)


def detect_captcha(html: str) -> bool:
    """Проверка, что в ответе вероятно страница с капчей."""
    if not html or not isinstance(html, str):
        return False
    lower = html.lower()
    return any(sign in lower for sign in CAPTCHA_SIGNS)


async def fetch_robots_txt(session) -> Optional[str]:
    """Загрузить robots.txt (session — aiohttp ClientSession)."""
    try:
        async with session.get(
            KAD_ARBITR_ROBOTS_URL,
            timeout=10,
        ) as resp:
            if resp.status == 200:
                return await resp.text()
    except Exception as e:
        logger.debug("robots.txt fetch failed: %s", e)
    return None


def robots_allows_path(robots_content: Optional[str], path: str = "/") -> bool:
    """
    Упрощённая проверка: разрешён ли путь для User-Agent *.
    Не парсит Crawl-delay (нестандарт); только Disallow.
    """
    if not robots_content:
        return True
    path = path.rstrip("/") or "/"
    lines = robots_content.lower().splitlines()
    disallowed = []
    in_star = False
    for line in lines:
        line = line.strip()
        if line.startswith("user-agent:"):
            ua = line.split(":", 1)[1].strip()
            in_star = ua == "*"
            continue
        if in_star and line.startswith("disallow:"):
            rule = line.split(":", 1)[1].strip()
            if rule:
                disallowed.append(rule)
    for rule in disallowed:
        if path == rule or path.startswith(rule.rstrip("/") + "/") or path.startswith(rule):
            return False
    return True


class RateLimiter:
    """Асинхронный ограничитель частоты запросов: минимальный интервал между acquire()."""

    def __init__(self, min_interval: float = DEFAULT_DELAY_MIN, max_interval: float = DEFAULT_DELAY_MAX):
        self._min = min_interval
        self._max = max_interval
        self._last_acquire = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            since_last = now - self._last_acquire
            delay = random.uniform(self._min, self._max)
            wait = max(0, delay - since_last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_acquire = time.monotonic()


# Глобальный лимитер для kad_arbitr (можно переопределить)
_global_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    global _global_rate_limiter
    if _global_rate_limiter is None:
        r = get_delay_range()
        _global_rate_limiter = RateLimiter(min_interval=r[0], max_interval=r[1])
    return _global_rate_limiter
