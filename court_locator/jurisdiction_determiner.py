"""
Обёртка определения подсудности по адресу (план улучшения, этап 3).
Нормализация → точное совпадение по району → геокодирование → суд по координатам.
Использует court_matcher.CourtMatcher и нормализацию из batch_processing.
"""
from typing import Any, Dict, Optional


class JurisdictionDeterminer:
    """
    Определение подсудности по адресу.
    Порядок: парсинг района из адреса → БД по району → геокодер → суд по координатам.
    """

    def __init__(self, use_cache: bool = True):
        self._use_cache = use_cache
        self._matcher = None

    def _get_matcher(self):
        if self._matcher is None:
            from court_locator.court_matcher import CourtMatcher
            self._matcher = CourtMatcher()
        return self._matcher

    def determine_jurisdiction(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Определить суд по адресу.
        Возвращает словарь с court_name, address, region, source и т.д. или None.
        """
        address = (address or "").strip()
        if not address:
            return None
        matcher = self._get_matcher()
        court = matcher.find_court_by_address(address)
        return court

    def find_exact_match(self, normalized_address: str) -> Optional[Dict[str, Any]]:
        """Попытка найти суд по нормализованному адресу (регион + район)."""
        return self._get_matcher().find_court_by_address(normalized_address)

    def find_court_by_coordinates(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Суд по координатам."""
        return self._get_matcher().find_court_by_coordinates(lat, lon)
