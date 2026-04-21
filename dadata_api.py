"""
DaData API — подсказки судов по адресу + Profile API (баланс, статистика, версии).
Регистрация: dadata.ru → Бесплатный тариф → Token + Secret.
Лимит: 10 000 запросов/день бесплатно на подсказки.
"""
import os
from typing import Optional, Dict, Any, List

import requests

DADATA_COURT_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/court"
DADATA_ADDRESS_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
DADATA_GEOLOCATE_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/geolocate/address"
DADATA_PROFILE_BASE = "https://dadata.ru/api/v2"


def _get_token() -> Optional[str]:
    token = os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY")
    return token.strip() if token else None


def _get_secret() -> Optional[str]:
    return (os.getenv("DADATA_SECRET") or os.getenv("DADATA_SECRET_KEY") or "").strip() or None


def _profile_headers() -> Dict[str, str]:
    """Заголовки для Profile API: нужны и Token, и X-Secret."""
    token = _get_token()
    secret = _get_secret()
    if not token:
        return {}
    h = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if secret:
        h["X-Secret"] = secret
    return h


def get_balance(token: Optional[str] = None, secret: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Баланс пользователя DaData (руб.).
    Требуется DADATA_TOKEN; для Profile API желателен DADATA_SECRET (X-Secret).
    Возвращает {"balance": float} или None при ошибке.
    """
    url = f"{DADATA_PROFILE_BASE}/profile/balance"
    headers = _profile_headers()
    if token:
        headers = {**headers, "Authorization": f"Token {token}"}
    if secret:
        headers["X-Secret"] = secret
    if not headers.get("Authorization"):
        return None
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def get_daily_stats(token: Optional[str] = None, secret: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Статистика использования сервисов DaData за сегодня.
    Возвращает dict с полями по сервисам (подсказки, стандартизация и т.д.) или None.
    """
    url = f"{DADATA_PROFILE_BASE}/stat/daily"
    headers = _profile_headers()
    if token:
        headers = {**headers, "Authorization": f"Token {token}"}
    if secret:
        headers["X-Secret"] = secret
    if not headers.get("Authorization"):
        return None
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def get_versions(token: Optional[str] = None, secret: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Версии сервисов DaData и даты актуальности справочников.
    """
    url = f"{DADATA_PROFILE_BASE}/version"
    headers = _profile_headers()
    if token:
        headers = {**headers, "Authorization": f"Token {token}"}
    if secret:
        headers["X-Secret"] = secret
    if not headers.get("Authorization"):
        return None
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# Типы судов для фильтра DaData (court_type): MS — мировые, G — городские, RS — районный и т.д.
DADATA_COURT_TYPE_MS = "MS"   # мировой суд
DADATA_COURT_TYPE_RS = "RS"   # районный, городской, межрайонный
DADATA_COURT_TYPE_G = "G"     # городской


def suggest_court(
    query: str,
    region: Optional[str] = None,
    count: int = 5,
    token: Optional[str] = None,
    court_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Поиск суда по адресу или названию.
    query: адрес (например "Москва, ул. Ленина 15") или название суда.
    region: ограничение по региону (например "Москва").
    court_type: фильтр типа суда (MS — мировые, RS — районные, G — городские и т.д.).
    Возвращает список suggestions или пустой список при ошибке/отсутствии токена.
    """
    tok = token or _get_token()
    if not tok:
        return []

    payload = {"query": query, "count": count}
    if region:
        payload["locations"] = [{"region": region}]
    if court_type:
        payload["filters"] = [{"court_type": court_type}]

    headers = {
        "Authorization": f"Token {tok}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(DADATA_COURT_URL, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("suggestions") or []
    except Exception:
        return []


def court_suggestion_to_result(suggestion: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Преобразует один элемент из ответа DaData в формат, совместимый с CourtResult.
    Возвращает dict с полями court_name, address, index, region, type или None.
    """
    if not suggestion or not isinstance(suggestion.get("data"), dict):
        return None
    d = suggestion["data"]
    return {
        "court_name": d.get("name") or suggestion.get("value", ""),
        "address": d.get("address", {}).get("value") if isinstance(d.get("address"), dict) else d.get("address") or "",
        "postal_index": (
            d.get("address", {}).get("postal_code") or ""
            if isinstance(d.get("address"), dict)
            else ""
        ),
        "region": d.get("region") or "",
        "type": d.get("type") or "",
    }


def standardize_address(address: str, token: Optional[str] = None) -> Optional[str]:
    """
    Стандартизация адреса по ФИАС через DaData suggest/address.
    Возвращает нормализованную строку адреса или None при ошибке/отсутствии токена.
    """
    tok = token or _get_token()
    if not tok:
        return None
    try:
        r = requests.post(
            DADATA_ADDRESS_URL,
            json={"query": address, "count": 1},
            headers={"Authorization": f"Token {tok}", "Content-Type": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        suggestions = data.get("suggestions") or []
        if not suggestions:
            return None
        s = suggestions[0]
        d = s.get("data") or {}
        return d.get("value") or s.get("value", "")
    except Exception:
        return None


def geolocate_address(
    lat: float,
    lon: float,
    token: Optional[str] = None,
    *,
    count: int = 1,
    radius_meters: int = 100,
) -> Optional[Dict[str, Any]]:
    """
    Обратное геокодирование: координаты → адрес (и компоненты ФИАС).
    Используется как fallback при 403/сбое Yandex Geocoder.

    Возвращает dict: region, district, locality, formatted (или None).
    """
    tok = token or _get_token()
    if not tok:
        return None
    try:
        r = requests.post(
            DADATA_GEOLOCATE_URL,
            json={
                "lat": lat,
                "lon": lon,
                "count": min(max(count, 1), 20),
                "radius_meters": max(10, min(radius_meters, 1000)),
            },
            headers={"Authorization": f"Token {tok}", "Content-Type": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        suggestions = data.get("suggestions") or []
        if not suggestions:
            return None
        d = (suggestions[0].get("data") or {}) if isinstance(suggestions[0], dict) else {}
        if not isinstance(d, dict):
            return None
        region = (d.get("region_with_type") or d.get("region") or "").strip()
        # Район: сначала район города, затем район области; не подставлять city=Москва вместо Тверского
        district = None
        for key in ("city_district", "area", "sub_area", "settlement"):
            v = d.get(key)
            if v and str(v).strip():
                district = str(v).strip()
                break
        if not district and d.get("city"):
            cty = str(d.get("city")).strip()
            reg_plain = (d.get("region") or "").strip()
            if cty and reg_plain and cty.lower() != reg_plain.lower():
                district = cty
        locality = (d.get("city") or d.get("settlement") or "").strip() or None
        formatted = (d.get("value") or suggestions[0].get("value") or "").strip()
        if not region and not formatted:
            return None
        return {
            "region": region,
            "district": district,
            "locality": locality,
            "formatted": formatted,
        }
    except Exception:
        return None


def geocode_address(address: str, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Геокодирование адреса через DaData suggest/address.
    Возвращает dict с lat, lon, normalized_address, accuracy или None.
    """
    tok = token or _get_token()
    if not tok:
        return None
    try:
        r = requests.post(
            DADATA_ADDRESS_URL,
            json={"query": address, "count": 1},
            headers={"Authorization": f"Token {tok}", "Content-Type": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        suggestions = data.get("suggestions") or []
        if not suggestions:
            return None
        s = suggestions[0]
        d = s.get("data") or {}
        geo = d.get("geo_lat"), d.get("geo_lon")
        if not geo[0] or not geo[1]:
            return None
        try:
            lat, lon = float(geo[0]), float(geo[1])
        except (TypeError, ValueError):
            return None
        # qc_geo: 0=точное, 1=ближайший дом, 2=улица, 3=населённый пункт, 4=город, 5=не определено
        qc = d.get("qc_geo")
        if qc in (0, 1):
            confidence = "exact"
        elif qc == 2:
            confidence = "street"
        elif qc in (3, 4):
            confidence = "city"
        else:
            confidence = "low"
        return {
            "lat": lat,
            "lon": lon,
            "normalized_address": d.get("value") or s.get("value", ""),
            "accuracy": qc,
            "confidence": confidence,
        }
    except Exception:
        return None


def find_court_by_address(
    address: str,
    region: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    По адресу возвращает первый подходящий мировой суд (или любой суд).
    Возвращает dict для CourtResult (court_name, address, postal_index) или None.
    """
    suggestions = suggest_court(address, region=region, count=5, token=token)
    for s in suggestions:
        row = court_suggestion_to_result(s)
        if not row:
            continue
        # предпочитаем мировых судей
        t = (row.get("type") or "").lower()
        if "мировой" in t or "миров" in t:
            return row
    if suggestions:
        return court_suggestion_to_result(suggestions[0])
    return None
