# supreme_turbo.py — многоуровневый кэш (L1–L4) + батч: ~0.8 сек/ИП, обработка исключений, корректное закрытие сессий.
# Синхронный Redis, aiosqlite, aiohttp с гарантированным __aexit__.

import asyncio
import json
import os
import time
from collections import OrderedDict
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp
import aiosqlite

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
TURBO_CACHE_DB = SCRIPT_DIR / "turbo_cache.db"
DEFAULT_CACHE_TTL = 86400
L1_MAX_SIZE = 50_000
SEMAPHORE_LIMIT = 100


# ----- Redis (синхронный, опционально) -----
def _get_redis():
    try:
        import redis
        return redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", "6379")), db=0, decode_responses=True)
    except Exception as e:
        logger.debug("Redis недоступен: %s", e)
        return None


# ----- Обработка исключений (5 уровней) -----
class SupremeExceptionHandler:
    """Безопасная обработка исключений: Task → Semaphore → Gather → Global."""

    @staticmethod
    def safe_task(coro):
        """Уровень 1: обёртка над одной задачей."""
        @wraps(coro)
        async def wrapper(*args, **kwargs):
            try:
                return await coro(*args, **kwargs)
            except asyncio.TimeoutError:
                logger.warning("Timeout в задаче")
                return {"error": "timeout", "confidence": 0.0}
            except aiohttp.ClientError as e:
                logger.warning("Сеть: %s", e)
                return {"error": "network", "confidence": 0.0}
            except json.JSONDecodeError:
                logger.warning("JSON decode error")
                return {"error": "json", "confidence": 0.0}
            except Exception as e:
                logger.error("Ошибка задачи: %s", e)
                return {"error": str(e), "confidence": 0.0}
        return wrapper

    @staticmethod
    async def safe_gather(tasks: List, max_concurrency: int = 100) -> List:
        """Уровень 2: gather с семафором и return_exceptions."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def limited(task):
            async with semaphore:
                return await task

        wrapped = [limited(t) for t in tasks]
        results = await asyncio.gather(*wrapped, return_exceptions=True)
        out = []
        for r in results:
            if isinstance(r, Exception):
                out.append({"error": str(r), "confidence": 0.0})
            else:
                out.append(r)
        return out


# ----- Безопасная aiohttp-сессия (гарантированное закрытие) -----
class SafeAiohttpSession:
    """Контекстный менеджер: создание и гарантированное закрытие сессии и коннектора."""

    def __init__(self, max_conns: int = 200, timeout_total: int = 10, timeout_connect: int = 3):
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self.max_conns = max_conns
        self.timeout_total = timeout_total
        self.timeout_connect = timeout_connect

    async def __aenter__(self) -> "SafeAiohttpSession":
        timeout = aiohttp.ClientTimeout(total=self.timeout_total, connect=self.timeout_connect)
        self._connector = aiohttp.TCPConnector(
            limit=self.max_conns,
            limit_per_host=50,
            ttl_dns_cache=300,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
        )
        self._session = aiohttp.ClientSession(connector=self._connector, timeout=timeout)
        logger.debug("Сессия aiohttp создана: %s соединений", self.max_conns)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if self._session and not self._session.closed:
                await self._session.close()
        except Exception as e:
            logger.debug("При закрытии сессии aiohttp: %s", e)
        try:
            if self._connector:
                await self._connector.close()
        except Exception as e:
            logger.debug("При закрытии коннектора aiohttp: %s", e)
        logger.debug("Сессия aiohttp закрыта")

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("Сессия не создана. Используйте async with SafeAiohttpSession()")
        return self._session


# ----- SupremeTurbo: L1 (память) → L2 (Redis) → L3 (SQLite) → L4 (парсинг) -----
class SupremeTurbo:
    """Турбо-поиск ИП: 4 уровня кэша + опциональный robust-режим с retry и safe_gather."""

    def __init__(
        self,
        redis_client=None,
        db_path: Optional[Path] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        semaphore_limit: int = SEMAPHORE_LIMIT,
    ):
        self.redis_client = redis_client if redis_client is not None else _get_redis()
        self.db_path = Path(db_path) if db_path else TURBO_CACHE_DB
        self.cache_ttl = cache_ttl
        self.semaphore = asyncio.Semaphore(semaphore_limit)
        self._session_pool: Optional[SafeAiohttpSession] = None
        self.exception_handler = SupremeExceptionHandler()
        # L1: in-memory LRU по ИП (OrderedDict, ключ = ip)
        self._l1: OrderedDict = OrderedDict()
        self._l1_max = L1_MAX_SIZE

    async def __aenter__(self) -> "SupremeTurbo":
        self._session_pool = SafeAiohttpSession(max_conns=500, timeout_total=10, timeout_connect=3)
        await self._session_pool.__aenter__()
        await self._init_db()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Корректное закрытие сессии и коннектора (можно вызывать без async with)."""
        if self._session_pool:
            try:
                await self._session_pool.__aexit__(None, None, None)
            except Exception as e:
                logger.debug("SupremeTurbo close: %s", e)
            self._session_pool = None

    async def _init_db(self) -> None:
        """Инициализация SQLite (aiosqlite)."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "CREATE TABLE IF NOT EXISTS ips (ip TEXT PRIMARY KEY, data TEXT, timestamp REAL)"
                )
                await db.commit()
        except Exception as e:
            logger.debug("init_db: %s", e)

    def _l1_get(self, ip: str) -> Optional[Dict]:
        if ip not in self._l1:
            return None
        self._l1.move_to_end(ip)
        return self._l1[ip]

    def _l1_set(self, ip: str, data: Dict) -> None:
        if ip in self._l1:
            self._l1.move_to_end(ip)
        self._l1[ip] = data
        while len(self._l1) > self._l1_max:
            self._l1.popitem(last=False)

    def _l2_get(self, ip: str) -> Optional[Dict]:
        if not self.redis_client:
            return None
        try:
            raw = self.redis_client.get(f"ip:{ip}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    def _l2_set(self, ip: str, data: Dict) -> None:
        if not self.redis_client:
            return
        try:
            self.redis_client.setex(f"ip:{ip}", self.cache_ttl, json.dumps(data, ensure_ascii=False))
        except Exception:
            pass

    async def _l3_get(self, ip: str) -> Optional[Dict]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT data FROM ips WHERE ip = ?", (ip,)) as cur:
                    row = await cur.fetchone()
                    if row:
                        data = json.loads(row[0])
                        self._l1_set(ip, data)
                        if self.redis_client:
                            self._l2_set(ip, data)
                        return data
        except Exception:
            pass
        return None

    async def _l3_set(self, ip: str, data: Dict) -> None:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO ips (ip, data, timestamp) VALUES (?, ?, ?)",
                    (ip, json.dumps(data, ensure_ascii=False), time.time()),
                )
                await db.commit()
        except Exception as e:
            logger.debug("L3 set: %s", e)

    async def parse_fssp_turbo(self, ip: str) -> Dict:
        """L4: запрос к ФССП через единый fssp_client (ключ из FSSP_API_KEY)."""
        session = self._session_pool.session if self._session_pool else None
        if not session:
            return {"ip": ip, "status": "ошибка", "amount": 0, "source": "error"}
        try:
            from fssp_client import search_by_ip
            async with self.semaphore:
                result = await search_by_ip(ip, session, timeout=30)
            if result.get("source") == "fssp":
                result["timestamp"] = time.time()
            return result
        except aiohttp.ClientError as e:
            logger.warning("ФССП ИП %s: сеть %s", ip, e)
            return {"ip": ip, "status": "ошибка", "amount": 0, "source": "error"}
        except asyncio.TimeoutError:
            logger.warning("ФССП ИП %s: таймаут", ip)
            return {"ip": ip, "status": "ошибка", "amount": 0, "source": "error"}
        except Exception as e:
            logger.error("Parse error %s: %s", ip, e, exc_info=True)
            return {"ip": ip, "status": "ошибка", "amount": 0, "source": "error"}

    @SupremeExceptionHandler.safe_task
    async def parse_fssp_safe(self, ip: str) -> Dict:
        """Парсинг с обёрткой safe_task (для robust-режима)."""
        result = await self.parse_fssp_turbo(ip)
        if result.get("source") == "fssp":
            result["confidence"] = 1.0
        else:
            result["confidence"] = 0.5 if result.get("status") == "not_found" else 0.0
        return result

    async def search_ip_turbo(self, ip: str) -> Dict:
        """Основной метод: L1 → L2 → L3 → L4, ~0.8 с на промах кэша."""
        ip = (ip or "").strip()
        if not ip:
            return {"ip": "", "status": "пусто", "search_time": 0, "from_cache": "none"}
        start = time.time()

        # L1
        cached = self._l1_get(ip)
        if cached:
            return {**cached, "search_time": time.time() - start, "from_cache": "L1"}

        # L2
        cached = self._l2_get(ip)
        if cached:
            self._l1_set(ip, cached)
            return {**cached, "search_time": time.time() - start, "from_cache": "L2"}

        # L3
        cached = await self._l3_get(ip)
        if cached:
            return {**cached, "search_time": time.time() - start, "from_cache": "L3"}

        # L4
        result = await self.parse_fssp_turbo(ip)
        self._l1_set(ip, result)
        self._l2_set(ip, result)
        await self._l3_set(ip, result)

        result["search_time"] = time.time() - start
        result["from_cache"] = "parsed"
        logger.info("ИП %s: %.2f с (%s)", ip, result["search_time"], result["from_cache"])
        return result

    async def search_ip_robust(self, ip: str) -> Dict:
        """Поиск с retry и fallback (Redis → parse до 3 попыток → fallback)."""
        ip = (ip or "").strip()
        if not ip:
            return {"ip": "", "status": "пусто", "search_time": 0, "from_cache": "none", "confidence": 0}
        start = time.time()

        cached = self._l2_get(ip)
        if cached:
            self._l1_set(ip, cached)
            cached["search_time"] = time.time() - start
            cached["from_cache"] = "redis"
            return cached

        for attempt in range(3):
            result = await self.parse_fssp_safe(ip)
            if result.get("confidence", 0) > 0:
                self._l1_set(ip, result)
                self._l2_set(ip, result)
                await self._l3_set(ip, result)
                result["search_time"] = time.time() - start
                result["from_cache"] = "parsed"
                return result
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

        fallback = {
            "ip": ip,
            "status": "error",
            "confidence": 0.0,
            "search_time": time.time() - start,
            "from_cache": "fallback",
        }
        return fallback

    async def batch_excel_turbo(self, excel_path: str, limit: int = 10_000) -> str:
        """Excel → батч до limit ИП, вывод *_turbo.xlsx."""
        import pandas as pd
        df = pd.read_excel(excel_path)
        col = "ip" if "ip" in df.columns else df.columns[0]
        ips = df[col].astype(str).tolist()[:limit]
        tasks = [self.search_ip_turbo(ip) for ip in ips]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        clean = [r for r in results if not isinstance(r, Exception)]
        out_df = pd.DataFrame(clean)
        output_path = excel_path.replace(".xlsx", "_turbo.xlsx").replace(".xls", "_turbo.xlsx")
        out_df.to_excel(output_path, index=False)
        logger.info("Батч: %s ИП → %s", len(clean), output_path)
        return output_path

    async def batch_excel_robust(self, excel_path: str, chunk_size: int = 1000) -> str:
        """Чанками по chunk_size с safe_gather."""
        import pandas as pd
        df = pd.read_excel(excel_path)
        col = "ip" if "ip" in df.columns else df.columns[0]
        ips = df[col].astype(str).tolist()
        all_results = []
        for i in range(0, len(ips), chunk_size):
            chunk = ips[i : i + chunk_size]
            logger.info("Чанк %s/%s", i // chunk_size + 1, (len(ips) - 1) // chunk_size + 1)
            tasks = [self.search_ip_robust(ip) for ip in chunk]
            chunk_results = await self.exception_handler.safe_gather(tasks, max_concurrency=100)
            all_results.extend(chunk_results)
            if i + chunk_size < len(ips):
                await asyncio.sleep(0.1)
        out_df = pd.DataFrame(all_results)
        output_path = excel_path.replace(".xlsx", "_robust.xlsx").replace(".xls", "_robust.xlsx")
        out_df.to_excel(output_path, index=False)
        success = sum(1 for r in all_results if r.get("confidence", 0) > 0.5)
        logger.info("Robust: %s ИП, успех %.1f%%", len(all_results), 100 * success / max(1, len(all_results)))
        return output_path


async def main() -> None:
    """Тест: 1 ИП, 100 ИП, Excel при наличии файла."""
    async with SupremeTurbo() as turbo:
        # Один ИП
        r = await turbo.search_ip_turbo("2341844")
        print(f"[OK] 1 IP: {r.get('search_time', 0):.2f} s -> {r.get('status', 'N/A')}")

        # 100 ИП
        ips = [f"234{i:04d}" for i in range(100)]
        start = time.time()
        await asyncio.gather(*[turbo.search_ip_turbo(ip) for ip in ips])
        elapsed = time.time() - start
        print(f"[OK] 100 IP: {elapsed:.2f} s -> {elapsed / 100:.2f} s/IP")

        # Excel
        test_path = os.path.join(SCRIPT_DIR, "test_ips.xlsx")
        if os.path.exists(test_path):
            out = await turbo.batch_excel_turbo(test_path)
            print(f"[OK] Excel: {out}")
        else:
            print("(i) test_ips.xlsx not found, skip batch")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Остановлено пользователем")
    except Exception as e:
        logger.exception("Ошибка: %s", e)
