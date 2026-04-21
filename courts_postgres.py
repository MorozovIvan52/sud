"""
Реализация CourtsRepository для PostgreSQL.
Переменные окружения: COURTS_DB_BACKEND=postgres, PG_DSN=...
"""
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from courts_repo import CourtsRepository


class PostgresCourtsRepository(CourtsRepository):
    def __init__(self, db_url: Optional[str] = None):
        self.dsn = db_url or os.getenv(
            "PG_DSN",
            "dbname=courts user=postgres password=postgres host=localhost port=5432",
        )

    @contextmanager
    def get_connection(self):
        conn = psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)
        try:
            yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS courts (
                        id SERIAL PRIMARY KEY,
                        region TEXT,
                        district TEXT,
                        section_num INTEGER,
                        court_name TEXT,
                        address TEXT,
                        postal_index TEXT,
                        coordinates TEXT
                    );
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_courts_region_district ON courts(region, district)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_courts_section ON courts(section_num)"
                )
            conn.commit()

    def get_court_by_district(self, region: str, district: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, region, district, section_num, court_name, address, postal_index, coordinates
                    FROM courts
                    WHERE LOWER(region) = LOWER(%s)
                      AND LOWER(district) = LOWER(%s)
                    LIMIT 1
                    """,
                    (region, district),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def get_all_courts(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, region, district, section_num, court_name, address, postal_index, coordinates FROM courts"
                )
                rows = cur.fetchall()
                return [dict(r) for r in rows]
