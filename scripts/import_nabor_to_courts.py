"""
Импорт batch_outputs/nabor_normalized.csv в parser/courts.sqlite.
Запуск:
  python scripts/import_nabor_to_courts.py --csv batch_outputs/nabor_normalized.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser import courts_db


def read_rows(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [r for r in reader]


def main() -> None:
    parser = argparse.ArgumentParser(description="Import normalized courts data into courts.sqlite")
    parser.add_argument("--csv", default="batch_outputs/nabor_normalized.csv", help="Path to normalized CSV")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    rows = read_rows(csv_path)
    if not rows:
        raise SystemExit("CSV is empty")

    courts_db.init_db()
    conn = courts_db.sqlite3.connect(courts_db.DB_PATH)
    cur = conn.cursor()

    cur.execute("DELETE FROM courts")

    data = []
    for r in rows:
        sec = r.get("section_num") or ""
        try:
            sec_int = int(sec)
        except Exception:
            sec_int = None
        data.append(
            (
                sec_int,
                "Нижегородская область",  # region
                "",  # district (нет в наборе)
                sec_int,
                r.get("court_name") or "",
                r.get("address") or "",
                "",  # postal_index
                "",  # coordinates
                None,  # court_type
                r.get("phone") or "",
                r.get("site_url") or "",
                r.get("email") or "",
            )
        )

    cur.executemany(
        """
        INSERT OR REPLACE INTO courts
        (id, region, district, section_num, court_name, address, postal_index, coordinates, court_type, phone, website, email)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        data,
    )
    conn.commit()
    conn.close()
    print(f"Imported {len(data)} rows into courts.sqlite")


if __name__ == "__main__":
    main()
