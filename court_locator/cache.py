"""
Опциональное кеширование результатов поиска суда по координатам/адресу.
При наличии REDIS_URL используется Redis, иначе — in-memory кеш (TTL по умолчанию 1 час).
"""
import json
from typing import Any, Dict, Optional

from court_locator import config


def _redis_available() -> bool:
    try:
        url = getattr(config, "REDIS_URL", "") or ""
        return bool(url and url.strip())
    except Exception:
        return False


class _MemoryCache:
    """Простой in-memory кеш с TTL (без внешних зависимостей)."""

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 10000):
        self._ttl = ttl_seconds
        self._max = max_size
        self._data: Dict[str, tuple] = {}  # key -> (value_json, expiry_time)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        import time
        if key not in self._data:
            return None
        val, expiry = self._data[key]
        if expiry and time.time() > expiry:
            del self._data[key]
            return None
        try:
            return json.loads(val) if isinstance(val, str) else val
        except Exception:
            return None

    def set(self, key: str, data: Dict[str, Any], expire: Optional[int] = None) -> None:
        import time
        if len(self._data) >= self._max:
            self._evict_one()
        ttl = expire if expire is not None else self._ttl
        expiry = time.time() + ttl if ttl else None
        self._data[key] = (json.dumps(data, ensure_ascii=False), expiry)

    def _evict_one(self) -> None:
        import time
        now = time.time()
        for k in list(self._data):
            _, exp = self._data[k]
            if exp and now > exp:
                del self._data[k]
                return
        if self._data:
            del self._data[next(iter(self._data))]


class CourtLocatorCache:
    """
    Кеш для результатов locate_court. Ключ по координатам: округление до 5 знаков (≈1 м).
    При REDIS_URL — Redis, иначе in-memory.
    """

    def __init__(self, ttl_seconds: int = 3600):
        self._ttl = ttl_seconds
        self._redis = None
        self._memory: Optional[_MemoryCache] = None
        if _redis_available():
            try:
                import redis
                url = config.REDIS_URL
                self._redis = redis.from_url(url)
                self._redis.ping()
            except Exception:
                self._redis = None
        if self._redis is None:
            self._memory = _MemoryCache(ttl_seconds=ttl_seconds)
        else:
            self._memory = None

    def _key_coords(self, lat: float, lng: float) -> str:
        return "court:%.5f:%.5f" % (round(lat, 5), round(lng, 5))

    def _key_address(self, address: str) -> str:
        import hashlib
        h = hashlib.sha256((address or "").strip().encode("utf-8")).hexdigest()[:16]
        return "court:addr:%s" % h

    def get_by_coordinates(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        key = self._key_coords(lat, lng)
        if self._redis:
            try:
                raw = self._redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
            return None
        return self._memory.get(key) if self._memory else None

    def set_by_coordinates(self, lat: float, lng: float, data: Dict[str, Any], expire: Optional[int] = None) -> None:
        key = self._key_coords(lat, lng)
        ttl = expire if expire is not None else self._ttl
        if self._redis:
            try:
                self._redis.setex(key, ttl, json.dumps(data, ensure_ascii=False))
            except Exception:
                pass
        elif self._memory:
            self._memory.set(key, data, expire=ttl)

    def get_by_address(self, address: str) -> Optional[Dict[str, Any]]:
        key = self._key_address(address)
        if self._redis:
            try:
                raw = self._redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
            return None
        return self._memory.get(key) if self._memory else None

    def set_by_address(self, address: str, data: Dict[str, Any], expire: Optional[int] = None) -> None:
        key = self._key_address(address)
        ttl = expire if expire is not None else self._ttl
        if self._redis:
            try:
                self._redis.setex(key, ttl, json.dumps(data, ensure_ascii=False))
            except Exception:
                pass
        elif self._memory:
            self._memory.set(key, data, expire=ttl)
