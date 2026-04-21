"""
Схемы для краудсорсинговых отчётов о верификации подсудности.
"""
from typing import Optional

from pydantic import BaseModel, Field


class ReportErrorRequest(BaseModel):
    """Запрос на сообщение об ошибке определения подсудности."""

    address: Optional[str] = Field(None, description="Адрес, по которому искали суд")
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="Широта (WGS84)")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="Долгота (WGS84)")
    reported_court: str = Field(..., min_length=1, max_length=500, description="Суд, который вернула система")
    suggested_court: Optional[str] = Field(None, max_length=500, description="Правильный суд по мнению пользователя")
    comment: Optional[str] = Field(None, max_length=2000, description="Комментарий")

    class Config:
        json_schema_extra = {
            "example": {
                "address": "г. Москва, ул. Тверская, 15",
                "latitude": 55.7558,
                "longitude": 37.6173,
                "reported_court": "Мировой судья участка № 123",
                "suggested_court": "Мировой судья участка № 124",
                "comment": "Адрес относится к участку 124",
            }
        }


class ReportErrorResponse(BaseModel):
    """Ответ на успешную отправку отчёта."""

    success: bool = True
    report_id: str
    message: str = "Спасибо за обратную связь. Отчёт принят на рассмотрение."
