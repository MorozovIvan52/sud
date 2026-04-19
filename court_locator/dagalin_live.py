"""
Живой запрос карточки суда на dagalin.org при обработке адреса (приоритет над кэшем detail_json).

Переменные окружения:
  DAGALIN_LIVE_FETCH — 0/false/off отключает HTTP (только detail_json из БД).
  DAGALIN_LIVE_TIMEOUT — таймаут запроса, сек (по умолчанию 20).
  DAGALIN_INSECURE_SSL — 1 при проблемах с сертификатом.
  DAGALIN_HOST_HEADER — Host при обращении по IP.
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from court_locator.database import Database

_logger = logging.getLogger("court_locator.dagalin_live")


def _live_fetch_enabled() -> bool:
    v = (os.environ.get("DAGALIN_LIVE_FETCH") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def fetch_dagalin_html(url: str) -> Optional[str]:
    if not url or not url.startswith("http"):
        return None
    try:
        import requests
    except ImportError:
        _logger.warning("dagalin_live: requests не установлен")
        return None

    timeout = float((os.environ.get("DAGALIN_LIVE_TIMEOUT") or "20").strip() or "20")
    verify = (os.environ.get("DAGALIN_INSECURE_SSL") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (compatible; ParserPRO-DagalinLive/1.0)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
    host = (os.environ.get("DAGALIN_HOST_HEADER") or "").strip()
    if host:
        headers["Host"] = host
    try:
        r = requests.get(url, timeout=timeout, verify=verify, headers=headers)
        ct = r.headers.get("Content-Type", "")
        if r.status_code == 200 and "html" in ct.lower():
            return r.text
    except Exception as e:
        _logger.debug("dagalin_live fetch %s: %s", url, e)
    return None


def apply_parsed_dagalin_to_court(court: Dict[str, Any], parsed: Dict[str, Any]) -> None:
    """Поля карточки и блоки superior / реквизиты / ОСП — из свежего парсинга."""
    cc = parsed.get("court_card") or {}
    if cc.get("name"):
        court["court_name"] = cc["name"]
    if cc.get("address"):
        court["address"] = cc["address"]
    if cc.get("phone"):
        court["phone"] = cc["phone"]
    if cc.get("email"):
        court["email"] = cc["email"]
    if cc.get("schedule"):
        court["schedule"] = cc["schedule"]
    sns = cc.get("section_numbers") or []
    if len(sns) == 1:
        try:
            court["section_num"] = int(sns[0])
        except (TypeError, ValueError):
            pass
    for key in ("superior_court", "state_fee_requisites", "bailiffs"):
        block = parsed.get(key)
        if isinstance(block, dict) and block:
            court[key] = block


def apply_detail_json_to_court(court: Dict[str, Any], detail: Dict[str, Any]) -> None:
    """Только расширенные блоки из кэша (без перезаписи основной карточки суда)."""
    for key in ("superior_court", "state_fee_requisites", "bailiffs"):
        block = detail.get(key)
        if isinstance(block, dict) and block:
            court[key] = block


def merge_live_or_cached_dagalin(
    court: Dict[str, Any],
    row: Dict[str, Any],
    db: "Database",
) -> None:
    """
    Сначала парсинг страницы dagalin по source_url, при успехе — обновление БД и court.
    Иначе — подстановка detail_json из строки.
    """
    url = (row.get("source_url") or "").strip()
    parsed: Optional[Dict[str, Any]] = None

    if _live_fetch_enabled() and url:
        html = fetch_dagalin_html(url)
        if html:
            try:
                from court_locator.dagalin_page_parse import (
                    dagalin_detail_to_json_str,
                    parse_dagalin_detail_html,
                )

                parsed = parse_dagalin_detail_html(html, url)
            except Exception as e:
                _logger.debug("dagalin_live parse %s: %s", url, e)
                parsed = None
        if parsed:
            apply_parsed_dagalin_to_court(court, parsed)
            dj = dagalin_detail_to_json_str(parsed)
            if dj:
                try:
                    db.update_dagalin_detail_json(url, dj)
                except Exception as e:
                    _logger.debug("dagalin_live cache write: %s", e)
            return

    dj_raw = row.get("detail_json")
    if dj_raw and str(dj_raw).strip():
        try:
            detail = json.loads(dj_raw) if isinstance(dj_raw, str) else dj_raw
        except json.JSONDecodeError:
            detail = None
        if isinstance(detail, dict):
            apply_detail_json_to_court(court, detail)
