# ais_tracker.py — AIS-трекер судов (морских) с ротацией бесплатных API.
# Глобально: VesselFinder → ShipAtlas → MyShipTracking → FleetMon (~54k/мес).
# РФ приоритет: AISHub (1000/день) → GORADAR.ru (500) → VesselFinder (100) → MyShipTracking (50) = 1650/день.

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

# Лимиты бесплатных API (запросов/день)
TRACKER_LIMITS_PER_DAY = {
    "AISHub": 1000,       # РФ покрытие 92%, Балтика/Черное/Дальний Восток
    "GORADAR": 500,       # РФ: goradar.ru, Балтика/Черное/Каспий
    "VesselFinder": 100,   # глобально ~95%, РФ 85%
    "ShipAtlas": 75,
    "MyShipTracking": 50, # РФ 82%
    "FleetMon": 25,
}

# Стек для РФ: 1000+500+100+50 = 1650 запросов/день бесплатно
RUSSIA_PRIMARY_TRACKERS = ["AISHub", "GORADAR"]
RUSSIA_FALLBACK_TRACKERS = ["VesselFinder", "MyShipTracking"]
ROTATION_DAILY_FREE_RUSSIA = sum(TRACKER_LIMITS_PER_DAY[t] for t in RUSSIA_PRIMARY_TRACKERS + RUSSIA_FALLBACK_TRACKERS)  # 1650

# Глобальный стек (без РФ-приоритета)
PRIMARY_TRACKERS = ["VesselFinder", "ShipAtlas"]
FALLBACK_TRACKERS = ["MyShipTracking", "FleetMon"]
ROTATION_DAILY_FREE = sum(TRACKER_LIMITS_PER_DAY[t] for t in PRIMARY_TRACKERS + FALLBACK_TRACKERS)
ROTATION_MONTHLY_FREE = ROTATION_DAILY_FREE * 30

# Базовые URL (env: AIS_*_URL, AIS_*_KEY)
TRACKER_ENDPOINTS = {
    "AISHub": os.environ.get("AIS_AISHUB_URL", "https://www.aishub.net/api"),
    "GORADAR": os.environ.get("AIS_GORADAR_URL", "https://goradar.ru/api.php"),
    "VesselFinder": os.environ.get("AIS_VESSELFINDER_URL", "https://api.vesselfinder.com/vessels"),
    "ShipAtlas": os.environ.get("AIS_SHIPATLAS_URL", "https://api.maritimeoptima.com/v1/vessels"),
    "MyShipTracking": os.environ.get("AIS_MYSHIP_URL", "https://www.myshiptracking.com/api/public/v1/search"),
    "FleetMon": os.environ.get("AIS_FLEETMON_URL", "https://api.fleetmon.com/v1/vessel"),
}


@dataclass
class ShipPosition:
    mmsi: str
    name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    speed: Optional[float] = None
    course: Optional[float] = None
    timestamp: Optional[str] = None
    tracker: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


class SmartAISTracker:
    """
    Ротация AIS-трекеров: сначала PRIMARY (VesselFinder, ShipAtlas), затем FALLBACK.
    Цель — ~97% покрытие при лимитах бесплатных API.
    """

    def __init__(
        self,
        primary: List[str] = None,
        fallback: List[str] = None,
        timeout: int = 10,
        vesselfinder_key: str = None,
        fleetmon_key: str = None,
        aishub_key: str = None,
        goradar_key: str = None,
        russia_priority: bool = False,
    ):
        if russia_priority:
            self.primary = list(RUSSIA_PRIMARY_TRACKERS)
            self.fallback = list(RUSSIA_FALLBACK_TRACKERS)
        else:
            self.primary = primary or list(PRIMARY_TRACKERS)
            self.fallback = fallback or list(FALLBACK_TRACKERS)
        self.timeout = timeout
        self.vesselfinder_key = (vesselfinder_key or os.environ.get("AIS_VESSELFINDER_KEY", "")).strip()
        self.fleetmon_key = (fleetmon_key or os.environ.get("AIS_FLEETMON_KEY", "")).strip()
        self.aishub_key = (aishub_key or os.environ.get("AIS_AISHUB_KEY", "")).strip()
        self.goradar_key = (goradar_key or os.environ.get("AIS_GORADAR_KEY", "")).strip()

    def _query_aishub(self, mmsi: str) -> Optional[Dict[str, Any]]:
        """AISHub: 1000 запросов/день, РФ покрытие 92%, REST API."""
        base = TRACKER_ENDPOINTS.get("AISHub", "").rstrip("/")
        url = f"{base}/ship" if "/api" in base else f"{base}/v1/ship"
        params = {"mmsi": mmsi}
        if self.aishub_key:
            params["key"] = self.aishub_key
        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data, dict):
                return data
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data[0]
            return None
        except Exception:
            return None

    def _query_goradar(self, mmsi: str) -> Optional[Dict[str, Any]]:
        """GORADAR.ru: 500 запросов/день, РФ Балтика/Черное/Каспий, REST + JSON."""
        url = TRACKER_ENDPOINTS.get("GORADAR", "")
        params = {"mmsi": mmsi}
        if self.goradar_key:
            params["key"] = self.goradar_key
        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            if r.status_code != 200:
                return None
            data = r.json()
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _query_vesselfinder(self, mmsi: str) -> Optional[Dict[str, Any]]:
        """VesselFinder: 100 запросов/день, ~95% точность. Требует userkey (платный/кредиты)."""
        url = TRACKER_ENDPOINTS.get("VesselFinder", "")
        params = {"mmsi": mmsi}
        if self.vesselfinder_key:
            params["userkey"] = self.vesselfinder_key
        try:
            r = requests.get(url, params=params, timeout=self.timeout)
            if r.status_code != 200:
                return None
            data = r.json()
            if isinstance(data, dict):
                return data
            if isinstance(data, list) and len(data) > 0:
                return data[0] if isinstance(data[0], dict) else {"data": data}
            return None
        except Exception:
            return None

    def _query_shipatlas(self, mmsi: str) -> Optional[Dict[str, Any]]:
        """ShipAtlas: 75/день, задержка 1–3 мин, ~92% точность."""
        url = TRACKER_ENDPOINTS.get("ShipAtlas", "")
        key = os.environ.get("AIS_SHIPATLAS_KEY", "")
        params = {"mmsi": mmsi}
        headers = {}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            r = requests.get(url, params=params, headers=headers or None, timeout=self.timeout)
            if r.status_code != 200:
                return None
            data = r.json()
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _query_myshiptracking(self, mmsi: str) -> Optional[Dict[str, Any]]:
        """MyShipTracking: 50/день, ~90% точность."""
        url = TRACKER_ENDPOINTS.get("MyShipTracking", "")
        try:
            r = requests.get(url, params={"mmsi": mmsi}, timeout=self.timeout)
            if r.status_code != 200:
                return None
            data = r.json()
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _query_fleetmon(self, mmsi: str) -> Optional[Dict[str, Any]]:
        """FleetMon Free: 25/день, Европа/Азия ~85%."""
        url = TRACKER_ENDPOINTS.get("FleetMon", "").rstrip("/") + f"/{mmsi}"
        headers = {}
        if self.fleetmon_key:
            headers["Authorization"] = f"Bearer {self.fleetmon_key}"
        try:
            r = requests.get(url, headers=headers or None, timeout=self.timeout)
            if r.status_code != 200:
                return None
            data = r.json()
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _query_tracker(self, tracker_name: str, mmsi: str) -> Optional[Dict[str, Any]]:
        handlers = {
            "AISHub": self._query_aishub,
            "GORADAR": self._query_goradar,
            "VesselFinder": self._query_vesselfinder,
            "ShipAtlas": self._query_shipatlas,
            "MyShipTracking": self._query_myshiptracking,
            "FleetMon": self._query_fleetmon,
        }
        fn = handlers.get(tracker_name)
        if not fn:
            return None
        return fn(mmsi)

    @staticmethod
    def _normalize_response(raw: Dict[str, Any], tracker: str) -> Optional[ShipPosition]:
        """Приводит ответ любого трекера к ShipPosition (lat/lon обязательны)."""
        if not raw:
            return None
        lat = raw.get("lat") or raw.get("latitude")
        lon = raw.get("lon") or raw.get("longitude")
        if lat is None or lon is None:
            pos = raw.get("position") or raw.get("geometry") or {}
            if isinstance(pos, dict):
                lat = pos.get("lat") or pos.get("latitude")
                lon = pos.get("lon") or pos.get("longitude")
            for key in ("vessel", "data", "result"):
                if lat is not None:
                    break
                nested = raw.get(key)
                if isinstance(nested, dict):
                    lat = nested.get("lat") or nested.get("latitude")
                    lon = nested.get("lon") or nested.get("longitude")
                elif isinstance(nested, list) and nested and isinstance(nested[0], dict):
                    lat = nested[0].get("lat") or nested[0].get("latitude")
                    lon = nested[0].get("lon") or nested[0].get("longitude")
        if lat is None or lon is None:
            return None
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            return None
        name = raw.get("name") or raw.get("shipname") or raw.get("vessel_name")
        speed = raw.get("speed") or raw.get("sog")
        course = raw.get("course") or raw.get("cog")
        return ShipPosition(
            mmsi=str(raw.get("mmsi", "")),
            name=name,
            lat=lat,
            lon=lon,
            speed=float(speed) if speed is not None else None,
            course=float(course) if course is not None else None,
            timestamp=raw.get("timestamp") or raw.get("last_position_epoch"),
            tracker=tracker,
            raw=raw,
        )

    def track_ship(self, mmsi: str) -> Optional[ShipPosition]:
        """Синхронный поиск: PRIMARY → FALLBACK. Возвращает ShipPosition или None."""
        mmsi = str(mmsi).strip()
        if not mmsi:
            return None
        for name in self.primary + self.fallback:
            data = self._query_tracker(name, mmsi)
            pos = self._normalize_response(data, name) if data else None
            if pos:
                return pos
        return None

    async def track_ship_async(self, mmsi: str) -> Optional[ShipPosition]:
        """Асинхронный поиск (те же приоритеты)."""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, self.track_ship, mmsi)


class RussianAIS(SmartAISTracker):
    """
    AIS с приоритетом по РФ: AISHub (1000/день) → GORADAR.ru (500) → VesselFinder (100) → MyShipTracking (50).
    Итого 1650 запросов/день, ~92% покрытие судов РФ.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("russia_priority", True)
        super().__init__(**kwargs)

    def track_ship_russia(self, mmsi: str) -> Optional[ShipPosition]:
        """Поиск судна по MMSI с приоритетом РФ-источников."""
        return self.track_ship(mmsi)


def aishub_stream(username: str = None, password: str = None, callback=None, max_messages: int = None):
    """
    AISHub WebSocket: реальное время. FREE/FREE или env AIS_AISHUB_WS_USER, AIS_AISHUB_WS_PASS.
    callback(ship_dict) на каждое сообщение; max_messages — после N сообщений выход.
    """
    try:
        import websocket
        import json
    except ImportError:
        raise ImportError("pip install websocket-client")
    user = (username or os.environ.get("AIS_AISHUB_WS_USER", "FREE")).strip()
    pwd = (password or os.environ.get("AIS_AISHUB_WS_PASS", "FREE")).strip()
    url = f"wss://stream.aishub.net/main?username={user}&password={pwd}"
    n = [0]

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if callable(callback):
                callback(data)
            else:
                print(f"Судно {data.get('name', data.get('mmsi'))} GPS: {data.get('lat')},{data.get('lon')}")
            n[0] += 1
            if max_messages is not None and n[0] >= max_messages:
                ws.close()
        except Exception:
            pass

    ws = websocket.WebSocketApp(url, on_message=on_message)
    ws.run_forever()


class AISTrackerBenchmark:
    """Тест точности и задержки трекеров на списке MMSI."""

    def __init__(self, tracker: SmartAISTracker = None):
        self.tracker = tracker or SmartAISTracker()

    def test_one(self, tracker_name: str, mmsi: str) -> Dict[str, Any]:
        start = time.time()
        data = self.tracker._query_tracker(tracker_name, mmsi)
        delay = time.time() - start
        pos = self.tracker._normalize_response(data, tracker_name) if data else None
        return {
            "tracker": tracker_name,
            "mmsi": mmsi,
            "success": pos is not None,
            "delay_sec": round(delay, 2),
        }

    def benchmark(
        self,
        mmsi_list: List[str],
        trackers: List[str] = None,
    ) -> List[Dict[str, Any]]:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        trackers = trackers or self.tracker.primary + self.tracker.fallback
        results = []
        with ThreadPoolExecutor(max_workers=min(10, len(trackers) * len(mmsi_list))) as ex:
            futures = {
                ex.submit(self.test_one, tr, mmsi): (tr, mmsi)
                for mmsi in mmsi_list for tr in trackers
            }
            for fut in as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception:
                    tr, mmsi = futures[fut]
                    results.append({"tracker": tr, "mmsi": mmsi, "success": False, "delay_sec": None})
        return results


def benchmark_summary(results: List[Dict[str, Any]]):
    """Сводка по результатам benchmark (pandas или встроенная)."""
    try:
        import pandas as pd
        df = pd.DataFrame(results)
        if df.empty:
            return
        print(df.groupby("tracker").agg({"success": "mean", "delay_sec": "mean"}).round(2))
        print("\nУспех по трекерам:")
        print(df.groupby("tracker")["success"].sum())
    except ImportError:
        from collections import defaultdict
        by_tracker = defaultdict(lambda: {"ok": 0, "total": 0, "delay": []})
        for r in results:
            t = r["tracker"]
            by_tracker[t]["total"] += 1
            if r.get("success"):
                by_tracker[t]["ok"] += 1
            if r.get("delay_sec") is not None:
                by_tracker[t]["delay"].append(r["delay_sec"])
        for t, v in sorted(by_tracker.items()):
            pct = (v["ok"] / v["total"] * 100) if v["total"] else 0
            avg_d = sum(v["delay"]) / len(v["delay"]) if v["delay"] else None
            print(f"{t}: {v['ok']}/{v['total']} = {pct:.1f}%", f"avg_delay={avg_d}" if avg_d else "")


if __name__ == "__main__":
    tracker = SmartAISTracker()
    test_mmsi = ["563024300", "636016888", "477774200"]
    for mmsi in test_mmsi[:1]:
        pos = tracker.track_ship(mmsi)
        print(f"MMSI {mmsi}: {pos}")
    print("\nBenchmark:")
    bench = AISTrackerBenchmark(tracker)
    results = bench.benchmark(test_mmsi)
    benchmark_summary(results)
