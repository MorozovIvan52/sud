"""
Пайплайн обработки должника: адрес → нормализация → unified_jurisdiction (по умолчанию) или court_locator → court_details.
"""
import os
import time
from pathlib import Path
from typing import Any, Optional

import sys

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "parser") not in sys.path:
    sys.path.insert(0, str(ROOT / "parser"))

_USE_UNIFIED = os.getenv("BATCH_USE_UNIFIED_JURISDICTION", "1").strip().lower() not in ("0", "false", "no")


def _normalize_input_address(original_address: str) -> str:
    o = (original_address or "").strip()
    try:
        from batch_processing.services.address_normalization import normalize_address_fias

        return normalize_address_fias(o) or o
    except Exception:
        try:
            from batch_processing.services.address_normalization import normalize_address_fssp

            return normalize_address_fssp(o) or o
        except Exception:
            return o


def _process_debtor_unified(
    fio: str,
    original_address: str,
    normalized_address: str,
    debt_amount: Optional[float],
    lat: Optional[float],
    lng: Optional[float],
    *,
    start_time: float,
) -> dict[str, str]:
    from unified_jurisdiction import UnifiedJurisdictionClient, FindCourtRequest
    from court_locator.court_details import build_court_details

    client = UnifiedJurisdictionClient(use_cache=True)
    try:
        court = None
        last_confidence = None
        last_review = False
        if lat is not None and lng is not None:
            r = client.find_court(FindCourtRequest(latitude=lat, longitude=lng))
            if r.success and r.court:
                court = r.court
                last_confidence = r.confidence_score
                last_review = r.needs_manual_review
        if court is None and normalized_address:
            r = client.find_court(FindCourtRequest(address=normalized_address))
            if r.success and r.court:
                court = r.court
                last_confidence = r.confidence_score
                last_review = r.needs_manual_review
        if court is None:
            result = _error_result(
                normalized_address,
                "Суд не найден",
                error_code="ERROR_ADDRESS_NOT_FOUND" if not (lat and lng) else "ERROR_COURT_NOT_FOUND",
                original_address=original_address,
            )
            _log_metrics(result, start_time)
            return result
        conf_str = str(last_confidence) if last_confidence is not None else court.get("confidence") or ""
        details = build_court_details(
            court,
            normalized_address=normalized_address,
            debt_amount=debt_amount,
            confidence=conf_str,
            needs_manual_review=last_review or court.get("needs_manual_review", False),
        )
        _log_metrics(details, start_time, district=court.get("region"), source=court.get("source"))
        return details
    finally:
        client.close()


def process_debtor(
    fio: str,
    address: str,
    passport: Optional[str] = None,
    debt_amount: Optional[float] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> dict[str, str]:
    """
    Обрабатывает одного должника: определяет подсудность, собирает 45 полей.

    По умолчанию используется UnifiedJurisdictionClient (см. BATCH_USE_UNIFIED_JURISDICTION).
    :return: словарь 45 полей (ключи — названия колонок)
    """
    start = time.perf_counter()
    original_address = (address or "").strip()
    normalized_address = _normalize_input_address(original_address)

    if _USE_UNIFIED:
        return _process_debtor_unified(
            fio,
            original_address,
            normalized_address,
            debt_amount,
            lat,
            lng,
            start_time=start,
        )

    from court_locator.main import CourtLocator
    from court_locator.court_details import build_court_details

    locator = CourtLocator(use_cache=True)
    try:
        court: Optional[dict[str, Any]] = None

        if lat is not None and lng is not None:
            court = locator.locate_court(lat=lat, lng=lng)
        if court is None and normalized_address:
            court = locator.locate_court(address=normalized_address)

        if court is None:
            result = _error_result(
                normalized_address,
                "Суд не найден",
                error_code="ERROR_ADDRESS_NOT_FOUND" if not (lat and lng) else "ERROR_COURT_NOT_FOUND",
                original_address=original_address,
            )
            _log_metrics(result, start)
            return result

        details = build_court_details(
            court,
            normalized_address=normalized_address,
            debt_amount=debt_amount,
        )
        _log_metrics(details, start, district=court.get("region"), source=court.get("source"))
        return details
    finally:
        locator.close()


def _log_metrics(
    result: dict[str, Any],
    start_time: float,
    district: Optional[str] = None,
    source: Optional[str] = None,
) -> None:
    """Пишет метрику в MetricsCollector."""
    try:
        from batch_processing.services.metrics_collector import get_metrics_collector
        success = bool(result.get("Наименование суда")) and "ERROR" not in str(result.get("Тип производства", ""))
        elapsed = time.perf_counter() - start_time
        error_type = result.get("_error_code") if not success else None
        src = source or result.get("Источник данных") or None
        get_metrics_collector().log_request(
            success=success,
            processing_time=elapsed,
            error_type=error_type,
            district=district,
            source=src,
        )
    except Exception:
        pass


def _error_result(
    normalized_address: str,
    error_msg: str,
    error_code: Optional[str] = None,
    original_address: Optional[str] = None,
) -> dict[str, str]:
    """Результат при ошибке: флаг ERROR, код ошибки, пустые поля суда."""
    from batch_processing.schemas.debtor_result import DEBTOR_RESULT_COLUMNS
    from batch_processing.constants import get_error_code, ERROR_COURT_NOT_FOUND

    code = error_code or get_error_code(error_msg)
    row = {col: "" for col in DEBTOR_RESULT_COLUMNS}
    row["Нормализованный адрес"] = normalized_address
    row["Тип производства"] = f"ERROR: {error_msg}"
    row["_error_code"] = code
    row["_original_address"] = original_address or normalized_address
    return row


def process_debtor_gps(
    lat: float,
    lng: float,
    debt_amount: Optional[float] = None,
    case_type: Optional[str] = None,
) -> dict[str, str]:
    """
    Обработка по GPS-координатам (без парсинга адресов).
    По умолчанию — UnifiedJurisdictionClient.
    """
    from batch_processing.utils.file_handler import validate_coordinates

    ok, err = validate_coordinates(lat, lng)
    if not ok:
        return _error_result(f"{lat},{lng}", err, error_code="ERROR_INVALID_COORDS")

    start = time.perf_counter()
    normalized = f"{lat:.6f}, {lng:.6f}"
    prod_type = (case_type or "").strip() or "Гражданское (ГПК РФ)"

    if _USE_UNIFIED:
        r = _process_debtor_unified(
            "",
            normalized,
            normalized,
            debt_amount,
            lat,
            lng,
            start_time=start,
        )
        r["Тип производства"] = prod_type
        return r

    from court_locator.main import CourtLocator
    from court_locator.court_details import build_court_details

    locator = CourtLocator(use_cache=True)
    try:
        court = locator.locate_court(lat=lat, lng=lng)
        if court is None:
            return _error_result(f"{lat:.6f},{lng:.6f}", "Точка не попадает в границы участков", error_code="ERROR_COURT_NOT_FOUND")

        details = build_court_details(court, normalized_address=normalized, debt_amount=debt_amount)
        details["Тип производства"] = prod_type
        return details
    finally:
        locator.close()


def process_batch_gps(
    rows: list[dict[str, Any]],
    *,
    chunk_size: int = 1000,
) -> list[dict[str, str]]:
    """
    Пакетная обработка по GPS. Каждый элемент — dict с lat, lng, debt_amount, case_type.
    Строки без валидных координат пропускаются с ERROR.
    """
    from batch_processing.utils.file_handler import validate_coordinates

    results: list[dict[str, str]] = []
    for d in rows:
        lat, lng = d.get("lat"), d.get("lng")
        ok, err = validate_coordinates(lat, lng)
        if not ok:
            results.append(_error_result(f"{lat},{lng}", err, error_code="ERROR_INVALID_COORDS"))
            continue

        debt = d.get("debt_amount")
        if debt is not None:
            try:
                debt = float(debt)
            except (TypeError, ValueError):
                debt = None

        r = process_debtor_gps(
            lat=float(lat),
            lng=float(lng),
            debt_amount=debt,
            case_type=d.get("case_type"),
        )
        results.append(r)
    return results


def process_batch(
    debtors: list[dict[str, Any]],
    *,
    chunk_size: int = 1000,
) -> list[dict[str, str]]:
    """
    Обрабатывает список должников. Каждый элемент debtors — dict с fio, address, passport, debt_amount, lat, lng.
    """
    results: list[dict[str, str]] = []
    for i, d in enumerate(debtors):
        fio = (d.get("fio") or "").strip()
        address = (d.get("address") or "").strip()
        if not fio and not address:
            err_r = _error_result("", "Пустая строка", error_code="ERROR_EMPTY_ROW", original_address="")
            err_r["id"], err_r["contract_number"] = d.get("id", ""), d.get("contract_number", "")
            results.append(err_r)
            continue
        if not address:
            err_r = _error_result(fio or "", "Адрес не указан", error_code="ERROR_NO_ADDRESS", original_address="")
            err_r["id"], err_r["contract_number"] = d.get("id", ""), d.get("contract_number", "")
            results.append(err_r)
            continue

        debt = d.get("debt_amount")
        if debt is not None:
            try:
                debt = float(debt)
            except (TypeError, ValueError):
                debt = None

        r = process_debtor(
            fio=fio,
            address=address,
            passport=d.get("passport"),
            debt_amount=debt,
            lat=d.get("lat"),
            lng=d.get("lng"),
        )
        r["id"] = d.get("id", "")
        r["contract_number"] = d.get("contract_number", "")
        results.append(r)
    return results
