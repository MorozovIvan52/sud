"""
Однократная подгрузка справочника dagalin в SQLite, если таблица пуста.
Источники (по приоритету): batch_outputs/dagalin_rf_mirovye_items.json,
затем самый свежий batch_outputs/dagalin_scrape_*.json.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("court_locator.dagalin_seed")

_ROOT = Path(__file__).resolve().parents[1]
_BATCH = _ROOT / "batch_outputs"


def _region_from_dagalin_url(url: str) -> Optional[str]:
    m = re.search(r"/courts/([^/]+)/wc/", url or "")
    return m.group(1) if m else None


def _rows_from_rf_catalog(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = (item.get("source_url") or "").strip()
        if not url:
            continue
        jt = item.get("jurisdiction_teaser") or item.get("jurisdiction_text") or ""
        rows.append(
            {
                "source_url": url,
                "region_code": item.get("region_code"),
                "court_name": (item.get("court_name") or item.get("name") or "").strip(),
                "jurisdiction_text": (jt or "").strip(),
            }
        )
    return rows


def _rows_from_scrape_dump(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        url = (item.get("source_url") or "").strip()
        if not url:
            continue
        boundary = (item.get("boundary_snippet") or "").strip()
        name = (item.get("name") or item.get("court_name") or "").strip()
        rows.append(
            {
                "source_url": url,
                "region_code": _region_from_dagalin_url(url),
                "court_name": name,
                "jurisdiction_text": boundary,
            }
        )
    return rows


def _load_json_list(path: Path) -> Optional[List[Dict[str, Any]]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("dagalin seed: cannot read %s: %s", path, e)
        return None
    if not isinstance(data, list):
        return None
    return data  # type: ignore[return-value]


def ensure_dagalin_catalog_loaded(db: Any) -> None:
    """
    Если dagalin_mirovye_courts пуста — заливает из локальных JSON в batch_outputs.
    """
    try:
        n = db.count_dagalin_mirovye_rows()
    except Exception as e:
        logger.warning("dagalin seed: count failed: %s", e)
        return
    if n > 0:
        return

    rf_path = _BATCH / "dagalin_rf_mirovye_items.json"
    rows: List[Dict[str, Any]] = []

    data = _load_json_list(rf_path)
    if data:
        rows = _rows_from_rf_catalog(data)
        logger.info("dagalin seed: loaded RF catalog %s (%d rows)", rf_path.name, len(rows))

    if not rows:
        pattern = str(_BATCH / "dagalin_scrape_*.json")
        candidates = sorted(glob.glob(pattern), key=lambda p: os.path.getmtime(p), reverse=True)
        for p in candidates[:3]:
            data = _load_json_list(Path(p))
            if not data:
                continue
            rows = _rows_from_scrape_dump(data)
            if rows:
                logger.info("dagalin seed: loaded scrape dump %s (%d rows)", Path(p).name, len(rows))
                break

    if not rows:
        logger.warning(
            "dagalin seed: no data (put dagalin_rf_mirovye_items.json in batch_outputs or run scrape)"
        )
        return

    chunk = 400
    for i in range(0, len(rows), chunk):
        db.upsert_dagalin_mirovye_courts(rows[i : i + chunk])
    logger.info("dagalin seed: upserted %d dagalin rows into sqlite", len(rows))
