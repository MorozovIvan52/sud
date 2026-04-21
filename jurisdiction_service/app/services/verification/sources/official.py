"""
Официальные источники: ГАС Правосудие, ФССП, НСПД, Кадастр.
Заглушки — API требуют регистрации/доступа.
"""
import logging
from typing import Optional

from app.services.verification.sources.base import (
    BaseVerificationSource,
    VerificationSourceResult,
)

logger = logging.getLogger("jurisdiction_service.verification")


class GASRightJusticeAPI(BaseVerificationSource):
    """ГАС «Правосудие» — официальные данные о подсудности."""

    name = "gas_pravosudie"

    async def verify(self, court_id: str, court_data: Optional[dict] = None) -> VerificationSourceResult:
        return VerificationSourceResult(
            source_name=self.name,
            success=False,
            error="API ГАС Правосудие требует регистрации. Интеграция в разработке.",
        )


class FSSPAPI(BaseVerificationSource):
    """Портал ФССП — зоны ответственности приставов."""

    name = "fssp_portal"

    async def verify(self, court_id: str, court_data: Optional[dict] = None) -> VerificationSourceResult:
        return VerificationSourceResult(
            source_name=self.name,
            success=False,
            error="API ФССП требует интеграции. Заглушка.",
        )


class NSPDAPI(BaseVerificationSource):
    """Национальная система пространственных данных."""

    name = "nspd"

    async def verify(self, court_id: str, court_data: Optional[dict] = None) -> VerificationSourceResult:
        return VerificationSourceResult(
            source_name=self.name,
            success=False,
            error="НСПД — кадастровые данные. Интеграция в разработке.",
        )


class KadastrAPI(BaseVerificationSource):
    """Публичная кадастровая карта."""

    name = "kadastr"

    async def verify(self, court_id: str, court_data: Optional[dict] = None) -> VerificationSourceResult:
        return VerificationSourceResult(
            source_name=self.name,
            success=False,
            error="API кадастровой карты. Интеграция в разработке.",
        )


class OfficialDataSource:
    """Менеджер официальных источников верификации."""

    def __init__(self):
        self.sources = {
            "gas_pravosudie": GASRightJusticeAPI(),
            "fssp_portal": FSSPAPI(),
            "nspd": NSPDAPI(),
            "kadastr": KadastrAPI(),
        }

    async def verify_boundaries(self, court_id: str, court_data: Optional[dict] = None) -> dict:
        """Запуск верификации по всем официальным источникам."""
        results = {}
        for key, source in self.sources.items():
            try:
                r = await source.verify(court_id, court_data)
                results[key] = {"success": r.success, "data": r.data, "error": r.error}
            except Exception as e:
                logger.warning("Ошибка источника %s: %s", key, e)
                results[key] = {"success": False, "error": str(e)}
        return results
