"""
Схемы API системы верификации границ.
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class VerificationStartRequest(BaseModel):
    """Запрос на запуск верификации."""

    court_id: str = Field(..., description="ID судебного участка (court_districts.id)")


class VerificationStartResponse(BaseModel):
    """Ответ на запуск верификации."""

    success: bool = True
    court_id: str
    verification_id: Optional[str] = None
    message: str = "Верификация запущена"
    result: Optional[dict[str, Any]] = None


class VerificationResultsResponse(BaseModel):
    """Результаты верификации по суду."""

    court_id: str
    results: list[dict[str, Any]] = Field(default_factory=list)
    latest: Optional[dict[str, Any]] = None


class ManualVerificationRequest(BaseModel):
    """Запрос на ручную верификацию."""

    court_id: str = Field(..., description="ID суда")
    verified_by: str = Field(..., description="Кто проверил (оператор)")
    comment: Optional[str] = Field(None, max_length=2000)
    status: str = Field("verified", description="verified | rejected | needs_review")


class ManualVerificationResponse(BaseModel):
    """Ответ на ручную верификацию."""

    success: bool = True
    result_id: str
    message: str = "Ручная верификация сохранена"
