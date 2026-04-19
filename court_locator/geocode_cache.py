"""
Кэш геокодирования: адрес → (lat, lon).
Redis при REDIS_URL, иначе in-memory. TTL 30 дней для стабильных адресов.
"""
import hashlib
import json
import os
from typing import Optional, Tuple

GEOCODE_CACHE_TTL = int(os.getenv("GEOCODE_CACHE_TTL", "2592000"))  # 30 дней
GEOCODE_CACHE_PREFIX = "geocode:"


def _redis_available() -> bool:
    try:
        from court_locator import config
        url = getattr(config, "REDIS_URL", "") or ""
        return bool(url and url.strip())
    except Exception:
        return False


class GeocodeCache:
    """Кэш адрес → (lat, lon). Redis или in-memory."""

    def __init__(self, ttl_seconds: int = GEOCODE_CACHE_TTL):
        self._ttl = ttl_seconds
        self._redis = None
        self._memory: dict = {}
        if _redis_available():
            try:
                from court_locator import config
                import redis
                self._redis = redis.from_url(config.REDIS_URL)
                self._redis.ping()
            except Exception:
                self._redis = None

    def _key(self, address: str) -> str:
        h = hashlib.sha256((address or "").strip().encode("utf-8")).hexdigest()[:24]
        return f"{GEOCODE_CACHE_PREFIX}{h}"

    def get(self, address: str) -> Optional[Tuple[float, float]]:
        """Возвращает (lat, lon) или None."""
        key = self._key(address)
        if self._redis:
            try:
                raw = self._redis.get(key)
                if raw:
                    d = json.loads(raw)
                    return (float(d["lat"]), float(d["lon"]))
            except Exception:
                pass
            return None
        if key in self._memory:
            return self._memory[key]
        return None

    def set(self, address: str, lat: float, lon: float, ttl: Optional[int] = None) -> None:
        """Сохраняет результат геокодирования."""
        key = self._key(address)
        ttl = ttl or self._ttl
        val = {"lat": lat, "lon": lon}
        if self._redis:
            try:
                self._redis.setex(key, ttl, json.dumps(val))
            except Exception:
                pass
        else:
            self._memory[key] = (lat, lon)
