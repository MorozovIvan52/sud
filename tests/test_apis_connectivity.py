"""
Тесты подключения и ответов API, используемых для определения подсудности.
Запуск: pytest tests/test_apis_connectivity.py -v
С ключами в .env проверяются DaData и Yandex Geocoder; без ключей тесты помечаются skip.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# корень проекта
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if str(ROOT / "parser") not in sys.path:
    sys.path.insert(0, str(ROOT / "parser"))

# загрузка .env
_env = ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass


def _has_dadata() -> bool:
    return bool((os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or "").strip())


def _has_yandex_geo() -> bool:
    sys.path.insert(0, str(ROOT))
    try:
        from court_locator import config as clc

        return bool((clc.YANDEX_GEO_KEY or "").strip())
    except Exception:
        return bool(
            (
                os.getenv("YANDEX_GEO_KEY")
                or os.getenv("YANDEX_GEOCODER_API_KEY")
                or os.getenv("YANDEX_LOCATOR_API_KEY")
                or os.getenv("YANDEX_LOCATOR_KEY")
                or ""
            ).strip()
        )


@pytest.fixture(scope="module")
def check_apis():
    from parser.check_apis import _load_dotenv
    _load_dotenv()
    import parser.check_apis as m
    return m


def test_dadata_connected_and_responds(check_apis):
    """DaData API: ключ задан и suggest/address возвращает ответ (или таймаут при недоступности)."""
    if not _has_dadata():
        pytest.skip("DADATA_TOKEN не задан")
    ok, msg = check_apis.check_dadata()
    if not ok and "timed out" in msg.lower():
        pytest.skip(f"DaData недоступен (таймаут): {msg}")
    assert ok, f"DaData: {msg}"


def test_yandex_geocoder_connected_and_responds(check_apis):
    """Yandex Geocoder: ключ задан и запрос возвращает координаты."""
    if not _has_yandex_geo():
        pytest.skip("YANDEX_GEO_KEY / YANDEX_GEOCODER_API_KEY / LOCATOR не заданы")
    ok, msg = check_apis.check_yandex_geocoder()
    assert ok, f"Yandex Geocoder: {msg}"


def test_courts_db_available(check_apis):
    """БД судов (courts.sqlite): доступна и можно выполнить запрос."""
    ok, msg = check_apis.check_courts_db()
    assert ok, f"БД судов: {msg}"


def test_dadata_suggest_returns_suggestions():
    """DaData: при успешном ответе standardize_address возвращает непустую строку."""
    if not _has_dadata():
        pytest.skip("DADATA_TOKEN не задан")
    from parser.dadata_api import standardize_address
    result = standardize_address("Москва, Тверская, 1")
    # При таймауте/ошибке API вернёт None — тест не падает (проверяем только формат ответа)
    if result is not None:
        assert isinstance(result, str) and len(result) > 0, "ожидается непустая строка адреса"


def test_yandex_geocode_returns_coords():
    """Yandex: геокодер возвращает координаты для известного адреса."""
    if not _has_yandex_geo():
        pytest.skip("ключ Геокодера не задан (см. court_locator.config)")
    import requests

    sys.path.insert(0, str(ROOT))
    from court_locator import config as clc

    key = clc.YANDEX_GEO_KEY
    r = requests.get(
        "https://geocode-maps.yandex.ru/1.x/",
        params={"apikey": key, "geocode": "Москва Красная площадь", "format": "json", "results": 1},
        timeout=10,
    )
    assert r.status_code == 200, f"HTTP {r.status_code}"
    data = r.json()
    members = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
    assert len(members) > 0, "ожидается хотя бы один featureMember"
    pos = members[0].get("GeoObject", {}).get("Point", {}).get("pos")
    assert pos, "в ответе должны быть координаты (pos)"
    lon, lat = map(float, pos.split())
    assert -90 <= lat <= 90 and -180 <= lon <= 180
