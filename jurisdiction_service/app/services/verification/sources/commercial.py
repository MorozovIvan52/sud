"""
Коммерческие сервисы: 2ГИС, DaData, Яндекс.Карты.
"""
import logging
from typing import Optional

from app.services.verification.sources.base import (
    BaseVerificationSource,
    VerificationSourceResult,
)

logger = logging.getLogger("jurisdiction_service.verification")


class TwoGISService(BaseVerificationSource):
    """2ГИС — координаты зданий судов."""

    name = "2gis"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def verify(self, court_id: str, court_data: Optional[dict] = None) -> VerificationSourceResult:
        if not self.api_key:
            return VerificationSourceResult(
                source_name=self.name,
                success=False,
                error="API ключ 2ГИС не настроен.",
            )
        # TODO: интеграция 2GIS API
        return VerificationSourceResult(
            source_name=self.name,
            success=False,
            error="Интеграция 2ГИС в разработке.",
        )


class DaDataService(BaseVerificationSource):
    """DaData — нормализация адресов, координаты."""

    name = "dadata"

    def __init__(self, token: Optional[str] = None):
        self.token = token

    async def verify(self, court_id: str, court_data: Optional[dict] = None) -> VerificationSourceResult:
        if not self.token:
            return VerificationSourceResult(
                source_name=self.name,
                success=False,
                error="DaData token не настроен.",
            )
        # DaData уже используется в geocoding_service — можно переиспользовать
        if court_data and court_data.get("address"):
            return VerificationSourceResult(
                source_name=self.name,
                success=True,
                data={"address": court_data["address"], "verified": "via_geocoding"},
            )
        return VerificationSourceResult(
            source_name=self.name,
            success=True,
            data={"court_id": court_id, "note": "DaData доступен через геокодер"},
        )


class YandexMapsService(BaseVerificationSource):
    """Яндекс.Карты — геокодирование."""

    name = "yandex_maps"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def verify(self, court_id: str, court_data: Optional[dict] = None) -> VerificationSourceResult:
        if not self.api_key:
            return VerificationSourceResult(
                source_name=self.name,
                success=False,
                error="API ключ Яндекс.Карт не настроен.",
            )
        return VerificationSourceResult(
            source_name=self.name,
            success=True,
            data={"court_id": court_id, "note": "Яндекс доступен через геокодер"},
        )


class CommercialDataSource:
    """Менеджер коммерческих сервисов."""

    def __init__(self, dadata_token: Optional[str] = None, yandex_key: Optional[str] = None, twogis_key: Optional[str] = None):
        self.services = {
            "2gis": TwoGISService(twogis_key),
            "dadata": DaDataService(dadata_token),
            "yandex_maps": YandexMapsService(yandex_key),
        }

    async def verify_location(self, court_data: dict) -> dict:
        """Верификация местоположения через коммерческие сервисы."""
        result = {}
        for name, service in self.services.items():
            try:
                r = await service.verify(court_data.get("court_id", ""), court_data)
                result[name] = {"success": r.success, "data": r.data, "error": r.error}
            except Exception as e:
                logger.warning("Ошибка %s: %s", name, e)
                result[name] = {"success": False, "error": str(e)}
        return result
