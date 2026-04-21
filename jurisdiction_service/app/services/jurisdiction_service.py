"""
Основная бизнес-логика определения подсудности.
PostGIS ST_Within: gist.github.com/Miron-Anosov, postgis.net/docs
ГПК РФ ст. 28-30: axiomjdk.ru
"""
from datetime import date
from typing import Optional

from geoalchemy2.functions import ST_MakePoint, ST_SetSRID, ST_Within
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jurisdiction import CourtDistrict
from app.core.exceptions import CourtNotFoundError
from app.services.address_normalizer import AddressNormalizer
from app.services.geocoding_service import GeocodingService


class JurisdictionService:
    """
    Определение суда по адресу или координатам.
    Координирует нормализатор и геокодер, выполняет PostGIS-запросы.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.normalizer = AddressNormalizer()
        self.geocoder = GeocodingService()

    async def determine_by_address(
        self,
        address: str,
        court_type: Optional[str] = None,
    ) -> dict:
        """
        Определение суда по адресу.
        1. Нормализация адреса
        2. Геокодирование
        3. Поиск суда по координатам
        """
        normalized = self.normalizer.normalize_with_fias(address, self.geocoder.settings.dadata_token)
        lat, lon, provider = await self.geocoder.geocode(normalized)
        return await self._find_court_by_coordinates(lat, lon, court_type, geocode_provider=provider)

    async def determine_by_coordinates(
        self,
        latitude: float,
        longitude: float,
        court_type: Optional[str] = None,
    ) -> dict:
        """Определение суда по координатам."""
        return await self._find_court_by_coordinates(latitude, longitude, court_type)

    async def _find_court_by_coordinates(
        self,
        latitude: float,
        longitude: float,
        court_type: Optional[str] = None,
        geocode_provider: Optional[str] = None,
    ) -> dict:
        """
        Поиск судебного участка, содержащего точку (ST_Within).
        Фильтрация по court_type и актуальности границ (valid_from/valid_to).
        """
        today = date.today()
        point = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)

        conditions = [
            ST_Within(point, CourtDistrict.geometry),
            CourtDistrict.geometry.isnot(None),
            or_(
                CourtDistrict.valid_from.is_(None),
                CourtDistrict.valid_from <= today,
            ),
            or_(
                CourtDistrict.valid_to.is_(None),
                CourtDistrict.valid_to >= today,
            ),
        ]
        if court_type:
            conditions.append(CourtDistrict.court_type == court_type)

        query = select(CourtDistrict).where(and_(*conditions)).limit(1)
        result = await self.db.execute(query)
        row = result.scalar_one_or_none()

        if row is None:
            raise CourtNotFoundError(
                "Суд не найден для заданных координат",
                lat=latitude,
                lon=longitude,
            )

        return {
            "court_code": row.court_code,
            "court_name": row.court_name,
            "court_type": row.court_type,
            "address": row.address,
            "gpk_article": "ст. 28 ГПК РФ",
            "source": "postgis",
            "geocode_provider": geocode_provider,
        }
