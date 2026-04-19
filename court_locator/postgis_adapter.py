"""
Адаптер PostGIS для поиска суда по координатам (ST_Contains).

1) Таблица court_districts (классическая схема parserSupreme / NextGIS → PostGIS).
2) Таблицы world_courts_zones + world_courts (схема GISmap/) — автоматический fallback,
   если court_districts пуста или отсутствует, при том же PG_DSN.

Переменные:
- PG_DSN — подключение к PostgreSQL с PostGIS.
- COURTS_SPATIAL_BACKEND=postgis — рекомендуемое включение (см. court_locator.config); иначе устаревшее COURTS_DB_BACKEND=postgis.
- POSTGIS_SKIP_GISMAP_ZONES=1 — не искать в world_courts_zones.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

PG_DSN = os.getenv("PG_DSN", "postgresql://postgres:postgres@localhost:5432/courts")


def _skip_gismap_zones() -> bool:
    v = (os.getenv("POSTGIS_SKIP_GISMAP_ZONES") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _infer_section_num(zone_name: Any, district_name: Any, court_id: Any) -> int:
    for s in (zone_name, district_name):
        if s is None:
            continue
        m = re.search(r"(\d+)", str(s))
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    if court_id is not None:
        try:
            return int(court_id)
        except (TypeError, ValueError):
            pass
    return 0


def _spatial_tables_status(conn) -> Tuple[bool, bool]:
    """(есть court_districts с колонкой boundary, есть world_courts_zones с geom)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            EXISTS (
                SELECT 1
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON c.table_schema = t.table_schema AND c.table_name = t.table_name
                WHERE c.table_schema = 'public'
                  AND t.table_type = 'BASE TABLE'
                  AND c.table_name = 'court_districts'
                  AND c.column_name = 'boundary'
            ),
            EXISTS (
                SELECT 1
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON c.table_schema = t.table_schema AND c.table_name = t.table_name
                WHERE c.table_schema = 'public'
                  AND t.table_type = 'BASE TABLE'
                  AND c.table_name = 'world_courts_zones'
                  AND c.column_name = 'geom'
            )
        """
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        return False, False
    return bool(row[0]), bool(row[1])


def find_court_by_coordinates_postgis(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Поиск участка по координатам: сначала court_districts, затем (опционально) GISmap world_courts_zones.
    Возвращает dict с ключами court_name, address, region, section_num, source.
    """
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        return None

    dsn = os.getenv("PG_DSN", PG_DSN)
    try:
        conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)
        has_cd, has_wcz = _spatial_tables_status(conn)

        row = None
        if has_cd:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT court_name, court_code, address, region, section_num, district_type
                    FROM court_districts
                    WHERE boundary IS NOT NULL
                      AND ST_Contains(boundary, ST_SetSRID(ST_Point(%s, %s), 4326))
                      AND (valid_from IS NULL OR valid_from <= CURRENT_DATE)
                      AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
                    ORDER BY CASE district_type
                        WHEN 'world' THEN 1
                        WHEN 'district' THEN 2
                        WHEN 'regional' THEN 3
                        ELSE 4
                    END
                    LIMIT 1
                    """,
                    (lon, lat),
                )
                row = cur.fetchone()
            except Exception:
                conn.rollback()
                cur.close()
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT court_name, court_code, address, region, section_num, NULL AS district_type
                    FROM court_districts
                    WHERE boundary IS NOT NULL
                      AND ST_Contains(boundary, ST_SetSRID(ST_Point(%s, %s), 4326))
                    LIMIT 1
                    """,
                    (lon, lat),
                )
                row = cur.fetchone()
            cur.close()

        if row:
            conn.close()
            return {
                "court_name": row.get("court_name") or "",
                "address": row.get("address") or "",
                "region": row.get("region") or "",
                "section_num": row.get("section_num") or 0,
                "source": "postgis",
            }

        if not _skip_gismap_zones() and has_wcz:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    w.name AS court_name,
                    w.address AS address,
                    w.district_name AS district_name,
                    w.court_id AS court_id,
                    z.zone_name AS zone_name
                FROM world_courts_zones z
                JOIN world_courts w ON w.court_id = z.court_id
                WHERE z.geom IS NOT NULL
                  AND ST_Contains(z.geom, ST_SetSRID(ST_Point(%s, %s), 4326))
                ORDER BY ST_Area(z.geom) ASC NULLS LAST
                LIMIT 1
                """,
                (lon, lat),
            )
            gz = cur.fetchone()
            cur.close()
            conn.close()
            if gz:
                sn = _infer_section_num(
                    gz.get("zone_name"),
                    gz.get("district_name"),
                    gz.get("court_id"),
                )
                region = (gz.get("district_name") or "").strip()
                return {
                    "court_name": (gz.get("court_name") or "").strip(),
                    "address": (gz.get("address") or "").strip(),
                    "region": region,
                    "section_num": sn,
                    "source": "postgis_gismap_zones",
                }

        conn.close()
    except Exception:
        pass
    return None


def is_postgis_available() -> bool:
    """
    True, если доступен PostgreSQL с расширением postgis и есть пространственные данные:
    либо court_districts.boundary, либо world_courts_zones.geom (GISmap).
    """
    try:
        import psycopg2
        conn = psycopg2.connect(os.getenv("PG_DSN", PG_DSN))
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
        if cur.fetchone() is None:
            cur.close()
            conn.close()
            return False
        has_cd, has_wcz = _spatial_tables_status(conn)
        cur.close()
        conn.close()
        return has_cd or has_wcz
    except Exception:
        return False
