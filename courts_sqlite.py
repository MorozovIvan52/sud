"""
Реализация CourtsRepository для SQLite.
Использует тот же courts.sqlite, что и courts_db (init_db, seed_example_data, import_courts).
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List

from courts_repo import CourtsRepository

DB_PATH = Path(__file__).parent / "courts.sqlite"


class SqliteCourtsRepository(CourtsRepository):
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS courts (
                    id INTEGER PRIMARY KEY,
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
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_courts_region_district ON courts(region, district)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_courts_section ON courts(section_num)"
            )
            conn.commit()

    def get_court_by_district(self, region: str, district: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM courts
                WHERE LOWER(region) = LOWER(?)
                  AND LOWER(district) = LOWER(?)
                LIMIT 1
                """,
                (region, district),
            )
            row = cur.fetchone()
            if not row:
                return None
            return dict(row)

    def get_all_courts(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM courts")
            rows = cur.fetchall()
            return [dict(r) for r in rows]
