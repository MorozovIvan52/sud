"""
Обновление данных о судебных участках из внешних API или GeoJSON.

Использование:
  from court_locator.updater import DataUpdater
  updater = DataUpdater()
  updater.update_from_api("https://api.example.com/courts")
  # или по расписанию: schedule.every().day.at("03:00").do(scheduled_update)
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests

from court_locator import config
from court_locator.database import Database

logger = logging.getLogger(__name__)


class DataUpdater:
    """
    Загрузка/обновление court_districts из API (JSON/GeoJSON) или локального файла.
    """

    def __init__(self, db_path: Optional[str] = None, timeout: int = 30):
        self.db_path = db_path or config.COURT_DISTRICTS_DB_PATH
        self.timeout = timeout

    def update_from_api(self, url: str) -> bool:
        """
        Загружает данные из API. Ожидается JSON: массив объектов с полями
        id, district_number, region, boundaries (массив координат или GeoJSON),
        address, phone, schedule, judge_name, court_name;
        либо GeoJSON FeatureCollection.

        :return: True при успешном обновлении
        """
        try:
            r = requests.get(url, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            logger.warning("DataUpdater: запрос к API не удался: %s", e)
            return False
        except json.JSONDecodeError as e:
            logger.warning("DataUpdater: ответ не JSON: %s", e)
            return False

        districts = self._normalize_response(data)
        if not districts:
            logger.warning("DataUpdater: в ответе нет записей судебных участков")
            return False

        db = Database(districts_db_path=self.db_path)
        db.init_schema()
        db.update_districts(districts)
        db.close()
        logger.info("DataUpdater: обновлено записей court_districts: %s", len(districts))
        return True

    def _normalize_response(self, data: Any) -> List[Dict[str, Any]]:
        """Приводит ответ API к списку записей court_districts."""
        if isinstance(data, list):
            return [self._normalize_row(d) for d in data if self._normalize_row(d)]
        if isinstance(data, dict):
            if data.get("type") == "FeatureCollection":
                features = data.get("features") or []
                from court_locator.data_loader import _feature_to_district
                out = []
                for i, f in enumerate(features):
                    row = _feature_to_district(f, feature_id=i + 1)
                    if row:
                        out.append(row)
                return out
            if "features" in data:
                return self._normalize_response(data["features"])
            if "data" in data:
                return self._normalize_response(data["data"])
            row = self._normalize_row(data)
            return [row] if row else []
        return []

    def _normalize_row(self, d: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(d, dict):
            return None
        boundaries = d.get("boundaries")
        if boundaries is None and "geometry" in d:
            geom = d["geometry"]
            if isinstance(geom, dict) and geom.get("type") == "Polygon":
                boundaries = geom.get("coordinates", [])[0] if geom.get("coordinates") else None
        if boundaries is None:
            return None
        raw_id = d.get("id")
        if raw_id is None:
            # Стабильный id по (region, district_number), чтобы INSERT OR REPLACE обновлял, а не дублировал
            key = (str(d.get("region") or ""), str(d.get("district_number") or d.get("number") or ""))
            raw_id = abs(hash(key)) % (2 ** 31)
        return {
            "id": raw_id,
            "district_number": d.get("district_number") or d.get("number") or "",
            "region": d.get("region") or "",
            "boundaries": boundaries,
            "address": d.get("address") or "",
            "phone": d.get("phone") or "",
            "schedule": d.get("schedule") or "",
            "judge_name": d.get("judge_name") or "",
            "court_name": d.get("court_name") or d.get("district_number") or "",
        }

    def update_from_geojson_file(self, path: Union[str, Path], clear_before: bool = False) -> int:
        """Обновление из локального GeoJSON файла (обёртка над load_geojson_to_db)."""
        from court_locator.data_loader import load_geojson_to_db
        return load_geojson_to_db(path, db_path=self.db_path, clear_before=clear_before)

    def update_from_nextgis(self, resource_id: Optional[int] = None, clear_before: bool = False) -> int:
        """
        Загрузка границ из NextGIS Map API (api.mapdev.io).
        Ресурс 137 — Россошанский судебный район (Воронежская обл.), 186 участков.
        """
        from court_locator.nextgis_source import load_nextgis_to_db
        rid = resource_id or getattr(config, "NEXTGIS_BOUNDARIES_RESOURCE_ID", 137)
        return load_nextgis_to_db(resource_id=rid, db_path=self.db_path, clear_before=clear_before)


def scheduled_update() -> bool:
    """
    Обновление из URL в конфиге. Вызывать по расписанию (schedule или cron).
    Сначала основной URL, при неудаче — fallback.
    """
    updater = DataUpdater()
    url = config.COURT_DATA_UPDATE_URL
    if url and updater.update_from_api(url):
        return True
    url_fb = config.COURT_DATA_UPDATE_URL_FALLBACK
    if url_fb:
        return updater.update_from_api(url_fb)
    return False
