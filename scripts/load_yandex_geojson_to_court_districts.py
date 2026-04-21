"""
Импорт GeoJSON (в т.ч. из Яндекс Конструктора карт) в parser/court_districts.sqlite.

Примеры:
  python scripts/load_yandex_geojson_to_court_districts.py --geojson "C:\\data\\court_districts.geojson" --clear-before
  python scripts/load_yandex_geojson_to_court_districts.py --geojson "C:\\data\\court_districts.geojson" --db "parser\\court_districts.sqlite"
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from court_locator.data_loader import load_geojson_to_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Load court districts GeoJSON into SQLite DB.")
    parser.add_argument("--geojson", required=True, help="Path to GeoJSON file exported from map constructor.")
    parser.add_argument(
        "--db",
        default="parser/court_districts.sqlite",
        help="Target SQLite DB path (default: parser/court_districts.sqlite).",
    )
    parser.add_argument(
        "--clear-before",
        action="store_true",
        help="Delete existing rows in court_districts before import.",
    )
    args = parser.parse_args()

    geojson_path = Path(args.geojson)
    if not geojson_path.exists():
        raise SystemExit(f"GeoJSON not found: {geojson_path}")

    loaded = load_geojson_to_db(
        geojson_path=geojson_path,
        db_path=args.db,
        clear_before=args.clear_before,
    )
    print(f"Imported districts: {loaded}")
    print(f"Target DB: {Path(args.db).resolve()}")


if __name__ == "__main__":
    main()

