"""
Pydantic-схемы для API подсудности.
docs.pydantic.dev, habr.com/ru/companies/amvera/articles/851642/
"""
from typing import Optional

from pydantic import BaseModel, Field


class JurisdictionRequestByAddress(BaseModel):
    """Запрос по адресу."""

    address: str = Field(..., min_length=5, description="Адрес для определения подсудности")
    court_type: Optional[str] = Field(None, description="Тип суда: мировой, районный")


class JurisdictionRequestByCoordinates(BaseModel):
    """Запрос по координатам."""

    latitude: float = Field(..., ge=-90, le=90, description="Широта WGS84")
    longitude: float = Field(..., ge=-180, le=180, description="Долгота WGS84")
    court_type: Optional[str] = Field(None, description="Тип суда: мировой, районный")


class JurisdictionResponse(BaseModel):
    """Успешный ответ с данными суда."""

    success: bool = True
    court_code: str
    court_name: str
    court_type: str
    address: Optional[str] = None
    gpk_article: str = "ст. 28 ГПК РФ"
    source: str = "postgis"
    geocode_provider: Optional[str] = None


class JurisdictionErrorResponse(BaseModel):
    """Ответ при ошибке."""

    success: bool = False
    error: str
    code: str
    details: Optional[dict] = None
