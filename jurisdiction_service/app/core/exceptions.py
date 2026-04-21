"""
Кастомные исключения для Jurisdiction Service.
Обработка в FastAPI: codelab.pro, fastapi.tiangolo.com
"""
from typing import Any, Optional


class JurisdictionError(Exception):
    """Базовое исключение сервиса подсудности."""

    def __init__(self, message: str, code: str = "JURISDICTION_ERROR", details: Optional[dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


class AddressNotFoundError(JurisdictionError):
    """Адрес не найден при геокодировании."""

    def __init__(self, message: str = "Адрес не найден", address: Optional[str] = None):
        super().__init__(message, "ADDRESS_NOT_FOUND", {"address": address} if address else {})


class CourtNotFoundError(JurisdictionError):
    """Суд не найден для заданных координат."""

    def __init__(self, message: str = "Суд не найден", lat: Optional[float] = None, lon: Optional[float] = None):
        super().__init__(message, "COURT_NOT_FOUND", {"lat": lat, "lon": lon} if lat is not None else {})


class GeocodingError(JurisdictionError):
    """Ошибка геокодирования."""

    def __init__(self, message: str = "Ошибка геокодирования", provider: Optional[str] = None):
        super().__init__(message, "GEOCODING_ERROR", {"provider": provider} if provider else {})


class ValidationError(JurisdictionError):
    """Ошибка валидации входных данных."""

    def __init__(self, message: str = "Неверные данные", field: Optional[str] = None):
        super().__init__(message, "VALIDATION_ERROR", {"field": field} if field else {})
