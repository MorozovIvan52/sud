# geo_court_parser.py — определение мирового суда по адресу через GPS (адрес → геокод → ближайший суд в радиусе).
# 0 капчи, легальные API карт, оффлайн БД с координатами.

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any

import requests

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
COURTS_SQLITE = SCRIPT_DIR / "courts.sqlite"
COURTS_GEO_SQLITE = SCRIPT_DIR / "courts_geo.sqlite"

# Коды паспорта → регион (фрагмент; полный в passport_parser / generate_courts_db)
PASSPORT_REGION_CODES = {
    "770": "Москва",
    "771": "Московская область",
    "450": "Москва",
    "451": "Москва",
    "504": "Санкт-Петербург",
    "780": "Санкт-Петербург",
    "773": "Краснодарский край",
    "502": "Свердловская область",
}


@dataclass
class GeoCourtResult:
    court_name: str
    court_address: str
    gps_coords: Tuple[float, float]
    distance_km: float
    section_num: int
    region: str
    confidence: float = 0.95
    court_index: str = ""


def _parse_coords(coord_str: str) -> Optional[Tuple[float, float]]:
    """Парсит '55.7558,37.6176' или '55.7558, 37.6176' в (lat, lon)."""
    if not coord_str or not isinstance(coord_str, str):
        return None
    parts = coord_str.replace(" ", "").split(",")
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return (lat, lon)
    except ValueError:
        pass
    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в км (формула Haversine)."""
    try:
        from math import radians, sin, cos, sqrt, atan2
        R = 6371
        lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c
    except Exception:
        return 99999.0


class YandexGeoParser:
    """Адрес → GPS (Yandex или Nominatim) → ближайший мировой суд из БД."""

    def __init__(self, api_key: str = None):
        os_env = __import__("os").environ
        self.api_key = (
            (api_key or "").strip()
            or os_env.get("YANDEX_GEO_KEY")
            or os_env.get("YANDEX_GEOCODER_API_KEY")
            or os_env.get("YANDEX_LOCATOR_API_KEY")
            or os_env.get("YANDEX_LOCATOR_KEY")
            or ""
        ).strip()
        self._courts_rows: List[Dict[str, Any]] = []
        self._load_courts_db()

    def _load_courts_db(self):
        """Загружает суды с координатами: сначала courts_geo.sqlite, иначе courts.sqlite с полем coordinates."""
        self._courts_rows = []

        if COURTS_GEO_SQLITE.exists():
            try:
                conn = sqlite3.connect(COURTS_GEO_SQLITE)
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT name, address, lat, lon, region, section FROM courts_geo WHERE lat IS NOT NULL AND lon IS NOT NULL"
                )
                for row in cur.fetchall():
                    r = dict(row)
                    self._courts_rows.append({
                        "name": r.get("name", ""),
                        "address": r.get("address", ""),
                        "lat": float(r["lat"]),
                        "lon": float(r["lon"]),
                        "region": r.get("region", ""),
                        "section": int(r["section"]) if r.get("section") is not None else 0,
                    })
                conn.close()
                if self._courts_rows:
                    logger.info("Загружено судов с GPS (courts_geo): %s", len(self._courts_rows))
                    return
            except Exception as e:
                logger.warning("courts_geo.sqlite: %s", e)

        if COURTS_SQLITE.exists():
            try:
                conn = sqlite3.connect(COURTS_SQLITE)
                conn.row_factory = sqlite3.Row
                cur = conn.execute("SELECT court_name, address, coordinates, region, section_num, postal_index FROM courts")
                for row in cur.fetchall():
                    r = dict(row)
                    coords = _parse_coords(r.get("coordinates") or "")
                    if not coords:
                        continue
                    lat, lon = coords
                    self._courts_rows.append({
                        "name": r.get("court_name", ""),
                        "address": r.get("address", ""),
                        "lat": lat,
                        "lon": lon,
                        "region": r.get("region", ""),
                        "section": int(r["section_num"]) if r.get("section_num") is not None else 0,
                        "postal_index": r.get("postal_index", ""),
                    })
                conn.close()
                if self._courts_rows:
                    logger.info("Загружено судов с GPS (courts): %s", len(self._courts_rows))
                    return
            except Exception as e:
                logger.warning("courts.sqlite: %s", e)

        logger.warning("Нет судов с координатами. Создайте courts_geo.sqlite или заполните coordinates в courts.")
        self._courts_rows = []

    def address_to_gps(self, address: str) -> Optional[Tuple[float, float]]:
        """Адрес → (lat, lon). Сначала Yandex Geocoder, при отсутствии ключа — Nominatim."""
        address = (address or "").strip()
        if not address:
            return None

        if self.api_key:
            try:
                url = "https://geocode-maps.yandex.ru/1.x/"
                params = {"apikey": self.api_key, "geocode": address, "format": "json", "results": 1}
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                members = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
                if not members:
                    return None
                pos = members[0].get("GeoObject", {}).get("Point", {}).get("pos")
                if not pos:
                    return None
                lon, lat = map(float, pos.split())
                return (lat, lon)
            except Exception as e:
                logger.debug("Yandex Geocoder: %s", e)

        try:
            from geopy.geocoders import Nominatim
            from geopy.exc import GeocoderTimedOut, GeocoderServiceError
            geolocator = Nominatim(user_agent="court_finder_parser")
            location = geolocator.geocode(address, timeout=10)
            if location:
                return (location.latitude, location.longitude)
        except Exception as e:
            logger.debug("Nominatim: %s", e)

        return None

    def find_nearest_court(
        self,
        lat: float,
        lon: float,
        radius_km: float = 5.0,
        only_mirovoy: bool = True,
    ) -> List[GeoCourtResult]:
        """Ближайшие суды в радиусе radius_km. По умолчанию только с «мировой» в названии."""
        candidates = []
        for c in self._courts_rows:
            dist = _haversine_km(lat, lon, c["lat"], c["lon"])
            if dist > radius_km:
                continue
            name = (c.get("name") or "").lower()
            if only_mirovoy and "мировой" not in name:
                continue
            confidence = max(0.5, 1.0 - (dist / radius_km))
            candidates.append(
                GeoCourtResult(
                    court_name=c.get("name", ""),
                    court_address=c.get("address", ""),
                    gps_coords=(c["lat"], c["lon"]),
                    distance_km=round(dist, 2),
                    section_num=c.get("section", 0),
                    region=c.get("region", ""),
                    confidence=round(confidence, 2),
                    court_index=c.get("postal_index", ""),
                )
            )
        return sorted(candidates, key=lambda x: x.distance_km)

    def parse_passport_region(self, passport: str) -> Optional[str]:
        """Регион по коду подразделения паспорта (первые 3 цифры)."""
        if not passport:
            return None
        m = re.search(r"(\d{3})", "".join(c for c in str(passport) if c.isdigit()))
        if m:
            return PASSPORT_REGION_CODES.get(m.group(1))
        return None

    def super_find_court(
        self,
        fio: str,
        address: str,
        passport: str = None,
        radius_km: float = 5.0,
    ) -> Optional[GeoCourtResult]:
        """Адрес → GPS → ближайшие суды в радиусе → фильтр по региону паспорта → лучший результат."""
        gps = self.address_to_gps(address)
        if not gps:
            logger.error("GPS не найден для адреса: %s", address[:50])
            return None

        lat, lon = gps
        logger.info("GPS: %.6f, %.6f", lat, lon)

        courts = self.find_nearest_court(lat, lon, radius_km=radius_km)
        if not courts:
            logger.error("В радиусе %s км суды не найдены", radius_km)
            return None

        if passport:
            region = self.parse_passport_region(passport)
            if region:
                filtered = [c for c in courts if region.lower() in (c.region or "").lower()]
                if filtered:
                    courts = filtered

        best = courts[0]
        logger.info("Найден суд: %s (%.1f км)", best.court_name[:50], best.distance_km)
        return best


def test_geo_parser():
    parser = YandexGeoParser()
    test_cases = [
        {"fio": "Иванов И.И.", "address": "г. Москва, ул. Ленина, д. 15"},
        {"fio": "Петров П.П.", "address": "г. Санкт-Петербург, Невский пр., 10"},
    ]
    results = []
    for case in test_cases:
        result = parser.super_find_court(case["fio"], case["address"])
        if result:
            print(f"Суд: {result.court_name} ({result.distance_km} км)")
            results.append(result)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_geo_parser()
