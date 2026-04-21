# -*- coding: utf-8 -*-
"""
Соответствие парсинга требованиям ГОСТ и законодательства РФ.

Используется в парсерах (ФССП веб, ГАС и др.) для:
- вежливого парсинга (лимиты, идентифицируемый User-Agent);
- минимизации рисков по ФЗ‑152 (персональные данные);
- учёта robots.txt и пользовательского соглашения.

См. docs/parsing_compliance_gost.md — что сделано и что ещё нужно.
"""

import logging
import os
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# --- Лимиты по рекомендациям (документация ФССП, вежливый парсинг) ---
MAX_REQUESTS_PER_MINUTE = int(os.getenv("PARSING_MAX_REQUESTS_PER_MINUTE", "10"))
DELAY_MIN_SEC = float(os.getenv("PARSING_DELAY_MIN", "3"))
DELAY_MAX_SEC = float(os.getenv("PARSING_DELAY_MAX", "10"))

# Идентифицируемый User-Agent (ГОСТ/лучшие практики: чтобы владелец сайта мог связаться)
# Не маскируемся под браузер — указываем название и контакт
PARSER_BOT_NAME = os.getenv("PARSER_BOT_NAME", "ParserSudPro-ComplianceBot")
PARSER_BOT_CONTACT = os.getenv("PARSER_BOT_CONTACT", "")  # например URL или email
USER_AGENT_IDENTIFIABLE = (
    f"{PARSER_BOT_NAME}/1.0 (+https://github.com/...; compliance)"
    if not PARSER_BOT_CONTACT
    else f"{PARSER_BOT_NAME}/1.0 (contact: {PARSER_BOT_CONTACT})"
)

# Храним время последних запросов для лимита (глобально по процессу)
_request_times: list = []
_request_times_lock = None

def _get_lock():
    global _request_times_lock
    if _request_times_lock is None:
        import threading
        _request_times_lock = threading.Lock()
    return _request_times_lock


def rate_limit_wait(requests_per_minute: Optional[int] = None) -> None:
    """
    Ждать при необходимости, чтобы не превысить лимит запросов в минуту.
    Соответствует рекомендациям: не более 10–20 запросов в минуту.
    """
    limit = requests_per_minute if requests_per_minute is not None else MAX_REQUESTS_PER_MINUTE
    if limit <= 0:
        return
    now = time.time()
    with _get_lock():
        global _request_times
        _request_times = [t for t in _request_times if now - t < 60]
        if len(_request_times) >= limit:
            sleep_time = 60 - (now - _request_times[0])
            if sleep_time > 0:
                logger.debug("Лимит запросов: пауза %.1f сек", sleep_time)
                time.sleep(sleep_time)
        _request_times.append(time.time())


def record_request() -> None:
    """Учесть запрос для лимита (вызывать перед запросом или после паузы)."""
    with _get_lock():
        _request_times.append(time.time())


def get_polite_delay() -> float:
    """Случайная задержка между запросами (сек) по настройкам."""
    import random
    return random.uniform(DELAY_MIN_SEC, DELAY_MAX_SEC)


def get_identifiable_headers() -> dict:
    """Заголовки с идентифицируемым User-Agent (для соответствия лучшим практикам)."""
    return {
        "User-Agent": USER_AGENT_IDENTIFIABLE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }


def audit_log(action: str, source: str, success: bool, details: Optional[dict] = None) -> None:
    """
    Аудит запросов без записи персональных данных (ФЗ‑152, минимизация).
    В details не передавать ФИО, адреса, номера ИП — только метаданные (количество записей, код ответа).
    """
    if details is None:
        details = {}
    safe_details = {k: v for k, v in details.items() if k in ("count", "records", "status_code", "duration_sec", "error_type", "query_type")}
    logger.info("Парсинг | %s | %s | success=%s | %s", source, action, success, safe_details)


def check_robots_txt_allowed(base_url: str, path: str = "/") -> Optional[bool]:
    """
    Проверить, разрешён ли путь в robots.txt. Возвращает True — разрешено, False — запрещено, None — не удалось получить.
    Рекомендуется вызывать перед первым запросом к домену.
    """
    try:
        from urllib.parse import urljoin, urlparse
        import requests
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        r = requests.get(robots_url, timeout=10, headers=get_identifiable_headers())
        if r.status_code != 200:
            return None
        # Упрощённый разбор: ищем User-agent: * и Disallow: /path
        in_star = False
        for line in r.text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("user-agent:"):
                in_star = line[11:].strip() == "*"
                continue
            if in_star and line.lower().startswith("disallow:"):
                disallow = line[9:].strip()
                if disallow and (path.startswith(disallow) or (disallow.endswith("/") and path.startswith(disallow.rstrip("/")))):
                    return False
        return True
    except Exception as e:
        logger.debug("robots.txt check: %s", e)
        return None
