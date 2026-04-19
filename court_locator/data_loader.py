"""
Загрузка данных о судебных участках из GeoJSON в БД court_districts.

Формат GeoJSON (Feature или FeatureCollection):
  - type: "Feature" | "FeatureCollection"
  - properties: id, district_number, region, address, phone, schedule, judge_name, court_name
  - geometry: { type: "Polygon", coordinates: [[[lng, lat], ...]] }

Использование:
  from court_locator.data_loader import load_geojson_to_db
  load_geojson_to_db("path/to/court_data.geojson")
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from court_locator import config
from court_locator.database import Database


def _extract_polygon_coordinates(geometry: Dict[str, Any]) -> Optional[List]:
    """Извлекает координаты полигона из GeoJSON geometry (Polygon или первый полигон MultiPolygon)."""
    if not geometry:
        return None
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords or not isinstance(coords, list):
        return None
    if gtype == "Polygon":
        return coords[0] if coords else None
    if gtype == "MultiPolygon":
        return coords[0][0] if coords and coords[0] else None
    return None


def _feature_to_district(
    feature: Dict[str, Any],
    feature_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Преобразует GeoJSON Feature в запись для court_districts."""
    if feature.get("type") != "Feature":
        return None
    props = feature.get("properties") or {}
    geometry = feature.get("geometry")
    boundaries = _extract_polygon_coordinates(geometry) if geometry else None
    if not boundaries:
        return None

    def _p(*keys: str) -> str:
        for k in keys:
            v = props.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""

    # Яндекс Конструктор карт и разные выгрузки часто несут номер участка только в name/title.
    district_number = _p("district_number", "number", "jud_dist")
    if not district_number:
        name_or_title = _p("name", "title", "court_name")
        m = re.search(r"(?:№|N)\s*(\d+)", name_or_title)
        if m:
            district_number = m.group(1)
    if not district_number and props.get("id_distr") is not None:
        district_number = str(int(props["id_distr"]))
    region = _p("region", "jud_reg") or (str(int(props.get("id_reg", 0))) if props.get("id_reg") is not None else "")
    district_id = feature_id if feature_id is not None else props.get("id") or props.get("object_id")
    if district_id is None:
        district_id = hash((region, district_number)) % (2 ** 31)
    return {
        "id": int(district_id) if isinstance(district_id, (int, float)) else hash(str(district_id)) % (2 ** 31),
        "district_number": district_number,
        "region": region,
        "boundaries": boundaries,
        "law_reference": _p("law_reference", "law", "law_ref", "normative_reference", "npa"),
        "address": props.get("address") or "",
        "phone": props.get("phone") or "",
        "email": props.get("email") or props.get("court_email") or "",
        "schedule": props.get("schedule") or "",
        "judge_name": props.get("judge_name") or "",
        "court_name": props.get("court_name") or _p("name", "title") or district_number or "",
    }


def load_geojson_to_db(
    geojson_path: Union[str, Path],
    db_path: Optional[str] = None,
    *,
    clear_before: bool = False,
) -> int:
    """
    Загружает судебные участки из GeoJSON файла в таблицу court_districts.

    :param geojson_path: путь к .geojson или .json
    :param db_path: путь к court_districts.sqlite (по умолчанию из config)
    :param clear_before: очистить таблицу перед загрузкой
    :return: количество загруженных записей
    """
    path = Path(geojson_path)
    if not path.exists():
        raise FileNotFoundError("GeoJSON file not found: %s" % path)

    # Для выгрузок из разных источников используем мягкий fallback по кодировке.
    data = None
    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            with path.open("r", encoding=enc) as f:
                data = json.load(f)
            break
        except Exception:
            data = None
    if data is None:
        raise ValueError(f"Cannot parse GeoJSON file with supported encodings: {path}")

    features: List[Dict] = []
    if data.get("type") == "Feature":
        features = [data]
    elif data.get("type") == "FeatureCollection":
        features = data.get("features") or []
    else:
        raise ValueError("GeoJSON must be Feature or FeatureCollection")

    districts: List[Dict[str, Any]] = []
    for i, feat in enumerate(features):
        row = _feature_to_district(feat, feature_id=i + 1)
        if row:
            districts.append(row)

    if not districts:
        return 0

    db = Database(districts_db_path=db_path or config.COURT_DISTRICTS_DB_PATH)
    db.init_schema()
    if clear_before:
        conn = db._get_districts_conn()
        conn.execute("DELETE FROM court_districts")
        conn.commit()
    db.update_districts(districts)
    db.close()
    return len(districts)
