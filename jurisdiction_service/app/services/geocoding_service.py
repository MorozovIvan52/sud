"""
Сервис геокодирования с поддержкой нескольких провайдеров.
Яндекс.Геокодер: yandex.ru/maps-api/docs/geocoder-api
Кэширование в Redis и БД. habr.com/ru/companies/otus/articles/764902/
"""
import hashlib
import json
from typing import Optional

import httpx

from app.core.config import get_settings
from app.core.exceptions import AddressNotFoundError, GeocodingError
from app.core.database import get_redis
from app.services.address_normalizer import AddressNormalizer


class GeocodingService:
    """Геокодирование с fallback и кэшированием."""

    def __init__(self):
        self.settings = get_settings()
        self.normalizer = AddressNormalizer()

    def _cache_key(self, address: str) -> str:
        return f"geocode:{hashlib.sha256(address.strip().lower().encode()).hexdigest()}"

    async def _get_cached(self, key: str) -> Optional[tuple[float, float, str]]:
        """Получить из Redis кэша."""
        try:
            redis = await get_redis()
            data = await redis.get(key)
            if data:
                d = json.loads(data)
                return (d["lat"], d["lon"], d.get("provider", ""))
        except Exception:
            pass
        return None

    async def _set_cached(self, key: str, lat: float, lon: float, provider: str) -> None:
        """Сохранить в Redis."""
        try:
            redis = await get_redis()
            await redis.setex(
                key,
                self.settings.geocode_cache_ttl,
                json.dumps({"lat": lat, "lon": lon, "provider": provider}),
            )
        except Exception:
            pass

    async def _yandex_geocode(self, address: str) -> Optional[tuple[float, float]]:
        """Яндекс.Геокодер."""
        key = self.settings.yandex_geo_key or self.settings.yandex_locator_api_key
        if not key:
            return None
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://geocode-maps.yandex.ru/1.x/",
                    params={
                        "apikey": key,
                        "geocode": address,
                        "format": "json",
                    },
                    timeout=10,
                )
                if r.status_code != 200:
                    return None
                data = r.json()
                geo = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
                if not geo:
                    return None
                pos = geo[0].get("GeoObject", {}).get("Point", {}).get("pos", "")
                if not pos:
                    return None
                lon, lat = map(float, pos.split())
                return (lat, lon)
        except Exception:
            return None

    async def _dadata_geocode(self, address: str) -> Optional[tuple[float, float]]:
        """DaData suggest/address."""
        if not self.settings.dadata_token:
            return None
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address",
                    json={"query": address, "count": 1},
                    headers={
                        "Authorization": f"Token {self.settings.dadata_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=10,
                )
                if r.status_code != 200:
                    return None
                data = r.json()
                suggestions = data.get("suggestions") or []
                if not suggestions:
                    return None
                d = suggestions[0].get("data") or {}
                lat = d.get("geo_lat")
                lon = d.get("geo_lon")
                if lat and lon:
                    return (float(lat), float(lon))
        except Exception:
            pass
        return None

    async def geocode(self, address: str) -> tuple[float, float, str]:
        """
        Геокодирование адреса. Возвращает (lat, lon, provider).
        Порядок: кэш → Yandex → DaData.
        """
        normalized = self.normalizer.normalize(address)
        key = self._cache_key(normalized)

        cached = await self._get_cached(key)
        if cached:
            return cached

        result = await self._yandex_geocode(normalized)
        provider = "yandex"
        if result is None:
            result = await self._dadata_geocode(normalized)
            provider = "dadata"

        if result is None:
            raise AddressNotFoundError("Адрес не найден", address=normalized)

        lat, lon = result
        await self._set_cached(key, lat, lon, provider)
        return (lat, lon, provider)

    async def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """Обратное геокодирование (координаты → адрес)."""
        key = self.settings.yandex_geo_key or self.settings.yandex_locator_api_key
        if not key:
            return None
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://geocode-maps.yandex.ru/1.x/",
                    params={
                        "apikey": key,
                        "geocode": f"{lon},{lat}",
                        "format": "json",
                    },
                    timeout=10,
                )
                if r.status_code != 200:
                    return None
                data = r.json()
                geo = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
                if not geo:
                    return None
                return geo[0].get("GeoObject", {}).get("metaDataProperty", {}).get("GeocoderMetaData", {}).get("text")
        except Exception:
            return None
