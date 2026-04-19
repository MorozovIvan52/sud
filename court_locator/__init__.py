"""
Модуль определения мирового суда по адресу или координатам.

Режим «только бесплатные источники»: не задавать DADATA_TOKEN и YANDEX_GEO_KEY —
тогда используются локальная БД судов и геокодер Nominatim (OSM).
Подробно: docs/court_locator_free_sources.md

Опционально: Yandex Geocoder, DaData; БД parser/courts.sqlite, court_districts (GeoJSON).
"""
from court_locator.main import CourtLocator
from court_locator.gps_handler import GPSHandler
from court_locator.database import Database

def load_geojson_to_db(geojson_path, db_path=None, *, clear_before=False):
    """Загрузка судебных участков из GeoJSON в court_districts (см. data_loader.load_geojson_to_db)."""
    from court_locator.data_loader import load_geojson_to_db as _load
    return _load(geojson_path, db_path=db_path, clear_before=clear_before)


def load_nextgis_to_db(resource_id=None, db_path=None, *, clear_before=False):
    """Загрузка границ из NextGIS Map API (api.mapdev.io) в court_districts."""
    from court_locator.nextgis_source import load_nextgis_to_db as _load
    return _load(resource_id=resource_id, db_path=db_path, clear_before=clear_before)


def scheduled_update():
    """Обновление court_districts из URL в конфиге (COURT_DATA_UPDATE_URL). Для schedule/cron."""
    from court_locator.updater import scheduled_update as _run
    return _run()


__all__ = [
    "CourtLocator",
    "GPSHandler",
    "Database",
    "load_geojson_to_db",
    "load_nextgis_to_db",
    "scheduled_update",
]
