# kad_arbitr_parser.py — парсер КАД Арбитраж (kad.arbitr.ru): поиск по ИНН.
# Улучшения: retry, dataclasses, парсинг HTML, батч с семафором.
# Соблюдение: robots.txt, rate limit, User-Agent, прокси, капча (см. kad_arbitr_compliance).

import asyncio
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    import aiohttp
    from aiohttp import ClientError
    from aiohttp.client_exceptions import ClientConnectionError, ServerDisconnectedError
except ImportError:
    aiohttp = None
    ClientError = Exception
    ClientConnectionError = Exception
    ServerDisconnectedError = Exception

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from kad_arbitr_compliance import (
        get_user_agent,
        get_proxy,
        get_rate_limiter,
        detect_captcha as compliance_detect_captcha,
        fetch_robots_txt,
        robots_allows_path,
        LEGAL_DISCLAIMER,
        RATE_LIMIT_BACKOFF,
    )
    _COMPLIANCE = True
except ImportError:
    _COMPLIANCE = False
    get_user_agent = lambda: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    get_proxy = lambda: None
    get_rate_limiter = None
    compliance_detect_captcha = None
    fetch_robots_txt = None
    robots_allows_path = None
    LEGAL_DISCLAIMER = ""
    RATE_LIMIT_BACKOFF = 60

KAD_ARBITR_SEARCH_URL = "https://kad.arbitr.ru/"
KAD_ARBITR_API_SEARCH = "https://kad.arbitr.ru/api/search"
MAX_RETRIES = 3
REQUEST_TIMEOUT = 20


def _headers() -> Dict[str, str]:
    return {
        "User-Agent": get_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Referer": KAD_ARBITR_SEARCH_URL,
    }


HEADERS = _headers()


@dataclass
class ArbitrCase:
    """Одно дело из КАД Арбитраж."""
    case_number: str
    case_type: str
    court: str
    status: str
    amount: float
    date: str
    link: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArbitrResult:
    """Результат поиска по ИНН в КАД Арбитраж."""
    inn: str
    cases: List[ArbitrCase]
    cases_count: int
    total_debt: float
    error: Optional[str] = None
    raw_preview: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["cases"] = [c.to_dict() if isinstance(c, ArbitrCase) else c for c in self.cases]
        return d


def _normalize_inn(inn: str) -> str:
    return (inn or "").strip().replace(" ", "").replace("-", "")


def _parse_amount(text: str) -> float:
    """Извлечь число из строки вида '1 234 567,89 ₽' или '1234567'."""
    if not text:
        return 0.0
    cleaned = re.sub(r"[^\d,.\s]", "", text).replace(" ", "").replace(",", ".")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


async def fetch_with_retries(
    session: "aiohttp.ClientSession",
    url: str,
    params: Optional[Dict[str, Any]] = None,
    retries: int = MAX_RETRIES,
) -> Optional[str]:
    """Загрузка страницы с повторными попытками, соблюдением rate limit и обработкой 429/капчи."""
    if not session:
        return None
    params = params or {}
    proxy = get_proxy() if _COMPLIANCE else None
    for attempt in range(retries):
        try:
            if _COMPLIANCE and get_rate_limiter:
                await get_rate_limiter().acquire()
            async with session.get(
                url,
                params=params,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                proxy=proxy,
            ) as response:
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After", str(RATE_LIMIT_BACKOFF))
                    try:
                        wait = int(retry_after)
                    except ValueError:
                        wait = RATE_LIMIT_BACKOFF
                    logger.warning("kad_arbitr rate limit 429, ждём %s сек", wait)
                    await asyncio.sleep(wait)
                    continue
                if response.status >= 500:
                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** (attempt + 1))
                        continue
                    return None
                response.raise_for_status()
                text = await response.text()
                if _COMPLIANCE and compliance_detect_captcha and compliance_detect_captcha(text):
                    logger.warning("kad_arbitr: в ответе обнаружена капча")
                    return None
                return text
        except (ClientError, asyncio.TimeoutError, ClientConnectionError, ServerDisconnectedError) as e:
            if attempt < retries - 1:
                delay = 2 ** (attempt + 1)
                logger.warning("kad_arbitr retry %s/%s %s: %s", attempt + 1, retries, url, e)
                await asyncio.sleep(delay)
            else:
                logger.error("kad_arbitr failed %s: %s", url, e)
                return None
    return None


def _parse_cases_from_html(html: str, inn: str) -> List[ArbitrCase]:
    """
    Извлечь дела из HTML страницы КАД Арбитраж.
    Сайт может отдавать SPA-оболочку; парсим таблицы и типовые блоки.
    """
    cases: List[ArbitrCase] = []
    if not BeautifulSoup or not html:
        return cases

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return cases

    # Вариант 1: таблица с делами (типовые классы kad.arbitr)
    for table in soup.select("table.b-search-result, table.search-result, table[class*='search'], table[class*='case']"):
        for row in table.select("tr"):
            cells = row.select("td")
            if len(cells) < 4:
                continue
            link_el = row.select_one("a[href*='/Documents/'], a[href*='caseNumber']")
            link = link_el.get("href", "") if link_el else ""
            if link and not link.startswith("http"):
                link = "https://kad.arbitr.ru" + link if link.startswith("/") else KAD_ARBITR_SEARCH_URL + link
            texts = [c.get_text(strip=True) for c in cells]
            case_num = texts[0] if texts else ""
            if not case_num or len(case_num) < 5:
                continue
            amount = 0.0
            for t in texts:
                a = _parse_amount(t)
                if a > 0:
                    amount = a
                    break
            cases.append(
                ArbitrCase(
                    case_number=case_num,
                    case_type=texts[1] if len(texts) > 1 else "",
                    court=texts[2] if len(texts) > 2 else "",
                    status=texts[3] if len(texts) > 3 else "",
                    amount=amount,
                    date=texts[4] if len(texts) > 4 else "",
                    link=link,
                )
            )
            if len(cases) >= 100:
                return cases

    # Вариант 2: блоки .b-search-result-item или похожие
    for block in soup.select(".b-search-result-item, .search-result-item, [class*='searchResultItem'], [data-case-number]"):
        num_el = block.select_one("[data-case-number], .case-number, .number, a[href*='/Documents/']")
        case_number = ""
        link = ""
        if num_el:
            case_number = num_el.get("data-case-number", "") or num_el.get_text(strip=True)
            if num_el.name == "a":
                link = num_el.get("href", "")
        if not case_number and num_el:
            case_number = num_el.get_text(strip=True)
        if link and not link.startswith("http"):
            link = "https://kad.arbitr.ru" + link if link.startswith("/") else KAD_ARBITR_SEARCH_URL + link

        court_el = block.select_one(".court-name, .court, [class*='court']")
        court = court_el.get_text(strip=True) if court_el else ""
        status_el = block.select_one(".status, .case-status, [class*='status']")
        status = status_el.get_text(strip=True) if status_el else ""
        amount_el = block.select_one(".amount, .sum, [class*='amount'], [class*='sum']")
        amount = _parse_amount(amount_el.get_text(strip=True)) if amount_el else 0.0
        date_el = block.select_one(".date, [class*='date']")
        date_str = date_el.get_text(strip=True) if date_el else ""

        if case_number:
            cases.append(
                ArbitrCase(
                    case_number=case_number[:200],
                    case_type="",
                    court=court[:500],
                    status=status[:200],
                    amount=amount,
                    date=date_str[:50],
                    link=link,
                )
            )
        if len(cases) >= 100:
            return cases

    # Вариант 3: ссылки на дела в тексте
    for a in soup.select('a[href*="/Documents/"]'):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if text and len(text) >= 10 and not any(c.case_number == text for c in cases):
            full_link = "https://kad.arbitr.ru" + href if href.startswith("/") else href
            cases.append(
                ArbitrCase(
                    case_number=text[:200],
                    case_type="",
                    court="",
                    status="",
                    amount=0.0,
                    date="",
                    link=full_link,
                )
            )
        if len(cases) >= 100:
            return cases

    return cases


async def parse_arbitr_inn(inn: str, session: Optional["aiohttp.ClientSession"] = None) -> ArbitrResult:
    """
    Поиск дел по ИНН в КАД Арбитраж (kad.arbitr.ru).
    Возвращает ArbitrResult с полем cases (список ArbitrCase) и total_debt.
    session — опционально; при массовом парсинге передайте одну сессию для переиспользования.
    """
    inn = _normalize_inn(inn)
    if not inn or len(inn) not in (10, 12):
        return ArbitrResult(
            inn=inn,
            cases=[],
            cases_count=0,
            total_debt=0.0,
            error="Некорректный ИНН (ожидается 10 или 12 цифр)",
        )

    if not aiohttp:
        return ArbitrResult(
            inn=inn,
            cases=[],
            cases_count=0,
            total_debt=0.0,
            error="aiohttp не установлен",
        )

    own_session = None
    if session is None:
        session = aiohttp.ClientSession()
        own_session = session

    try:
        html = await fetch_with_retries(
            session,
            KAD_ARBITR_SEARCH_URL,
            params={"query": inn},
            retries=MAX_RETRIES,
        )

        if not html:
            return ArbitrResult(
                inn=inn,
                cases=[],
                cases_count=0,
                total_debt=0.0,
                error="Ошибка загрузки страницы",
                raw_preview="",
            )

        cases = _parse_cases_from_html(html, inn)
        total_debt = sum(c.amount for c in cases)

        return ArbitrResult(
            inn=inn,
            cases=cases,
            cases_count=len(cases),
            total_debt=round(total_debt, 2),
            raw_preview=html[:500] if html else None,
        )
    finally:
        if own_session:
            await own_session.close()


async def parse_arbitr_inn_dict(inn: str) -> Dict[str, Any]:
    """То же, что parse_arbitr_inn, но возвращает dict (обратная совместимость)."""
    result = await parse_arbitr_inn(inn)
    return result.to_dict()


async def parse_arbitr_inn_batch(
    inn_list: List[str],
    concurrency: int = 10,
    return_dicts: bool = True,
    check_robots: bool = True,
) -> List[Any]:
    """
    Батч-поиск по списку ИНН.
    return_dicts=True — список dict (как раньше), False — список ArbitrResult.
    check_robots — при True и наличии kad_arbitr_compliance проверяется robots.txt перед первым запросом.
    Используется одна сессия на весь батч (сохранение сессии браузера).
    """
    if _COMPLIANCE and check_robots and fetch_robots_txt and robots_allows_path and aiohttp:
        async with aiohttp.ClientSession() as check_session:
            robots = await fetch_robots_txt(check_session)
            if not robots_allows_path(robots, "/"):
                logger.warning("kad_arbitr: robots.txt не разрешает доступ к /")
                return [
                    (ArbitrResult(inn=_normalize_inn(i), cases=[], cases_count=0, total_debt=0.0, error="robots.txt запрещает доступ").to_dict() if return_dicts else ArbitrResult(inn=_normalize_inn(i), cases=[], cases_count=0, total_debt=0.0, error="robots.txt запрещает доступ"))
                    for i in inn_list
                ]

    semaphore = asyncio.Semaphore(concurrency)

    async def one(inn: str, sess: "aiohttp.ClientSession"):
        async with semaphore:
            return await parse_arbitr_inn(inn, session=sess)

    if not aiohttp:
        err_result = ArbitrResult(inn="", cases=[], cases_count=0, total_debt=0.0, error="aiohttp не установлен")
        return [err_result.to_dict() if return_dicts else err_result for _ in inn_list]

    results = []
    async with aiohttp.ClientSession() as session:
        tasks = [one(_normalize_inn(i), session) for i in inn_list]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(gathered):
            inn = inn_list[i] if i < len(inn_list) else ""
            if isinstance(r, Exception):
                err_result = ArbitrResult(
                    inn=_normalize_inn(inn),
                    cases=[],
                    cases_count=0,
                    total_debt=0.0,
                    error=str(r),
                )
                results.append(err_result.to_dict() if return_dicts else err_result)
            else:
                results.append(r.to_dict() if return_dicts else r)
    return results
