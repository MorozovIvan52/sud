"""
Единый кэш ответов: Redis (продакшен) или SQLite (локально).
Поддержка:
- версионирования ключей кэша;
- разных TTL для адресов и координат;
- инвалидации (полной и по префиксу).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("unified_jurisdiction.cache")

_DEFAULT_SQLITE = Path(__file__).resolve().parent.parent / "parser" / "unified_jurisdiction_cache.sqlite"


def _cache_version() -> str:
    return (os.getenv("UNIFIED_JURISDICTION_CACHE_VERSION") or "v1").strip() or "v1"


def _ttl_for_key(key: str, fallback: int) -> int:
    k = key or ""
    if ":coord:" in k:
        return int(os.getenv("UNIFIED_JURISDICTION_CACHE_TTL_COORD", "2592000"))
    if ":addr:" in k:
        return int(os.getenv("UNIFIED_JURISDICTION_CACHE_TTL_ADDR", "604800"))
    return fallback


def cache_key_for_address(normalized_address: str) -> str:
    h = hashlib.sha256((normalized_address or "").strip().encode("utf-8")).hexdigest()
    return f"{_cache_version()}:addr:{h}"


def cache_key_for_coordinates(lat: float, lng: float, ndigits: int = 5) -> str:
    return f"{_cache_version()}:coord:{round(lat, ndigits)}:{round(lng, ndigits)}"


class UnifiedCache:
    def __init__(
        self,
        ttl_seconds: int = 3600,
        sqlite_path: Optional[str] = None,
    ):
        self._ttl = ttl_seconds
        self._redis = None
        self._stats: Dict[str, int] = {"hits": 0, "misses": 0, "sets": 0, "invalidations": 0}
        self._sqlite_path = sqlite_path or os.getenv(
            "UNIFIED_JURISDICTION_CACHE_SQLITE",
            str(_DEFAULT_SQLITE),
        )
        url = (os.getenv("REDIS_URL") or "").strip()
        if url:
            try:
                import redis

                r = redis.from_url(url)
                r.ping()
                self._redis = r
            except Exception as e:
                logger.debug("UnifiedCache: Redis недоступен (%s), SQLite", e)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if self._redis:
            try:
                raw = self._redis.get(f"uj:{key}")
                if raw:
                    self._stats["hits"] += 1
                    return json.loads(raw)
            except Exception as e:
                logger.debug("UnifiedCache get redis: %s", e)
        v = self._get_sqlite(key)
        if v is None:
            self._stats["misses"] += 1
        else:
            self._stats["hits"] += 1
        return v

    def set(self, key: str, payload: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        ttl = int(ttl_seconds) if ttl_seconds is not None else _ttl_for_key(key, self._ttl)
        if self._redis:
            try:
                self._redis.setex(f"uj:{key}", ttl, data)
                self._stats["sets"] += 1
                return
            except Exception as e:
                logger.debug("UnifiedCache set redis: %s", e)
        self._set_sqlite(key, payload, ttl_seconds=ttl)
        self._stats["sets"] += 1

    def invalidate_all(self) -> None:
        if self._redis:
            try:
                for k in self._redis.scan_iter("uj:*"):
                    self._redis.delete(k)
            except Exception as e:
                logger.debug("UnifiedCache invalidate_all redis: %s", e)
        try:
            conn = sqlite3.connect(self._sqlite_path)
            conn.execute("DELETE FROM uj_cache")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("UnifiedCache invalidate_all sqlite: %s", e)
        self._stats["invalidations"] += 1

    def invalidate_prefix(self, prefix: str) -> None:
        p = (prefix or "").strip()
        if not p:
            return
        if self._redis:
            try:
                for k in self._redis.scan_iter(f"uj:{p}*"):
                    self._redis.delete(k)
            except Exception as e:
                logger.debug("UnifiedCache invalidate_prefix redis: %s", e)
        try:
            conn = sqlite3.connect(self._sqlite_path)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS uj_cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL)"
            )
            conn.execute("DELETE FROM uj_cache WHERE key LIKE ?", (f"{p}%",))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("UnifiedCache invalidate_prefix sqlite: %s", e)
        self._stats["invalidations"] += 1

    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def _get_sqlite(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            conn = sqlite3.connect(self._sqlite_path)
            cur = conn.execute(
                "SELECT value, expires_at FROM uj_cache WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
            conn.close()
            if not row:
                return None
            val, exp = row[0], row[1]
            if exp and time.time() > exp:
                return None
            return json.loads(val)
        except Exception:
            return None

    def _set_sqlite(self, key: str, payload: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        try:
            Path(self._sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._sqlite_path)
            conn.execute(
                """CREATE TABLE IF NOT EXISTS uj_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL
                )"""
            )
            ttl = self._ttl if ttl_seconds is None else int(ttl_seconds)
            exp = time.time() + ttl if ttl else None
            conn.execute(
                "INSERT OR REPLACE INTO uj_cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(payload, ensure_ascii=False), exp),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("UnifiedCache sqlite: %s", e)
