#!/usr/bin/env python3
"""
Диагностика окружения перед определением подсудности (без вывода секретов).

  python scripts/diagnose_jurisdiction.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "parser"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _yes(v: str | None) -> str:
    return "да" if (v or "").strip() else "нет"


def main() -> int:
    print("=== Диагностика подсудности (parserSupreme) ===\n")

    from court_locator import config as cl_config
    from court_locator.config import use_postgis_for_spatial_search

    courts_path = Path(cl_config.COURTS_DB_PATH)
    dist_path = Path(cl_config.COURT_DISTRICTS_DB_PATH)
    print("Пути к БД:")
    print(f"  courts.sqlite          {courts_path.resolve()} — существует: {courts_path.exists()}")
    print(f"  court_districts.sqlite {dist_path.resolve()} — существует: {dist_path.exists()}")

    try:
        from courts_db import get_courts_count

        n_c = get_courts_count()
        print(f"\nТаблица courts: строк ~ {n_c}")
        if n_c == 0:
            print("  ⚠ Пусто — подсудность по району не сработает. Импорт: docs/howto_fill_courts_db.md")
    except Exception as e:
        print(f"\n⚠ Не удалось прочитать courts: {e}")

    try:
        from court_locator.database import Database

        db = Database()
        db.init_schema()
        districts = db.get_all_districts()
        with_poly = sum(1 for d in districts if d.get("boundaries"))
        print(f"\nУчастков в court_districts: {len(districts)}, с полигоном: {with_poly}")
        db.close()
    except Exception as e:
        print(f"\n⚠ court_districts: {e}")

    print("\nКлючи и режимы (значения не показываются):")
    print(f"  YANDEX_GEO_KEY задан:     {_yes(os.getenv('YANDEX_GEO_KEY') or os.getenv('YANDEX_GEOCODER_API_KEY'))}")
    print(f"  DADATA_TOKEN задан:       {_yes(os.getenv('DADATA_TOKEN') or os.getenv('DADATA_API_KEY'))}")
    print(f"  COURTS_DB_BACKEND:        {(os.getenv('COURTS_DB_BACKEND') or 'sqlite').strip()}")
    print(f"  Пространственный PostGIS: {'да' if use_postgis_for_spatial_search() else 'нет'}")
    print(f"  PG_DSN задан:             {_yes(os.getenv('PG_DSN'))}")

    print("\nПробный вызов process_debtor (адрес в Москве, ~5–30 с)...")
    try:
        from batch_processing.services.pipeline import process_debtor

        r = process_debtor(fio="Диагностика", address="г. Москва, ул. Тверская, д. 1", debt_amount=None)
        court = (r.get("Наименование суда") or "").strip()
        typ = (r.get("Тип производства") or "").strip()
        src = (r.get("Источник данных") or "").strip()
        print(f"  Наименование суда: {court[:80] or '(пусто)'}")
        print(f"  Тип производства:  {typ[:100]}")
        print(f"  Источник данных:   {src[:80] or '(пусто)'}")
        if "ERROR" in typ.upper():
            print("  ⚠ Ответ с ошибкой — смотрите текст выше и раздел «Почему не нашёл» в docs/USER_GUIDE_BEGINNER_RU.md")
    except Exception as e:
        print(f"  ⚠ Исключение: {e}")

    print("\nГотово. Полное руководство: docs/USER_GUIDE_BEGINNER_RU.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
