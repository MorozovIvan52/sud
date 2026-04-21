"""
Верификационный сервис — оркестрация проверок границ судебных участков.
"""
import logging
import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import CourtDistrict
from app.services.verification.boundary_checker import BoundaryChecker
from app.services.verification.data_source_manager import DataSourceManager

logger = logging.getLogger("jurisdiction_service.verification")


class ValidatorService:
    """
    Сервис верификации границ судебных участков.
    Координирует BoundaryChecker, DataSourceManager, сохраняет результаты.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.boundary_checker = BoundaryChecker(db)
        self.data_sources = DataSourceManager()

    async def verify_court(self, court_id: str) -> dict[str, Any]:
        """
        Полная верификация суда: топология + внешние источники.
        """
        start = time.perf_counter()
        result = {
            "court_id": court_id,
            "verification_date": datetime.utcnow().isoformat(),
            "topology": {},
            "sources": {},
            "status": "ok",
            "errors": [],
            "duration_ms": 0,
        }

        # 1. Получить данные суда
        row = await self.db.execute(
            select(CourtDistrict).where(CourtDistrict.id == court_id)
        )
        court = row.scalar_one_or_none()
        if not court:
            result["status"] = "error"
            result["errors"].append("Суд не найден")
            result["duration_ms"] = (time.perf_counter() - start) * 1000
            return result

        court_data = {
            "court_id": court_id,
            "court_code": court.court_code,
            "court_name": court.court_name,
            "address": court.address,
        }

        # 2. Топологическая проверка
        try:
            integrity = await self.boundary_checker.check_integrity(court_id=court_id)
            overlaps = await self.boundary_checker.check_overlaps(court_id=court_id)
            gaps = await self.boundary_checker.check_gaps()
            result["topology"] = {
                "integrity_valid": integrity.is_valid,
                "integrity_errors": integrity.errors,
                "overlaps_count": len(overlaps.overlaps),
                "overlaps": overlaps.overlaps,
                "gaps_count": len(gaps.gaps),
            }
            if not integrity.is_valid or overlaps.overlaps or gaps.gaps:
                result["status"] = "warnings"
        except Exception as e:
            logger.exception("Ошибка топологической проверки")
            result["topology"]["error"] = str(e)
            result["status"] = "error"
            result["errors"].append(str(e))

        # 3. Внешние источники
        try:
            result["sources"] = await self.data_sources.verify_court(court_id, court_data)
        except Exception as e:
            logger.warning("Ошибка источников: %s", e)
            result["sources"] = {"error": str(e)}

        result["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return result

    async def verify_all_courts(self, limit: Optional[int] = None) -> dict[str, Any]:
        """
        Верификация всех судов (для пакетной проверки).
        """
        row = await self.db.execute(
            select(CourtDistrict.id).limit(limit or 1000)
        )
        ids = [r[0] for r in row.fetchall()]
        results = []
        total_ok = 0
        total_warnings = 0
        total_errors = 0
        for cid in ids:
            r = await self.verify_court(cid)
            results.append(r)
            if r["status"] == "ok":
                total_ok += 1
            elif r["status"] == "warnings":
                total_warnings += 1
            else:
                total_errors += 1
        return {
            "total": len(results),
            "ok": total_ok,
            "warnings": total_warnings,
            "errors": total_errors,
            "results": results,
        }
