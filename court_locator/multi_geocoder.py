"""
Многоисточниковое геокодирование с верификацией.
Yandex + DaData: перекрёстная проверка, консенсус при расхождении < 100 м.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

_logger = logging.getLogger("court_locator.multi_geocoder")

from court_locator import config
from court_locator.log_sanitize import redact_secrets
from court_locator.geocode_verification import (
    GeocodeResult,
    CONFIDENCE_EXACT,
    CONFIDENCE_STREET,
    CONFIDENCE_CITY,
    CONFIDENCE_LOW,
    LEVEL_AUTO,
    LEVEL_SEMI,
    LEVEL_MANUAL,
    LEVEL_EXTERNAL,
    check_coordinate_consistency,
    weighted_average_coordinates,
    best_available_result,
    MAX_CONSENSUS_DISTANCE_M,
)


def _yandex_geocode_full(address: str) -> Optional[Dict[str, Any]]:
    """Yandex Geocoder с полным ответом (lat, lon, confidence)."""
    if not config.YANDEX_GEO_KEY:
        return None
    try:
        import requests
        url = "https://geocode-maps.yandex.ru/1.x/"
        params = {"apikey": config.YANDEX_GEO_KEY, "geocode": address, "format": "json", "results": 1}
        r = requests.get(url, params=params, timeout=config.GEOCODE_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        members = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
        if not members:
            return None
        obj = members[0].get("GeoObject", {})
        pos = obj.get("Point", {}).get("pos")
        if not pos:
            return None
        lon, lat = map(float, pos.split())
        meta = obj.get("metaDataProperty", {}).get("GeocoderMetaData", {})
        precision = (meta.get("precision") or "approximate").lower()
        if precision in ("exact", "number"):
            confidence = CONFIDENCE_EXACT
        elif "street" in precision or "street" in (meta.get("kind") or ""):
            confidence = CONFIDENCE_STREET
        elif "locality" in (meta.get("kind") or "") or "city" in precision:
            confidence = CONFIDENCE_CITY
        else:
            confidence = CONFIDENCE_LOW
        return {
            "lat": lat,
            "lon": lon,
            "confidence": confidence,
            "normalized_address": meta.get("text") or address,
        }
    except Exception as e:
        _logger.warning("yandex_geocode_full failed: %s", redact_secrets(str(e)))
        return None


def _dadata_geocode_full(address: str) -> Optional[Dict[str, Any]]:
    """DaData suggest/address с полным ответом."""
    if not config.DADATA_TOKEN:
        return None
    try:
        from court_locator.parser_bridge import dadata_geocode_address

        r = dadata_geocode_address(address, token=config.DADATA_TOKEN)
        if r:
            r["confidence"] = r.get("confidence", CONFIDENCE_LOW)
            return r
    except Exception as e:
        _logger.warning("dadata_geocode_full failed: %s", redact_secrets(str(e)))
    return None


def _nominatim_geocode_full(address: str) -> Optional[Dict[str, Any]]:
    """Nominatim с базовым ответом (низкая точность для РФ)."""
    try:
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="court_locator_parser")
        location = geolocator.geocode(address, timeout=config.GEOCODE_TIMEOUT)
        if location:
            return {
                "lat": location.latitude,
                "lon": location.longitude,
                "confidence": CONFIDENCE_LOW,
                "normalized_address": location.address or address,
            }
    except Exception as e:
        _logger.warning("nominatim_geocode_full failed: %s", redact_secrets(str(e)))
    return None


def multi_source_geocode(address: str) -> Optional[GeocodeResult]:
    """
    Многоисточниковое геокодирование с верификацией.
    При наличии Yandex и DaData — перекрёстная проверка, консенсус при расхождении < 100 м.
    """
    address = (address or "").strip()
    if not address:
        return None

    results: List[Tuple[str, Dict[str, Any]]] = []
    coord_results: List[Tuple[str, Tuple[float, float]]] = []

    yandex = _yandex_geocode_full(address)
    if yandex:
        results.append(("yandex", yandex))
        coord_results.append(("yandex", (yandex["lat"], yandex["lon"])))

    dadata = _dadata_geocode_full(address)
    if dadata:
        results.append(("dadata", dadata))
        coord_results.append(("dadata", (dadata["lat"], dadata["lon"])))

    if len(coord_results) >= 2 and check_coordinate_consistency(
        coord_results, max_distance_m=MAX_CONSENSUS_DISTANCE_M
    ):
        lat, lon = weighted_average_coordinates(coord_results)
        best = results[0]
        conf = best[1].get("confidence", CONFIDENCE_EXACT)
        return GeocodeResult(
            lat=lat,
            lon=lon,
            confidence=conf,
            source="multi_verified",
            normalized_address=best[1].get("normalized_address", address),
            needs_manual_review=False,
            processing_level=LEVEL_AUTO,
        )

    if not results:
        nominatim = _nominatim_geocode_full(address)
        if nominatim:
            results.append(("nominatim", nominatim))

    gr = best_available_result(results)
    if not gr:
        return None

    needs_review = gr.confidence in (CONFIDENCE_CITY, CONFIDENCE_LOW)
    level = LEVEL_AUTO if gr.confidence == CONFIDENCE_EXACT else (
        LEVEL_SEMI if gr.confidence == CONFIDENCE_STREET else (
            LEVEL_MANUAL if gr.confidence == CONFIDENCE_CITY else LEVEL_EXTERNAL
        )
    )
    gr.needs_manual_review = needs_review
    gr.processing_level = level
    return gr
