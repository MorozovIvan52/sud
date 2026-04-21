"""
Топологическая проверка геометрии судебных участков.
Проверка целостности, перекрытий, разрывов.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("jurisdiction_service.verification")


@dataclass
class TopologyResult:
    """Результат топологической проверки."""

    is_valid: bool
    overlaps: list[dict] = field(default_factory=list)
    gaps: list[dict] = field(default_factory=list)
    self_intersections: bool = False
    errors: list[str] = field(default_factory=list)


class BoundaryChecker:
    """
    Топологический анализ полигонов судебных участков.
    Использует PostGIS: ST_IsValid, ST_MakeValid, проверка перекрытий.
    """

    def __init__(self, db_session=None):
        self.db = db_session

    async def check_integrity(self, geometry_wkt: Optional[str] = None, court_id: Optional[str] = None) -> TopologyResult:
        """
        Проверка целостности геометрии.
        geometry_wkt — WKT-строка полигона, court_id — для запроса из БД.
        """
        result = TopologyResult(is_valid=True)
        if not self.db:
            result.errors.append("Сессия БД не передана")
            result.is_valid = False
            return result

        try:
            from sqlalchemy import text
            if court_id:
                row = await self.db.execute(
                    text("""
                        SELECT id, court_code, ST_IsValid(geometry) as valid,
                               ST_IsValidReason(geometry) as reason
                        FROM court_districts WHERE id = :id
                    """),
                    {"id": court_id},
                )
                r = row.fetchone()
                if r and not r.valid:
                    result.is_valid = False
                    result.self_intersections = True
                    result.errors.append(f"Самопересечение: {r.reason or 'unknown'}")
            elif geometry_wkt:
                row = await self.db.execute(
                    text("SELECT ST_IsValid(ST_GeomFromText(:wkt, 4326)) as valid"),
                    {"wkt": geometry_wkt},
                )
                r = row.fetchone()
                if r and not r.valid:
                    result.is_valid = False
                    result.self_intersections = True
                    result.errors.append("Геометрия содержит самопересечения")
        except Exception as e:
            logger.exception("Ошибка проверки целостности")
            result.is_valid = False
            result.errors.append(str(e))
        return result

    async def check_overlaps(self, court_id: Optional[str] = None, region_filter: Optional[str] = None) -> TopologyResult:
        """
        Поиск перекрытий между полигонами участков.
        """
        result = TopologyResult(is_valid=True)
        if not self.db:
            result.errors.append("Сессия БД не передана")
            return result

        try:
            from sqlalchemy import text
            sql = """
                SELECT a.id as id1, a.court_code as code1, b.id as id2, b.court_code as code2,
                       ST_Area(ST_Intersection(a.geometry, b.geometry)) as overlap_area
                FROM court_districts a
                JOIN court_districts b ON a.id < b.id
                WHERE a.geometry IS NOT NULL AND b.geometry IS NOT NULL
                  AND ST_Intersects(a.geometry, b.geometry)
                  AND ST_Area(ST_Intersection(a.geometry, b.geometry)) > 0.0000001
            """
            params = {}
            if court_id:
                sql += " AND (a.id = :court_id OR b.id = :court_id)"
                params["court_id"] = court_id
            row = await self.db.execute(text(sql), params)
            overlaps = []
            for r in row.fetchall():
                overlaps.append({
                    "court_1": r.code1,
                    "court_2": r.code2,
                    "overlap_area_sq_deg": float(r.overlap_area) if r.overlap_area else 0,
                })
                result.overlaps = overlaps
                result.is_valid = len(overlaps) == 0
        except Exception as e:
            logger.exception("Ошибка проверки перекрытий")
            result.errors.append(str(e))
        return result

    async def check_gaps(self, region_filter: Optional[str] = None) -> TopologyResult:
        """
        Проверка на разрывы (дыры) между полигонами.
        Упрощённая проверка: участки без геометрии.
        """
        result = TopologyResult(is_valid=True)
        if not self.db:
            result.errors.append("Сессия БД не передана")
            return result

        try:
            from sqlalchemy import text
            sql = """
                SELECT court_code, court_name FROM court_districts
                WHERE geometry IS NULL
            """
            params = {}
            row = await self.db.execute(text(sql), params)
            gaps = [{"court_code": r.court_code, "court_name": r.court_name} for r in row.fetchall()]
            result.gaps = gaps
            result.is_valid = len(gaps) == 0
        except Exception as e:
            logger.exception("Ошибка проверки разрывов")
            result.errors.append(str(e))
        return result
