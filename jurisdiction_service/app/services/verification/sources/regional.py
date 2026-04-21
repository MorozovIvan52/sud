"""
Региональные источники: сайты судов, администраций субъектов РФ.
"""
import logging
from typing import Optional

from app.services.verification.sources.base import (
    BaseVerificationSource,
    VerificationSourceResult,
)

logger = logging.getLogger("jurisdiction_service.verification")


class RegionalPortal(BaseVerificationSource):
    """Портал региона (суд, администрация)."""

    def __init__(self, region_code: str, portal_url: str):
        self.name = f"regional_{region_code}"
        self.region_code = region_code
        self.portal_url = portal_url

    async def verify(self, court_id: str, court_data: Optional[dict] = None) -> VerificationSourceResult:
        # Парсинг региональных порталов требует индивидуальной реализации
        return VerificationSourceResult(
            source_name=self.name,
            success=False,
            error=f"Парсер {self.portal_url} в разработке.",
        )


class RegionalDataSource:
    """Менеджер региональных порталов."""

    def __init__(self):
        self.regional_ports: dict[str, RegionalPortal] = {}

    def add_regional_portal(self, region_code: str, portal_url: str) -> None:
        """Добавить региональный портал."""
        self.regional_ports[region_code] = RegionalPortal(region_code, portal_url)

    async def fetch_regional_data(self, region_code: str, court_id: Optional[str] = None) -> Optional[dict]:
        """Получить данные из регионального портала."""
        if region_code not in self.regional_ports:
            return None
        portal = self.regional_ports[region_code]
        result = await portal.verify(court_id or "", None)
        return {"source": result.source_name, "success": result.success, "data": result.data, "error": result.error}
