"""
Оптимизированный сервис определения подсудности с кэшированием результатов.
Использует CourtLocator и кэш по адресу/координатам для сокращения времени обработки.
"""
import time
from typing import Any, Dict, Optional

# Ограничение размера кэша (LRU можно заменить на cachetools при необходимости)
_MAX_CACHE = 5000


class OptimizedJurisdictionService:
    """
    Определение подсудности с кэшем результатов.
    Кэш по ключу (address или "lat,lng") уменьшает повторные запросы к геокодеру и БД.
    """

    def __init__(self, use_geocode_cache: bool = True, result_cache_max: int = _MAX_CACHE):
        self._use_geocode_cache = use_geocode_cache
        self._result_cache: Dict[str, Dict[str, Any]] = {}
        self._result_cache_max = result_cache_max

    def _cache_key_str(self, address: Optional[str] = None, lat: Optional[float] = None, lng: Optional[float] = None) -> str:
        if address:
            return "addr:" + (address or "").strip()
        if lat is not None and lng is not None:
            return f"coord:{lat:.6f},{lng:.6f}"
        return ""

    def determine_jurisdiction(
        self,
        address: Optional[str] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Определить подсудность по адресу или координатам.
        Возвращает словарь с полями результата (45 полей при успехе) или с _error_code при ошибке.
        """
        key = self._cache_key_str(address=address, lat=lat, lng=lng)
        if key and key in self._result_cache:
            return dict(self._result_cache[key])

        from batch_processing.services.pipeline import process_debtor

        result = process_debtor(
            fio="",
            address=address or "",
            debt_amount=None,
            lat=lat,
            lng=lng,
        )

        if key:
            self._result_cache[key] = dict(result)
            if len(self._result_cache) > self._result_cache_max:
                # Удалить первые (старые) записи
                keys_to_drop = list(self._result_cache.keys())[: len(self._result_cache) - self._result_cache_max]
                for k in keys_to_drop:
                    del self._result_cache[k]
        return result

    def clear_cache(self) -> None:
        """Очистить кэш результатов."""
        self._result_cache.clear()
