#!/usr/bin/env python3
"""
Создаёт локальные SQLite-файлы со схемой (после git clone *.sqlite в .gitignore).

  python scripts/bootstrap_local_databases.py
  python scripts/bootstrap_local_databases.py --seed

Дальше наполните courts: см. docs/howto_fill_courts_db.md или
  cd parser && python import_courts.py  (нужен parser/data/magistrates.csv)

Полигоны: scripts/load_yandex_geojson_to_court_districts.py или API NextGIS.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "parser"))


def main() -> int:
    p = argparse.ArgumentParser(description="Инициализация parser/*.sqlite")
    p.add_argument(
        "--seed",
        action="store_true",
        help="Вставить демо-записи Москва/СПб в courts (для теста, не для продакшена)",
    )
    args = p.parse_args()

    from courts_db import DB_PATH, get_courts_count, init_db, seed_example_data
    from court_locator.database import Database

    init_db()
    if args.seed:
        seed_example_data()

    db = Database()
    db.init_schema()
    db.close()

    n = get_courts_count()
    print(f"courts.sqlite:      {DB_PATH.resolve()} (строк в courts: {n})")
    print(f"court_districts:    {db.districts_path.resolve()} (схема создана)")
    if n == 0 and not args.seed:
        print("\nТаблица courts пуста. Импорт CSV: docs/howto_fill_courts_db.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
