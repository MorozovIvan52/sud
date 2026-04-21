#!/usr/bin/env python3
"""
Проверка структуры и данных courts.sqlite (диагностика «чуши» при заполнении).

Запуск из корня проекта:
  python parser/verify_courts_db.py

Использует PRAGMA table_info(courts) и выводит первые записи для проверки кодировки и типов.
"""
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / "courts.sqlite"


def main():
    if not DB_PATH.exists():
        print(f"Файл не найден: {DB_PATH}")
        print("Создайте БД: python parser/run_courts_collect_geocode_load.py --regions \"Нижегородская область\" --no-geocode")
        sys.exit(1)
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from courts_db import init_db
    init_db()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA encoding = 'UTF-8'")
    cur = conn.cursor()

    # Структура таблицы courts (как ожидает court_locator и parser)
    cur.execute("PRAGMA table_info(courts)")
    columns = cur.fetchall()
    if not columns:
        print("Таблица courts не найдена. Выполните: from courts_db import init_db; init_db()")
        conn.close()
        sys.exit(1)

    print("Структура таблицы courts (ожидаемая в проекте):")
    print("  cid | name          | type    | notnull | default | pk")
    print("  ----+---------------+--------+---------+---------+---")
    for col in columns:
        cid, name, type_, notnull, default, pk = col
        print(f"  {cid:<3} | {name:<13} | {type_:<6} | {notnull:<7} | {str(default):<7} | {pk}")
    print()

    cur.execute("SELECT COUNT(*) FROM courts")
    total = cur.fetchone()[0]
    print(f"Всего записей: {total}")
    if total == 0:
        conn.close()
        return

    # Примеры данных (проверка на «чушь» и кодировку; court_type, phone, website — при наличии)
    cur.execute("SELECT id, region, district, section_num, court_name, address, coordinates, court_type, phone, website FROM courts LIMIT 3")
    rows = cur.fetchall()
    names = [d[0] for d in cur.description]
    print("\nПримеры записей (первые 3):")
    for i, row in enumerate(rows, 1):
        print(f"  --- Запись {i} ---")
        for j, name in enumerate(names):
            val = row[j]
            if val is not None and isinstance(val, str) and len(val) > 60:
                val = val[:57] + "..."
            print(f"    {name}: {val!r} (type={type(val).__name__})")
    conn.close()
    print("\nЕсли вместо русского текста видны кракозябры — проверьте кодировку CSV (UTF-8) и PRAGMA encoding.")


if __name__ == "__main__":
    main()
