"""
Интеграция с NextGIS Map API — границы судебных участков.

Источник: https://api.mapdev.io — Геоинформационная система NextGIS.
Ресурс 137: Границы судебных участков (полигональный), Россошанский судебный район
(Воронежская область, вкл. Ольховатский, Подгоренский).

TMS (карта): https://api.mapdev.io/api/component/render/tile?resource=138&nd=204&z={z}&x={x}&y={y}
GeoJSON:    https://api.mapdev.io/api/resource/{resource_id}/geojson
API:       GET /api/resource/{id} — метаданные, GET /api/resource/?parent={id} — дочерние ресурсы
"""
import logging
from typing import Any, Dict, List, Optional

import requests

from court_locator import config
from court_locator.data_loader import _feature_to_district
from court_locator.database import Database

logger = logging.getLogger(__name__)

# Ресурс 137 — векторный слой границ (resource 138 — стиль QGIS для отображения)
DEFAULT_NEXTGIS_RESOURCE_ID = 137
DEFAULT_NEXTGIS_BASE_URL = "https://api.mapdev.io"
# Классы ресурсов, поддерживающие экспорт GeoJSON
GEOJSON_RESOURCE_CLASSES = ("postgis_layer", "vector_layer")


def fetch_nextgis_geojson(
    resource_id: Optional[int] = None,
    base_url: Optional[str] = None,
    timeout: int = 60,
) -> Optional[Dict[str, Any]]:
    """
    Загружает GeoJSON границ судебных участков из NextGIS API.

    :param resource_id: ID ресурса (по умолчанию из config или 137)
    :param base_url: базовый URL API (по умолчанию https://api.mapdev.io)
    :return: GeoJSON FeatureCollection или None при ошибке
    """
    rid = resource_id or getattr(config, "NEXTGIS_BOUNDARIES_RESOURCE_ID", None) or DEFAULT_NEXTGIS_RESOURCE_ID
    base = base_url or getattr(config, "NEXTGIS_BASE_URL", None) or DEFAULT_NEXTGIS_BASE_URL
    url = f"{base.rstrip('/')}/api/resource/{rid}/geojson"
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.warning("NextGIS: запрос не удался %s: %s", url, e)
        return None
    except ValueError as e:
        logger.warning("NextGIS: ответ не JSON: %s", e)
        return None


def load_nextgis_to_db(
    resource_id: Optional[int] = None,
    db_path: Optional[str] = None,
    *,
    clear_before: bool = False,
    merge_with_existing: bool = True,
) -> int:
    """
    Загружает границы из NextGIS API в court_districts.

    :param resource_id: ID ресурса NextGIS (по умолчанию 137)
    :param db_path: путь к court_districts.sqlite
    :param clear_before: очистить таблицу перед загрузкой
    :param merge_with_existing: при False — clear_before=True
    :return: количество загруженных записей
    """
    data = fetch_nextgis_geojson(resource_id=resource_id)
    if not data or data.get("type") != "FeatureCollection":
        return 0
    features = data.get("features") or []
    districts: List[Dict[str, Any]] = []
    for i, feat in enumerate(features):
        row = _feature_to_district(feat, feature_id=i + 1)
        if row:
            districts.append(row)
    if not districts:
        return 0
    db_path = db_path or config.COURT_DISTRICTS_DB_PATH
    db = Database(districts_db_path=db_path)
    db.init_schema()
    if clear_before or not merge_with_existing:
        conn = db._get_districts_conn()
        conn.execute("DELETE FROM court_districts")
        conn.commit()
    db.update_districts(districts)
    db.close()
    logger.info("NextGIS: загружено записей court_districts: %s", len(districts))
    return len(districts)


def fetch_resource_meta(
    resource_id: int,
    base_url: Optional[str] = None,
    timeout: int = 15,
) -> Optional[Dict[str, Any]]:
    """
    Метаданные ресурса NextGIS (GET /api/resource/{id}).
    Возвращает dict с resource.id, resource.cls, resource.display_name, resource.children и т.д.
    """
    base = base_url or getattr(config, "NEXTGIS_BASE_URL", None) or DEFAULT_NEXTGIS_BASE_URL
    url = f"{base.rstrip('/')}/api/resource/{resource_id}"
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.warning("NextGIS: запрос метаданных %s: %s", url, e)
        return None
    except ValueError:
        return None


def fetch_children(
    parent_id: int,
    base_url: Optional[str] = None,
    timeout: int = 15,
) -> List[Dict[str, Any]]:
    """
    Список дочерних ресурсов (GET /api/resource/?parent={id}).
    Возвращает список объектов с полями resource, resmeta, postgis_connection и т.д.
    """
    base = base_url or getattr(config, "NEXTGIS_BASE_URL", None) or DEFAULT_NEXTGIS_BASE_URL
    url = f"{base.rstrip('/')}/api/resource/"
    try:
        r = requests.get(url, params={"parent": parent_id}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except requests.RequestException as e:
        logger.warning("NextGIS: запрос дочерних %s?parent=%s: %s", url, parent_id, e)
        return []
    except ValueError:
        return []


def discover_geojson_resources(
    parent_id: int = 2,
    base_url: Optional[str] = None,
    *,
    recursive: bool = True,
) -> List[Dict[str, Any]]:
    """
    Рекурсивный поиск ресурсов с GeoJSON (postgis_layer, vector_layer).
    parent_id=2 — «Границы участков мировых судей».
    Возвращает список {id, cls, display_name} для каждого ресурса.
    """
    result: List[Dict[str, Any]] = []
    children = fetch_children(parent_id, base_url=base_url)
    for item in children:
        res = item.get("resource") if isinstance(item, dict) else {}
        if not res:
            continue
        rid = res.get("id")
        cls = res.get("cls") or ""
        name = res.get("display_name") or ""
        if cls in GEOJSON_RESOURCE_CLASSES:
            result.append({"id": rid, "cls": cls, "display_name": name})
        if recursive and res.get("children") and cls == "resource_group":
            result.extend(discover_geojson_resources(rid, base_url=base_url, recursive=True))
    return result


def load_nextgis_from_resources(
    resource_ids: Optional[List[int]] = None,
    db_path: Optional[str] = None,
    *,
    clear_before: bool = False,
) -> int:
    """
    Загружает границы из нескольких ресурсов NextGIS.
    resource_ids: список ID (по умолчанию — основной + NEXTGIS_EXTRA_RESOURCE_IDS).
    """
    main_id = getattr(config, "NEXTGIS_BOUNDARIES_RESOURCE_ID", None) or DEFAULT_NEXTGIS_RESOURCE_ID
    extra = getattr(config, "NEXTGIS_EXTRA_RESOURCE_IDS", None) or []
    ids = resource_ids or [main_id] + list(extra)
    total = 0
    all_districts: List[Dict[str, Any]] = []
    for rid in ids:
        data = fetch_nextgis_geojson(resource_id=rid)
        if not data or data.get("type") != "FeatureCollection":
            continue
        features = data.get("features") or []
        for i, feat in enumerate(features):
            row = _feature_to_district(feat, feature_id=len(all_districts) + i + 1)
            if row:
                all_districts.append(row)
    if not all_districts:
        return 0
    db_path = db_path or config.COURT_DISTRICTS_DB_PATH
    db = Database(districts_db_path=db_path)
    db.init_schema()
    if clear_before:
        conn = db._get_districts_conn()
        conn.execute("DELETE FROM court_districts")
        conn.commit()
    db.update_districts(all_districts)
    db.close()
    logger.info("NextGIS: загружено из %s ресурсов: %s записей", len(ids), len(all_districts))
    return len(all_districts)


def sync_nextgis_to_postgis(
    resource_ids: Optional[List[int]] = None,
    db_path: Optional[str] = None,
    *,
    clear_before: bool = False,
) -> int:
    """
    Загружает GeoJSON из NextGIS в PostGIS court_districts.
    Требует PG_DSN или NGW_POSTGIS_DSN и таблицу court_districts с колонкой boundary (GEOMETRY).
    """
    dsn = getattr(config, "NGW_POSTGIS_DSN", None) or ""
    if not dsn:
        import os
        dsn = os.getenv("PG_DSN", "")
    if not dsn:
        logger.warning("NextGIS→PostGIS: не задан PG_DSN или NGW_POSTGIS_DSN")
        return 0
    main_id = getattr(config, "NEXTGIS_BOUNDARIES_RESOURCE_ID", None) or DEFAULT_NEXTGIS_RESOURCE_ID
    extra = getattr(config, "NEXTGIS_EXTRA_RESOURCE_IDS", None) or []
    ids = resource_ids or [main_id] + list(extra)
    all_districts: List[Dict[str, Any]] = []
    for rid in ids:
        data = fetch_nextgis_geojson(resource_id=rid)
        if not data or data.get("type") != "FeatureCollection":
            continue
        features = data.get("features") or []
        for i, feat in enumerate(features):
            row = _feature_to_district(feat, feature_id=len(all_districts) + i + 1)
            if row:
                all_districts.append(row)
    if not all_districts:
        return 0
    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        logger.warning("NextGIS→PostGIS: не установлен psycopg2")
        return 0
    try:
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        if clear_before:
            cur.execute("TRUNCATE TABLE court_districts RESTART IDENTITY")
        for d in all_districts:
            from shapely.geometry import Polygon
            boundaries = d.get("boundaries")
            if not boundaries:
                continue
            try:
                poly = Polygon(boundaries)
                wkt = poly.wkt
            except Exception:
                continue
            cur.execute(
                """
                INSERT INTO court_districts (court_name, address, region, section_num, boundary)
                VALUES (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326))
                """,
                (
                    d.get("court_name") or "",
                    d.get("address") or "",
                    d.get("region") or "",
                    int(d.get("district_number") or 0) if str(d.get("district_number", "")).isdigit() else 0,
                    wkt,
                ),
            )
        conn.commit()
        cur.close()
        conn.close()
        logger.info("NextGIS→PostGIS: загружено %s записей", len(all_districts))
        return len(all_districts)
    except Exception as e:
        logger.warning("NextGIS→PostGIS: ошибка: %s", e)
        return 0


def get_tms_url(resource_id: int = 138, nd: int = 204) -> str:
    """
    Возвращает URL TMS для отображения границ на карте (Leaflet, OpenLayers и т.д.).

    Пример для Leaflet:
      L.tileLayer(get_tms_url(), { ... }).addTo(map)
    """
    base = getattr(config, "NEXTGIS_BASE_URL", None) or DEFAULT_NEXTGIS_BASE_URL
    return f"{base.rstrip('/')}/api/component/render/tile?resource={resource_id}&nd={nd}&z={{z}}&x={{x}}&y={{y}}"
