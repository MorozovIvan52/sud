"""
Базовый класс источника верификации.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class VerificationSourceResult:
    """Результат проверки от одного источника."""

    source_name: str
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


class BaseVerificationSource(ABC):
    """Абстрактный источник верификации."""

    name: str = "base"

    @abstractmethod
    async def verify(self, court_id: str, court_data: Optional[dict] = None) -> VerificationSourceResult:
        """Выполнить верификацию для суда."""
        pass
