"""
Абстракция репозитория судов: единый интерфейс для SQLite и PostgreSQL.
Переключение через переменную окружения COURTS_DB_BACKEND=sqlite|postgres.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class CourtsRepository(ABC):
    @abstractmethod
    def init_schema(self):
        """Создать таблицу courts при отсутствии."""
        ...

    @abstractmethod
    def get_court_by_district(self, region: str, district: str) -> Optional[Dict[str, Any]]:
        """Найти суд по региону и району."""
        ...

    @abstractmethod
    def get_all_courts(self) -> List[Dict[str, Any]]:
        """Получить все суды."""
        ...
