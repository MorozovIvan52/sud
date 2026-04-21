# generate_courts_geo.py — создание courts_geo.sqlite: суды с координатами для гео-парсера.
# Источники: courts.sqlite (дополнение координатами по адресу) или CSV.
# Геокодирование: Yandex (если задан YANDEX_GEO_KEY) или Nominatim с паузой 1 сек.

import os
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

SCRIPT_DIR = Path(__file__).parent
COURTS_SQLITE = SCRIPT_DIR / "courts.sqlite"
COURTS_GEO_SQLITE = SCRIPT_DIR / "courts_geo.sqlite"
GEOCODE_PAUSE_SEC = 1.0


def _resolve_yandex_geocode_key() -> str:
    """Тот же каскад, что в court_locator.config (GEOCODER → LOCATOR)."""
    import sys

    root = SCRIPT_DIR.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from court_locator.config import YANDEX_GEO_KEY

        return (YANDEX_GEO_KEY or "").strip()
    except Exception:
        pass
    return (
        (os.environ.get("YANDEX_GEO_KEY") or os.environ.get("YANDEX_GEOCODER_API_KEY") or "").strip()
        or (os.environ.get("YANDEX_LOCATOR_API_KEY") or os.environ.get("YANDEX_LOCATOR_KEY") or "").strip()
    )


def geocode_yandex(address: str, api_key: str) -> Optional[Tuple[float, float]]:
    """Геокодирование через Yandex Geocoder API. Возвращает (lat, lon) или None."""
    import requests
    try:
        url = "https://geocode-maps.yandex.ru/1.x/"
        params = {"apikey": api_key, "geocode": address, "format": "json", "results": 1}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        members = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
        if not members:
            return None
        pos = members[0].get("GeoObject", {}).get("Point", {}).get("pos")
        if not pos:
            return None
        lon, lat = map(float, pos.split())
        return (lat, lon)
    except Exception:
        return None


def geocode_nominatim(address: str) -> Optional[Tuple[float, float]]:
    """Геокодирование через Nominatim (бесплатно). Возвращает (lat, lon) или None."""
    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError
        geolocator = Nominatim(user_agent="parser_supreme_courts_geo")
        location = geolocator.geocode(address, timeout=10)
        if location:
            return (location.latitude, location.longitude)
    except Exception:
        pass
    return None


def geocode_address(address: str, yandex_key: str = "") -> Optional[Tuple[float, float]]:
    """Сначала Yandex, при отсутствии ключа или ошибке — Nominatim. Пауза между вызовами — в вызывающем коде."""
    if (yandex_key or "").strip():
        coords = geocode_yandex(address, yandex_key.strip())
        if coords:
            return coords
    return geocode_nominatim(address)


def _parse_coords(coord_str: str) -> Optional[Tuple[float, float]]:
    if not coord_str or not isinstance(coord_str, str):
        return None
    parts = coord_str.replace(" ", "").split(",")
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return (lat, lon)
    except ValueError:
        pass
    return None


def create_courts_geo_from_courts_sqlite(
    courts_path: Path = None,
    geo_path: Path = None,
    geocode_pause_sec: float = GEOCODE_PAUSE_SEC,
    limit: Optional[int] = None,
) -> int:
    """
    Создаёт/дополняет courts_geo.sqlite из courts.sqlite.
    Для записей с заполненным coordinates копирует координаты; для остальных — геокодирует адрес.
    Возвращает количество записей в courts_geo.
    """
    courts_path = courts_path or COURTS_SQLITE
    geo_path = geo_path or COURTS_GEO_SQLITE
    yandex_key = _resolve_yandex_geocode_key()

    if not courts_path.exists():
        print(f"Файл не найден: {courts_path}")
        return 0

    conn_geo = sqlite3.connect(geo_path)
    conn_geo.execute(
        """
        CREATE TABLE IF NOT EXISTS courts_geo (
            name TEXT,
            address TEXT,
            lat REAL,
            lon REAL,
            region TEXT,
            section INTEGER,
            gps_accuracy REAL
        )
        """
    )
    conn_geo.execute("DELETE FROM courts_geo")
    conn_geo.commit()

    conn = sqlite3.connect(courts_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT court_name, address, coordinates, region, section_num, postal_index FROM courts"
    ).fetchall()
    conn.close()

    inserted = 0
    for i, row in enumerate(rows):
        if limit is not None and i >= limit:
            break
        name = row["court_name"] or ""
        address = row["address"] or ""
        region = row["region"] or ""
        section = row["section_num"]
        if section is None:
            section = 0
        coords = _parse_coords(row["coordinates"] or "")
        if not coords and address:
            time.sleep(geocode_pause_sec)
            coords = geocode_address(address, yandex_key)
        if not coords:
            continue
        lat, lon = coords
        conn_geo.execute(
            "INSERT INTO courts_geo (name, address, lat, lon, region, section, gps_accuracy) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, address, lat, lon, region, int(section), 1.0),
        )
        inserted += 1
        if (inserted % 10) == 0:
            print(f"Обработано: {inserted}")

    conn_geo.commit()
    conn_geo.close()
    print(f"Готово. Записей в courts_geo: {inserted}")
    return inserted


def create_courts_geo_from_csv(
    csv_path: str,
    geo_path: Path = None,
    address_column: str = "address",
    name_column: str = "name",
    region_column: str = "region",
    section_column: str = "section",
    geocode_pause_sec: float = GEOCODE_PAUSE_SEC,
    limit: Optional[int] = None,
) -> int:
    """
    Создаёт courts_geo.sqlite из CSV. Обязательная колонка — адрес; остальные по имени.
    Все координаты получаются геокодированием.
    """
    import pandas as pd
    geo_path = geo_path or COURTS_GEO_SQLITE
    yandex_key = _resolve_yandex_geocode_key()

    df = pd.read_csv(csv_path)
    if address_column not in df.columns:
        print(f"В CSV нет колонки '{address_column}'")
        return 0

    conn_geo = sqlite3.connect(geo_path)
    conn_geo.execute(
        """
        CREATE TABLE IF NOT EXISTS courts_geo (
            name TEXT,
            address TEXT,
            lat REAL,
            lon REAL,
            region TEXT,
            section INTEGER,
            gps_accuracy REAL
        )
        """
    )
    conn_geo.execute("DELETE FROM courts_geo")
    conn_geo.commit()

    name_col = name_column if name_column in df.columns else None
    region_col = region_column if region_column in df.columns else None
    section_col = section_column if section_column in df.columns else None

    inserted = 0
    for i, row in df.iterrows():
        if limit is not None and inserted >= limit:
            break
        address = str(row[address_column] or "").strip()
        if not address:
            continue
        time.sleep(geocode_pause_sec)
        coords = geocode_address(address, yandex_key)
        if not coords:
            continue
        lat, lon = coords
        name = str(row.get(name_col, "") or "") if name_col else ""
        region = str(row.get(region_col, "") or "") if region_col else ""
        section = row.get(section_col)
        if section is None or (isinstance(section, float) and section != section):
            section = 0
        section = int(section)
        conn_geo.execute(
            "INSERT INTO courts_geo (name, address, lat, lon, region, section, gps_accuracy) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, address, lat, lon, region, section, 1.0),
        )
        inserted += 1
        if (inserted % 10) == 0:
            print(f"Обработано: {inserted}")

    conn_geo.commit()
    conn_geo.close()
    print(f"Готово. Записей в courts_geo: {inserted}")
    return inserted


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].endswith(".csv"):
        create_courts_geo_from_csv(sys.argv[1], limit=50)
    else:
        create_courts_geo_from_courts_sqlite(limit=None)
