"""
Вспомогательные функции court_locator.
"""
from typing import Optional, Tuple


def normalize_coordinates(lat: Optional[float], lng: Optional[float]) -> Optional[Tuple[float, float]]:
    """Проверяет и возвращает (lat, lng) или None."""
    if lat is None or lng is None:
        return None
    try:
        lat_f, lng_f = float(lat), float(lng)
        if -90 <= lat_f <= 90 and -180 <= lng_f <= 180:
            return (lat_f, lng_f)
    except (TypeError, ValueError):
        pass
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в км (формула Haversine)."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def court_row_to_result(
    row: dict,
    source: str = "court_locator",
    *,
    confidence: Optional[str] = None,
    needs_manual_review: Optional[bool] = None,
    processing_level: Optional[str] = None,
) -> dict:
    """Приводит строку БД к единому формату результата (совместимо с parser)."""
    sn = row.get("section_num") or row.get("section")
    if sn is not None:
        try:
            sn = int(sn)
        except (TypeError, ValueError):
            sn = 0
    else:
        sn = 0
    out = {
        "court_name": row.get("court_name") or row.get("name") or row.get("district_number") or "",
        "address": row.get("address") or "",
        "postal_index": row.get("postal_index") or "",
        "region": row.get("region") or "",
        "district": row.get("district") or "",
        "section_num": sn,
        "phone": row.get("phone") or "",
        # court_details.py ожидает email в ключах "email" или "court_email"
        "email": row.get("email") or row.get("court_email") or "",
        "schedule": row.get("schedule") or "",
        "judge_name": row.get("judge_name") or "",
        "source": source,
    }
    if confidence is not None:
        out["confidence"] = confidence
    if needs_manual_review is not None:
        out["needs_manual_review"] = needs_manual_review
    if processing_level is not None:
        out["processing_level"] = processing_level
    return out
