"""
Настройки из переменных окружения (Pydantic BaseSettings).
См. docs и best practices: habr.com/ru/companies/gnivc/articles/792082/
"""
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация приложения из .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://jurisdiction:jurisdiction_secret@localhost:5432/jurisdiction_db",
        description="PostgreSQL + asyncpg DSN",
    )

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL")

    # JWT
    jwt_secret_key: str = Field(default="change-me-in-production", description="Секрет для JWT")
    jwt_algorithm: str = Field(default="HS256", description="Алгоритм JWT")
    jwt_expire_minutes: int = Field(default=60 * 24, description="Время жизни токена (минуты)")

    # Geocoding
    yandex_geo_key: Optional[str] = Field(default=None, description="Ключ Яндекс.Геокодер")
    yandex_locator_api_key: Optional[str] = Field(default=None, description="Ключ Яндекс Локатор (опционально)")
    dadata_token: Optional[str] = Field(default=None, description="DaData API token")
    twogis_api_key: Optional[str] = Field(default=None, description="2ГИС API ключ (для верификации)")
    geocode_cache_ttl: int = Field(default=30 * 24 * 3600, description="TTL кэша геокодирования (сек), 30 дней")

    # Rate limiting
    rate_limit_requests: int = Field(default=100, description="Лимит запросов на пользователя")
    rate_limit_window: int = Field(default=3600, description="Окно лимита (секунды), 1 час")

    # Logging
    log_level: str = Field(default="INFO", description="Уровень логирования")


@lru_cache
def get_settings() -> Settings:
    """Синглтон настроек."""
    return Settings()
