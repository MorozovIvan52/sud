"""
Получение координат по адресу или с устройства.
Гибридная цепочка: многоисточниковая верификация (Yandex+DaData) → Yandex → DaData → Nominatim.
Кэширование: Redis (GEOCODE_CACHE_TTL) или in-memory.
Соответствие docs/jurisdiction_conclusion.md (элемент 2): геокодирование с точностью до здания, confidence.
"""
import logging
from typing import Optional, Tuple

_logger = logging.getLogger("court_locator.gps_handler")

from court_locator import config
from court_locator.geocode_verification import GeocodeResult
from court_locator.log_sanitize import redact_secrets


def _normalize_region_for_courts(name: Optional[str]) -> Optional[str]:
    """Приводит название региона к виду, как в БД courts (Москва, Санкт-Петербург)."""
    if not name or not name.strip():
        return None
    n = name.strip()
    lower = n.lower()
    if "москва" in lower and "область" not in lower and "обл" not in lower:
        return "Москва"
    if "санкт-петербург" in lower or "спб" in lower or "петербург" in lower:
        return "Санкт-Петербург"
    if " область" in lower or " обл." in lower:
        return n
    return n


class GPSHandler:
    """Геокодирование адреса -> (lat, lon)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (api_key or config.YANDEX_GEO_KEY).strip()

    def get_coordinates(
        self,
        address: Optional[str] = None,
        use_gps: bool = False,
    ) -> Optional[Tuple[float, float]]:
        """
        Получает координаты по адресу или через GPS.
        use_gps: в серверном Python недоступен; для веб/мобильных — передавать lat/lng в locate_court.
        """
        if use_gps:
            return self._get_device_gps()
        if address:
            return self._geocode_address(address)
        return None

    def _get_device_gps(self) -> Optional[Tuple[float, float]]:
        """В серверном приложении недоступен."""
        return None

    def _geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """Гибрид: многоисточниковая верификация → Yandex → DaData → Nominatim. С кэшированием."""
        gr = self.geocode_with_verification(address)
        return (gr.lat, gr.lon) if gr else None

    def geocode_with_verification(self, address: str) -> Optional[GeocodeResult]:
        """
        Многоисточниковое геокодирование с верификацией (Yandex+DaData при согласованности < 100 м).
        Возвращает GeocodeResult с confidence, needs_manual_review, processing_level.
        """
        address = (address or "").strip()
        if not address:
            return None
        try:
            from court_locator.geocode_cache import GeocodeCache
            cache = GeocodeCache()
            cached = cache.get(address)
            if cached:
                lat, lon = cached
                return GeocodeResult(
                    lat=lat, lon=lon,
                    confidence="exact",
                    source="cache",
                    normalized_address=address,
                    needs_manual_review=False,
                    processing_level="auto",
                )
        except Exception:
            pass
        try:
            from court_locator.multi_geocoder import multi_source_geocode
            gr = multi_source_geocode(address)
            if gr:
                try:
                    from court_locator.geocode_cache import GeocodeCache
                    GeocodeCache().set(address, gr.lat, gr.lon)
                except Exception:
                    pass
                return gr
        except Exception:
            pass
        coords = None
        if self.api_key:
            coords = self._yandex_geocode(address)
        if not coords and config.DADATA_TOKEN:
            coords = self._dadata_geocode(address)
        if not coords:
            coords = self._nominatim_geocode(address)
        if coords:
            try:
                from court_locator.geocode_cache import GeocodeCache
                GeocodeCache().set(address, coords[0], coords[1])
            except Exception:
                pass
            return GeocodeResult(
                lat=coords[0], lon=coords[1],
                confidence="low",
                source="fallback",
                normalized_address=address,
                needs_manual_review=True,
                processing_level="manual",
            )
        return None

    def _dadata_geocode(self, address: str) -> Optional[Tuple[float, float]]:
        """DaData suggest/address как fallback после Yandex."""
        try:
            from court_locator.parser_bridge import dadata_geocode_address

            r = dadata_geocode_address(address, token=config.DADATA_TOKEN)
            if r and r.get("lat") is not None and r.get("lon") is not None:
                return (float(r["lat"]), float(r["lon"]))
        except Exception as e:
            _logger.warning("_dadata_geocode failed: %s", redact_secrets(str(e)))
        return None

    def _yandex_geocode(self, address: str) -> Optional[Tuple[float, float]]:
        try:
            import requests
            url = "https://geocode-maps.yandex.ru/1.x/"
            params = {"apikey": self.api_key, "geocode": address, "format": "json", "results": 1}
            r = requests.get(url, params=params, timeout=config.GEOCODE_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            members = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
            if not members:
                return None
            pos = members[0].get("GeoObject", {}).get("Point", {}).get("pos")
            if not pos:
                return None
            lon, lat = map(float, pos.split())
            return (lat, lon)
        except Exception as e:
            _logger.warning("_yandex_geocode failed: %s", redact_secrets(str(e)))
            # Прямой fallback на DaData при 403/лимите и т.д. (не только в multi_geocoder)
            if config.DADATA_TOKEN:
                dd = self._dadata_geocode(address)
                if dd:
                    return dd
            return None

    def _nominatim_geocode(self, address: str) -> Optional[Tuple[float, float]]:
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="court_locator_parser")
            location = geolocator.geocode(address, timeout=config.GEOCODE_TIMEOUT)
            if location:
                return (location.latitude, location.longitude)
        except Exception as e:
            _logger.warning("_nominatim_geocode failed: %s", redact_secrets(str(e)))
        return None

    def reverse_geocode_open(self, lat: float, lon: float) -> Optional[dict]:
        """
        Обратное геокодирование без ключа Яндекса (Nominatim / OSM), language=ru.
        Нужно для шага «район + регион → БД», когда YANDEX_GEO_KEY не задан.
        """
        try:
            from geopy.geocoders import Nominatim

            geolocator = Nominatim(user_agent="court_locator_parser")
            loc = geolocator.reverse(
                f"{lat}, {lon}",
                language="ru",
                timeout=config.GEOCODE_TIMEOUT,
            )
            if not loc or not getattr(loc, "raw", None):
                return None
            ad = loc.raw.get("address") or {}
            state = (ad.get("state") or ad.get("province") or "").strip()
            city = (
                ad.get("city")
                or ad.get("town")
                or ad.get("village")
                or ad.get("municipality")
                or ""
            )
            city = str(city).strip()
            county = (ad.get("county") or "").strip()
            region = _normalize_region_for_courts(state or None)
            if not region:
                return None
            district = county or city or None
            return {
                "region": region,
                "district": district,
                "locality": city or None,
                "address": getattr(loc, "address", None) or "",
            }
        except Exception as e:
            _logger.warning("reverse_geocode_open failed: %s", redact_secrets(str(e)))
            return None

    def _reverse_geocode_yandex(self, lat: float, lon: float) -> Optional[dict]:
        """Yandex reverse; при 403/лимите — None (далее вызывается DaData)."""
        if not self.api_key:
            return None
        try:
            import requests

            url = "https://geocode-maps.yandex.ru/1.x/"
            params = {
                "apikey": self.api_key,
                "geocode": "%s,%s" % (lon, lat),
                "format": "json",
                "results": 1,
                "kind": "house",
            }
            r = requests.get(url, params=params, timeout=config.GEOCODE_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            members = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
            if not members:
                return None
            obj = members[0].get("GeoObject", {})
            addr = obj.get("metaDataProperty", {}).get("GeocoderMetaData", {}).get("Address", {})
            if not isinstance(addr, dict):
                return None
            components = addr.get("Components") or []
            region = None
            district = None
            locality_name = None
            for c in components:
                if not isinstance(c, dict):
                    continue
                kind = (c.get("kind") or "").strip()
                name = (c.get("name") or "").strip()
                if kind == "region" or "область" in name or "край" in name or "Республика" in name:
                    region = name
                if kind == "locality" or kind == "area":
                    locality_name = name
                if kind == "district" or "район" in name.lower():
                    district = name.replace(" район", "").strip() or name
            region = _normalize_region_for_courts(region or locality_name)
            return {"region": region, "district": district, "address": addr.get("formatted") or ""}
        except Exception as e:
            _logger.warning("reverse_geocode yandex failed: %s", redact_secrets(str(e)))
            return None

    def _reverse_geocode_dadata(self, lat: float, lon: float) -> Optional[dict]:
        """DaData geolocate — обязательный fallback при ошибке Yandex (403 и т.д.)."""
        if not (config.DADATA_TOKEN or "").strip():
            return None
        try:
            from court_locator.parser_bridge import dadata_geolocate_address

            raw = dadata_geolocate_address(lat, lon, token=config.DADATA_TOKEN)
            if not raw:
                return None
            reg = (raw.get("region") or "").strip()
            dist = raw.get("district")
            if dist:
                dist = str(dist).replace(" район", "").strip() or dist
            locality = raw.get("locality")
            region = _normalize_region_for_courts(reg or locality)
            if not region:
                return None
            return {
                "region": region,
                "district": dist,
                "locality": locality,
                "address": raw.get("formatted") or "",
            }
        except Exception as e:
            _logger.warning("reverse_geocode dadata failed: %s", redact_secrets(str(e)))
            return None

    def reverse_geocode(self, lat: float, lon: float) -> Optional[dict]:
        """
        Обратное геокодирование: (lat, lon) → region, district (для БД по району).
        Сначала Yandex (если есть ключ), при сбое или 403 — DaData (если есть DADATA_TOKEN).
        """
        y = self._reverse_geocode_yandex(lat, lon)
        if y and (y.get("region") or "").strip():
            return y
        d = self._reverse_geocode_dadata(lat, lon)
        if d and (d.get("region") or "").strip():
            return d
        return None
