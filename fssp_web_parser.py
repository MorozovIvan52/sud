"""
Парсинг открытых данных ФССП через веб-интерфейс fssp.gov.ru/iss/ip/.

Соответствие: лимиты и вежливый парсинг — parser/parsing_compliance.py;
юридические требования — docs/parsing_compliance_gost.md, docs/fssp_parsing_open_data.md.
Лимиты: не более 10–20 запросов в минуту, паузы 3–10 сек между запросами.
"""
import csv
import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Соответствие ГОСТ/вежливый парсинг: идентифицируемый User-Agent, лимиты, аудит
try:
    from parsing_compliance import (
        get_identifiable_headers as _compliance_headers,
        rate_limit_wait,
        get_polite_delay,
        audit_log as _audit_log,
        check_robots_txt_allowed,
        MAX_REQUESTS_PER_MINUTE as _COMPLIANCE_MAX_RPM,
    )
    HAS_COMPLIANCE = True
except ImportError:
    HAS_COMPLIANCE = False
    _COMPLIANCE_MAX_RPM = 10

# Опционально: ротация User-Agent (pip install fake_useragent) — для совместимости
try:
    from fake_useragent import UserAgent
    HAS_FAKE_USERAGENT = True
except ImportError:
    HAS_FAKE_USERAGENT = False

FSSP_WEB_BASE_URL = os.getenv("FSSP_WEB_BASE_URL", "https://fssp.gov.ru/iss/ip/")
FSSP_WEB_DELAY_MIN = float(os.getenv("FSSP_WEB_DELAY_MIN", "3"))
FSSP_WEB_DELAY_MAX = float(os.getenv("FSSP_WEB_DELAY_MAX", "10"))
FSSP_WEB_TIMEOUT = int(os.getenv("FSSP_WEB_TIMEOUT", "30"))
FSSP_WEB_MAX_REQUESTS_PER_MINUTE = int(os.getenv("FSSP_WEB_MAX_REQUESTS_PER_MINUTE", "15"))
# По умолчанию — идентифицируемый User-Agent (соответствие рекомендациям); 0 — маскировка под браузер
FSSP_WEB_USE_IDENTIFIABLE_UA = os.getenv("FSSP_WEB_USE_IDENTIFIABLE_UA", "1").strip().lower() in ("1", "true", "yes")

DEFAULT_FIELDNAMES = ("number", "date", "department", "debtor", "amount")


class FSSPWebParser:
    """
    Парсер веб-интерфейса банка данных исполнительных производств ФССП.
    Соблюдает лимиты из документации: задержки, ротация User-Agent.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        delay_min: Optional[float] = None,
        delay_max: Optional[float] = None,
    ):
        self.base_url = (base_url or FSSP_WEB_BASE_URL).rstrip("/") + "/"
        self.timeout = timeout if timeout is not None else FSSP_WEB_TIMEOUT
        self.delay_min = delay_min if delay_min is not None else FSSP_WEB_DELAY_MIN
        self.delay_max = delay_max if delay_max is not None else FSSP_WEB_DELAY_MAX
        self.session = requests.Session()
        self._ua = None
        self._robots_checked: Optional[bool] = None  # True — разрешено, False — запрещено
        self.max_rpm = (
            min(FSSP_WEB_MAX_REQUESTS_PER_MINUTE, _COMPLIANCE_MAX_RPM)
            if HAS_COMPLIANCE
            else FSSP_WEB_MAX_REQUESTS_PER_MINUTE
        )
        if HAS_FAKE_USERAGENT:
            try:
                self._ua = UserAgent()
            except Exception as e:
                logger.debug("fake_useragent недоступен: %s", e)

    def _get_headers(self) -> Dict[str, str]:
        if FSSP_WEB_USE_IDENTIFIABLE_UA and HAS_COMPLIANCE:
            return _compliance_headers()
        if self._ua and not FSSP_WEB_USE_IDENTIFIABLE_UA:
            try:
                ua = self._ua.random
            except Exception:
                ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        else:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    def _check_robots_once(self) -> bool:
        """Один раз за сессию проверить robots.txt; при запрете не делать запрос."""
        if not HAS_COMPLIANCE:
            return True
        if self._robots_checked is not None:
            return self._robots_checked
        allowed = check_robots_txt_allowed(self.base_url, "/iss/ip/")
        if allowed is False:
            logger.warning("FSSP robots.txt запрещает парсинг %s", self.base_url)
            self._robots_checked = False
            return False
        self._robots_checked = True
        return True

    def _check_allowed(self) -> bool:
        """Проверка robots.txt перед запросами (обёртка над _check_robots_once)."""
        if HAS_COMPLIANCE:
            return self._check_robots_once()
        return True

    def search_by_fio(
        self,
        last_name: str,
        first_name: str,
        middle_name: Optional[str] = None,
        *,
        add_delay_after: bool = True,
        check_robots: bool = True,
    ) -> List[Dict[str, Any]]:
        """Поиск по ФИО физического лица. Возвращает список записей (number, date, department, debtor, amount)."""
        fio = f"{last_name} {first_name} {middle_name or ''}".strip()
        payload = {"isFiz": "true", "fio": fio}
        if check_robots and not self._check_allowed():
            return []
        if HAS_COMPLIANCE:
            rate_limit_wait(requests_per_minute=self.max_rpm)
        t0 = time.time()
        try:
            response = self.session.post(
                self.base_url,
                data=payload,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            duration = time.time() - t0
            if HAS_COMPLIANCE:
                _audit_log(
                    "search_fssp_web",
                    "fssp_web",
                    response.status_code == 200,
                    {"status_code": response.status_code, "duration_sec": round(duration, 2)},
                )
            if response.status_code == 429:
                time.sleep(get_polite_delay() * 2)
                return []
            response.raise_for_status()
            results = self._parse_results(response.text)
            if HAS_COMPLIANCE:
                _audit_log(
                    "search_fssp_web",
                    "fssp_web",
                    True,
                    {"query_type": "fio", "records": len(results), "duration_sec": round(time.time() - t0, 2)},
                )
            if add_delay_after:
                self.add_delay()
            return results
        except requests.exceptions.RequestException as e:
            duration = time.time() - t0
            if HAS_COMPLIANCE:
                _audit_log("search_fssp_web", "fssp_web", False, {"error_type": type(e).__name__, "duration_sec": round(duration, 2)})
            logger.warning("FSSP веб-поиск: %s", e)
            return []

    def _parse_results(self, html: str) -> List[Dict[str, Any]]:
        """Парсинг таблицы результатов (подстройте под актуальную вёрстку сайта)."""
        soup = BeautifulSoup(html, "html.parser")
        results: List[Dict[str, Any]] = []
        table = soup.find("table", {"class": "results-table"})
        if not table:
            # Альтернативные варианты селекторов при изменении сайта
            table = soup.find("table", class_=lambda c: c and "result" in (c or ""))
        if table:
            rows = table.find_all("tr")[1:]
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 5:
                    results.append({
                        "number": cells[0].get_text(strip=True),
                        "date": cells[1].get_text(strip=True),
                        "department": cells[2].get_text(strip=True),
                        "debtor": cells[3].get_text(strip=True),
                        "amount": cells[4].get_text(strip=True),
                    })
        return results

    def add_delay(self) -> None:
        """Случайная задержка между запросами (по умолчанию 3–10 сек, по ГОСТ/рекомендациям)."""
        if HAS_COMPLIANCE:
            delay = get_polite_delay()
        else:
            delay = random.uniform(self.delay_min, self.delay_max)
        time.sleep(delay)

    def save_to_csv(
        self,
        results: List[Dict[str, Any]],
        path: Path | str,
        fieldnames: Optional[List[str]] = None,
    ) -> None:
        """Сохранение результатов в CSV (инструкция из docs/fssp_parsing_open_data.md)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        names = fieldnames or list(DEFAULT_FIELDNAMES)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=names, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)
        logger.info("FSSP веб: сохранено %s записей в %s", len(results), path)


def search_fssp_by_fio(
    last_name: str,
    first_name: str,
    middle_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Удобная функция: поиск по ФИО через веб-интерфейс ФССП с задержкой."""
    parser = FSSPWebParser()
    return parser.search_by_fio(last_name, first_name, middle_name)
