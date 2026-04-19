"""
Основной класс интеграции: поиск мирового суда по адресу или координатам.
Использует все API проекта: Yandex Geocoder, DaData, БД судов (courts + court_districts).
Опционально: кеширование результатов (Redis при REDIS_URL, иначе in-memory).
"""
from typing import Any, Dict, List, Optional

from court_locator.database import Database
from court_locator.court_matcher import CourtMatcher


class CourtLocator:
    """
    Единая точка входа: locate_court(address=...) или locate_court(lat=..., lng=...).
    """

    def __init__(
        self,
        courts_db_path: Optional[str] = None,
        districts_db_path: Optional[str] = None,
        use_cache: bool = True,
    ):
        self.db = Database(courts_db_path=courts_db_path, districts_db_path=districts_db_path)
        self.matcher = CourtMatcher(self.db)
        self._cache = None
        if use_cache:
            try:
                from court_locator.cache import CourtLocatorCache
                from court_locator import config
                self._cache = CourtLocatorCache(ttl_seconds=config.COURT_LOCATOR_CACHE_TTL)
            except Exception:
                self._cache = None

    def locate_court(
        self,
        address: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Находит мировой суд по адресу или по координатам.

        :param address: текстовый адрес (используются Yandex Geocoder, DaData, БД по району)
        :param lat: широта (если заданы lat и lng — поиск по полигонам/ближайший суд)
        :param lng: долгота
        :return: словарь court_name, address, region, phone, schedule, source и др. или None
        """
        if lat is not None and lng is not None:
            lat, lng = float(lat), float(lng)
            if self._cache:
                cached = self._cache.get_by_coordinates(lat, lng)
                if cached is not None:
                    return cached
            result = self.matcher.find_court_by_coordinates(lat, lng)
            if self._cache and result is not None:
                self._cache.set_by_coordinates(lat, lng, result)
            return result
        if address:
            if self._cache:
                cached = self._cache.get_by_address(address)
                if cached is not None:
                    return cached
            result = self.matcher.find_court_by_address(address)
            if self._cache and result is not None:
                self._cache.set_by_address(address, result)
            return result
        return None

    def update_court_data(self, data_source: List[Dict[str, Any]]) -> None:
        """
        Обновляет данные о границах участков (court_districts).
        data_source: список словарей с ключами id, district_number, region, boundaries (GeoJSON), address, phone, schedule, judge_name, court_name.
        """
        self.db.update_districts(data_source)

    def close(self) -> None:
        """Закрывает соединения с БД."""
        self.db.close()
