"""
СУПЕР-ПАРСЕР: обёртка над determine_jurisdiction с confidence, ссылками на реквизиты и КБК.
5 уровней точности: DaData → паспорт → адрес → ГАС по ФИО → fallback.
Кэш 7 дней — молниеносный повтор для тех же данных.
"""
import hashlib
import json
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from jurisdiction import determine_jurisdiction, CourtResult
from regions_rf import get_rekvizity_urls

_CACHE_DB = Path(__file__).parent / "super_cache.sqlite"
_CACHE_DAYS = 7

# Точность по источнику (0.0–1.0)
CONFIDENCE_BY_SOURCE = {
    "dadata": 0.98,
    "address_geo": 0.95,  # Yandex Geocoder + БД судов (обход DaData)
    "passport_code": 0.95,
    "address": 0.90,
    "fio_sudrf": 0.85,
    "fallback_rule": 0.50,
}

KBK_DEFAULT = "18210803010011050110"


@dataclass
class SuperCourtResult:
    court_name: str
    court_address: str
    court_index: str
    court_region: str
    court_section: int
    rekvizity_url: str
    sudrf_url: str
    court_site: str
    gasp_raw: str
    confidence: float
    source: str
    kbk: str
    jurisdiction_type: str
    gpk_article: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _cache_key(fio: str, passport: str, address: str) -> str:
    raw = f"{fio}|{passport}|{address}".strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _init_cache_db():
    conn = sqlite3.connect(_CACHE_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS super_cache (
            key_hash TEXT PRIMARY KEY,
            result_json TEXT NOT NULL,
            confidence REAL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    conn.close()


def _get_cached(key_hash: str) -> Optional[SuperCourtResult]:
    _init_cache_db()
    conn = sqlite3.connect(_CACHE_DB)
    row = conn.execute(
        """
        SELECT result_json FROM super_cache
        WHERE key_hash = ? AND datetime(created_at) > datetime('now', ?)
        """,
        (key_hash, f"-{_CACHE_DAYS} days"),
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        d = json.loads(row[0])
        return SuperCourtResult(**d)
    except Exception:
        return None


def get_cached_with_meta(key_hash: str) -> Tuple[Optional[SuperCourtResult], Optional[str]]:
    """Возвращает (результат из кэша, created_at ISO) или (None, None)."""
    _init_cache_db()
    conn = sqlite3.connect(_CACHE_DB)
    row = conn.execute(
        """
        SELECT result_json, created_at FROM super_cache
        WHERE key_hash = ? AND datetime(created_at) > datetime('now', ?)
        """,
        (key_hash, f"-{_CACHE_DAYS} days"),
    ).fetchone()
    conn.close()
    if not row:
        return None, None
    try:
        d = json.loads(row[0])
        return SuperCourtResult(**d), (row[1] if len(row) > 1 else None)
    except Exception:
        return None, None


def _set_cached(key_hash: str, result: SuperCourtResult):
    _init_cache_db()
    conn = sqlite3.connect(_CACHE_DB)
    conn.execute(
        "INSERT OR REPLACE INTO super_cache (key_hash, result_json, confidence) VALUES (?, ?, ?)",
        (key_hash, json.dumps(asdict(result), ensure_ascii=False), result.confidence),
    )
    conn.commit()
    conn.close()


def super_determine_jurisdiction(data: Dict[str, Any], use_cache: bool = True) -> SuperCourtResult:
    """
    Определяет подсудность и возвращает результат с confidence, ссылками на реквизиты и КБК.
    При use_cache=True повторные запросы с теми же fio+passport+address берутся из кэша (7 дней).
    """
    fio = (data.get("fio") or "").strip()
    passport = (data.get("passport") or "").strip()
    address = (data.get("address") or "").strip()

    if use_cache:
        key = _cache_key(fio, passport, address)
        cached = _get_cached(key)
        if cached is not None:
            return cached

    cr: CourtResult = determine_jurisdiction(data)
    confidence = CONFIDENCE_BY_SOURCE.get(cr.source, 0.5)
    region = cr.court_region or ""
    section = cr.section_num or 0
    urls = get_rekvizity_urls(region, section)

    result = SuperCourtResult(
        court_name=cr.court_name,
        court_address=cr.address,
        court_index=cr.index,
        court_region=region,
        court_section=section,
        rekvizity_url=urls.get("rekvizity_url", ""),
        sudrf_url=urls.get("sudrf_search", ""),
        court_site=urls.get("court_site", ""),
        gasp_raw=urls.get("gasp_raw", ""),
        confidence=confidence,
        source=cr.source,
        kbk=KBK_DEFAULT,
        jurisdiction_type=cr.jurisdiction_type,
        gpk_article=cr.gpk_article,
    )
    if use_cache:
        _set_cached(_cache_key(fio, passport, address), result)
    return result


def state_duty_from_debt(debt_amount: float) -> float:
    """Госпошлина по иску до 1 млн: 3.2% + фикс, но не более 6000 (упрощённо — до 4 тыс.)."""
    if debt_amount <= 0:
        return 0.0
    # Упрощённая формула: 3.2% при сумме до 200 тыс., иначе ступенчато
    duty = min(4000, debt_amount * 0.032)
    return round(duty, 2)
