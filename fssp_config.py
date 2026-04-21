"""
Конфигурация ФССП из окружения (.env).

Инструкция: docs/fssp_legal_integration.md.
Переменные: FSSP_API_KEY, FSSP_API_BASE, FSSP_TIMEOUT, FSSP_MAX_REQUESTS_PER_MINUTE,
FSSP_API_MODE, FSSP_CERT_PATH и др.
"""
import os
from typing import Optional


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class FSSPConfig:
    """Единая конфигурация ФССП из .env (официальный API)."""

    MODE = os.getenv("FSSP_API_MODE", "gosuslugi")
    BASE_URL = (os.getenv("FSSP_BASE_URL") or os.getenv("FSSP_API_BASE") or "https://api.fssp.gov.ru").rstrip("/")
    API_KEY = (os.getenv("FSSP_API_KEY") or os.getenv("FSSP_TOKEN") or "").strip() or None
    CERT_PATH = (os.getenv("FSSP_CERT_PATH") or "").strip() or None
    TIMEOUT = _int_env("FSSP_TIMEOUT", 30)
    MAX_REQUESTS_PER_MINUTE = _int_env("FSSP_MAX_REQUESTS_PER_MINUTE", 10)
    MIN_DELAY_SEC = _float_env("FSSP_MIN_DELAY_SEC", 60.0 / 10)  # 6 сек при 10 req/min

    @classmethod
    def get_headers(cls) -> dict:
        """Заголовки для запросов к API ФССП."""
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if cls.API_KEY:
            headers["Authorization"] = f"Bearer {cls.API_KEY}"
        return headers

    @classmethod
    def is_valid_config(cls) -> bool:
        """Проверка минимальной конфигурации (BASE_URL обязателен; для СМЭВ — сертификат)."""
        if not cls.BASE_URL:
            raise ValueError("FSSP_BASE_URL / FSSP_API_BASE не задан в конфигурации")
        if cls.MODE == "smev" and not cls.CERT_PATH:
            raise ValueError("Для режима СМЭВ требуется сертификат (FSSP_CERT_PATH)")
        return True

    @classmethod
    def get_timeout(cls) -> int:
        """Таймаут запроса в секундах (для fssp_client)."""
        return cls.TIMEOUT


def get_fssp_timeout() -> int:
    """Таймаут по умолчанию для клиента ФССП."""
    return FSSPConfig.get_timeout()
