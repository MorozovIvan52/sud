"""
Импорт текстовых правил (law_rules) из CSV в court_districts.sqlite.

Формат CSV (utf-8):
id,section_num,region,area_text,street_pattern,house_from,house_to,law_reference

Запуск:
  python scripts/import_law_rules_csv.py --csv path/to/rules.csv --db parser/court_districts.sqlite --clear-before
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List, Dict, Any

from court_locator.database import Database


def read_csv(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not any(row.values()):
                continue
            def _oint(key: str):
                v = (row.get(key) or "").strip()
                return int(v) if v else None

            rows.append(
                {
                    "id": row.get("id"),
                    "section_num": row.get("section_num"),
                    "region": row.get("region"),
                    "area_text": row.get("area_text"),
                    "street_pattern": row.get("street_pattern"),
                    "house_from": _oint("house_from"),
                    "house_to": _oint("house_to"),
                    "house_parity": (row.get("house_parity") or "").strip() or None,
                    "house_suffix": (row.get("house_suffix") or "").strip() or None,
                    "house_step": _oint("house_step"),
                    "law_reference": row.get("law_reference"),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Import law_rules from CSV into court_districts.sqlite")
    parser.add_argument("--csv", required=True, help="Path to CSV file with rules.")
    parser.add_argument("--db", default="parser/court_districts.sqlite", help="Target SQLite DB path.")
    parser.add_argument("--clear-before", action="store_true", help="Delete existing rules before import.")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    rules = read_csv(csv_path)
    if not rules:
        raise SystemExit("No rules found in CSV")

    db = Database(districts_db_path=args.db)
    db.init_schema()
    db.update_law_rules(rules, clear_before=args.clear_before)
    db.close()
    print(f"Imported {len(rules)} rules into {args.db}")


if __name__ == "__main__":
    main()
