"""
Менеджер источников данных для верификации.
Объединяет официальные, региональные и коммерческие источники.
"""
import logging
from typing import Any, Optional

from app.core.config import get_settings
from app.services.verification.sources.official import OfficialDataSource
from app.services.verification.sources.regional import RegionalDataSource
from app.services.verification.sources.commercial import CommercialDataSource

logger = logging.getLogger("jurisdiction_service.verification")


class DataSourceManager:
    """
    Централизованное управление источниками верификации.
    """

    def __init__(self):
        settings = get_settings()
        self.official = OfficialDataSource()
        self.regional = RegionalDataSource()
        self.commercial = CommercialDataSource(
            dadata_token=settings.dadata_token,
            yandex_key=settings.yandex_geo_key,
            twogis_key=settings.twogis_api_key,
        )

    async def verify_court(self, court_id: str, court_data: Optional[dict] = None) -> dict[str, Any]:
        """
        Запуск верификации по всем доступным источникам.
        Возвращает агрегированные результаты.
        """
        results = {
            "court_id": court_id,
            "official": await self.official.verify_boundaries(court_id, court_data),
            "commercial": await self.commercial.verify_location(
                court_data or {"court_id": court_id}
            ),
        }
        if court_data and court_data.get("region_code"):
            regional = await self.regional.fetch_regional_data(
                court_data["region_code"], court_id
            )
            results["regional"] = regional or {}
        else:
            results["regional"] = {}
        return results
