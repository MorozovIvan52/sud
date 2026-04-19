"""
Сопоставление адреса/координат с мировым судом (docs/jurisdiction_conclusion.md).
0) PostGIS (COURTS_SPATIAL_BACKEND=postgis или COURTS_DB_BACKEND=postgis) — границы судебных участков.
1) Полигоны участков (court_districts) — point-in-polygon (shapely), needs_manual_review при < 50 м до границы.
2) Ближайший суд из БД с координатами (parser/courts.sqlite, courts_geo.sqlite).
3) Регион/район из адреса + get_court_by_district.
4) Опционально DaData API по адресу.
"""
import logging
from typing import Any, Dict, List, Optional

_logger = logging.getLogger("court_locator.court_matcher")

from court_locator import config
from court_locator.database import Database
from court_locator.gps_handler import GPSHandler
from court_locator.address_parser import parse_address
from court_locator.utils import haversine_km, court_row_to_result
from court_locator.law_rules import LawRuleMatcher
from court_locator.log_sanitize import redact_secrets


def _parse_coords(coord_str: str) -> Optional[tuple]:
    """Парсит '55.7558,37.6176' в (lat, lon)."""
    if not coord_str or not isinstance(coord_str, str):
        return None
    parts = coord_str.replace(" ", "").strip().split(",")
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return (lat, lon)
    except ValueError:
        pass
    return None


class CourtMatcher:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.db.init_schema()
        self.gps = GPSHandler()
        self._dadata_available = bool(config.DADATA_TOKEN)
        self._law_matcher = LawRuleMatcher(self.db)

    def find_court_by_coordinates(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        """
        Находит суд по координатам: PostGIS (если доступен) → полигоны SQLite → обратное геокодирование → ближайший суд.
        """
        # 0) PostGIS при явном включении пространственного слоя
        if config.use_postgis_for_spatial_search():
            try:
                from court_locator.postgis_adapter import find_court_by_coordinates_postgis, is_postgis_available
                if is_postgis_available():
                    row = find_court_by_coordinates_postgis(lat, lng)
                    if row:
                        return court_row_to_result(row, "postgis")
            except Exception:
                pass

        # 1) Полигоны участков (shapely; при наличии rtree — быстрый отбор кандидатов O(log n))
        BOUNDARY_NEAR_THRESHOLD_M = 50
        districts = self.db.get_all_districts()
        candidates_to_check = self._spatial_candidates(districts, lng, lat)
        for idx in candidates_to_check:
            d = districts[idx]
            boundaries = d.get("boundaries")
            if not boundaries:
                continue
            dist_m, in_poly = self._point_in_polygon_with_distance(lng, lat, boundaries)
            if in_poly:
                needs_review = dist_m < BOUNDARY_NEAR_THRESHOLD_M
                return court_row_to_result(
                    {
                        "court_name": d.get("court_name") or d.get("district_number"),
                        "address": d.get("address"),
                        "region": d.get("region"),
                        "phone": d.get("phone"),
                        "email": d.get("email") or d.get("court_email"),
                        "schedule": d.get("schedule"),
                        "judge_name": d.get("judge_name"),
                        "section_num": d.get("district_number"),
                    },
                    "court_districts",
                    needs_manual_review=needs_review if needs_review else None,
                )

        # 2) Обратное геокодирование → суд по (регион, район), чтобы не путать районы
        rev = self.gps.reverse_geocode(lat, lng)
        if rev and rev.get("region") and rev.get("district"):
            row = self.db.get_court_by_district(rev["region"], rev["district"])
            if row:
                return court_row_to_result(row, "coordinates_district")

        # 2b) То же без API Яндекса (Nominatim) — иначе при одном только геокоде до точки район не находился
        rev_osm = self.gps.reverse_geocode_open(lat, lng)
        if rev_osm and rev_osm.get("region"):
            reg = rev_osm["region"]
            for dtry in (
                rev_osm.get("district"),
                rev_osm.get("locality"),
            ):
                if not dtry:
                    continue
                row = self.db.get_court_by_district(reg, dtry)
                if row:
                    return court_row_to_result(row, "coordinates_district_osm")

        # 3) Ближайший суд из courts с координатами (только если район не определился)
        courts = self.db.get_courts_with_coordinates()
        candidates = []
        for c in courts:
            coords = _parse_coords(c.get("coordinates") or "")
            if not coords:
                continue
            clat, clon = coords
            dist = haversine_km(lat, lng, clat, clon)
            if dist <= config.NEAREST_RADIUS_KM:
                candidates.append((dist, c))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return court_row_to_result(candidates[0][1], "courts_nearest")

        # 3b) courts_geo.sqlite при наличии
        try:
            import sqlite3
            from pathlib import Path
            geo_path = Path(config.COURTS_GEO_DB_PATH)
            if geo_path.exists():
                conn = sqlite3.connect(str(geo_path))
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT name, address, lat, lon, region, section FROM courts_geo WHERE lat IS NOT NULL AND lon IS NOT NULL"
                )
                for row in cur.fetchall():
                    r = dict(row)
                    dist = haversine_km(lat, lng, float(r["lat"]), float(r["lon"]))
                    if dist <= config.NEAREST_RADIUS_KM:
                        candidates.append((dist, {
                            "court_name": r.get("name"),
                            "address": r.get("address"),
                            "region": r.get("region"),
                            "section_num": r.get("section"),
                        }))
                conn.close()
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    return court_row_to_result(candidates[0][1], "courts_geo")
        except Exception:
            pass

        return None

    def _spatial_candidates(self, districts: List[Dict], lng: float, lat: float) -> List[int]:
        """
        Индексы участков-кандидатов, содержащих точку (lng, lat).
        При установленном rtree используется R-tree индекс (O(log n)), иначе проверяем все.
        """
        try:
            from shapely.geometry import Point, Polygon
            from rtree import index
            idx = index.Index()
            for i, d in enumerate(districts):
                b = d.get("boundaries")
                if not b:
                    continue
                try:
                    if isinstance(b, list) and b:
                        ring = b[0] if isinstance(b[0], (list, tuple)) and len(b[0]) > 2 else b
                        poly = Polygon(ring)
                    else:
                        continue
                    bounds = poly.bounds
                    idx.insert(i, (bounds[0], bounds[1], bounds[2], bounds[3]))
                except Exception:
                    continue
            return list(idx.intersection((lng, lat, lng, lat)))
        except ImportError:
            pass
        return list(range(len(districts)))

    def _point_in_polygon(self, lng: float, lat: float, boundaries: Any) -> bool:
        """Проверка точки в полигоне (shapely). boundaries — GeoJSON координаты или список [lng,lat] колец."""
        _, in_poly = self._point_in_polygon_with_distance(lng, lat, boundaries)
        return in_poly

    def _point_in_polygon_with_distance(
        self, lng: float, lat: float, boundaries: Any
    ) -> tuple[float, bool]:
        """
        Проверка точки в полигоне + расстояние до границы (м).
        Возвращает (distance_to_boundary_m, in_polygon).
        """
        try:
            from shapely.geometry import Point, shape
            point = Point(lng, lat)
            if isinstance(boundaries, dict):
                geom = shape(boundaries)
            elif isinstance(boundaries, list):
                if boundaries and isinstance(boundaries[0], (list, tuple)):
                    from shapely.geometry import Polygon
                    geom = Polygon(boundaries[0])
                else:
                    return (float("inf"), False)
            else:
                return (float("inf"), False)
            in_poly = geom.contains(point)
            dist_deg = geom.boundary.distance(point)
            dist_m = dist_deg * 111320 if dist_deg < 0.1 else float("inf")
            return (dist_m, in_poly)
        except Exception:
            return (float("inf"), False)

    def find_court_by_address(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Находит суд по адресу. Приоритет: район из адреса (как в parser) → DaData → геокодер + координаты.
        Чтобы результат совпадал с parser/jurisdiction — сначала поиск по (регион, район).
        """
        address = (address or "").strip()
        if not address:
            return None

        # 0) Правила из законов (текстовые диапазоны улиц/домов)
        rule_hit = self._law_matcher.match(address)
        if rule_hit:
            return rule_hit

        # 1) Регион/район из адреса + БД (тот же порядок, что в parser/jurisdiction — суд по району)
        parsed = parse_address(address)
        region = parsed.get("region")
        district = parsed.get("district")
        if region and district:
            row = self.db.get_court_by_district(region, district)
            if row:
                return court_row_to_result(row, "address_district")

        # 2) DaData, если доступен
        if self._dadata_available:
            try:
                from court_locator.parser_bridge import dadata_find_court_by_address

                row = dadata_find_court_by_address(
                    address, region=region, token=config.DADATA_TOKEN
                )
                if row and row.get("court_name"):
                    return court_row_to_result(row, "dadata")
            except Exception as e:
                _logger.warning("find_court_by_address DaData: %s", redact_secrets(str(e)))

        # 3) Геокодер → по координатам (многоисточниковая верификация, confidence, needs_manual_review)
        gr = self.gps.geocode_with_verification(address)
        if gr:
            court = self.find_court_by_coordinates(gr.lat, gr.lon)
            if court:
                court["confidence"] = gr.confidence
                court["needs_manual_review"] = court.get("needs_manual_review", False) or gr.needs_manual_review
                court["processing_level"] = gr.processing_level
                court["geocode_source"] = gr.source
            try:
                from court_locator.geocode_quality_monitor import get_monitor
                get_monitor().log(
                    address=address,
                    region=court.get("region") if court else None,
                    source=gr.source,
                    confidence=gr.confidence,
                    lat=gr.lat,
                    lon=gr.lon,
                    court_found=bool(court),
                    needs_manual_review=gr.needs_manual_review or (court.get("needs_manual_review") if court else False),
                    processing_level=gr.processing_level,
                )
            except Exception:
                pass
            if court:
                return court

        return None
