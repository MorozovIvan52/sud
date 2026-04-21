# generate_courts_db.py — генерация courts.sqlite с мировыми судами и кодами паспортов.
# Запуск: python generate_courts_db.py (один раз, затем парсер использует courts.sqlite)

import sqlite3
from pathlib import Path
from typing import Dict, List, Any

from courts_db import DB_PATH, init_db


def load_courts_from_open_sources() -> List[Dict[str, Any]]:
    """Загружает данные из открытых источников (примеры; полная БД ~85к — из GitHub/Excel)."""
    courts = []

    # Пример: Москва
    moscow_courts = [
        {
            "region": "Москва",
            "district": "Таганский",
            "section_num": 123,
            "name": "Мировой судья судебного участка № 123 Таганского района г. Москвы",
            "address": "г. Москва, ул. Таганская, д. 10",
            "index": "109240",
        },
        {
            "region": "Москва",
            "district": "Тверской",
            "section_num": 123,
            "name": "Мировой судья судебного участка № 123 Тверского района г. Москвы",
            "address": "125009, г. Москва, ул. Правосудия, д. 10",
            "index": "125009",
        },
        {
            "region": "Москва",
            "district": "ЮЗАО",
            "section_num": 456,
            "name": "Мировой судья судебного участка № 456 ЮЗАО г. Москвы",
            "address": "г. Москва, ул. Профсоюзная, д. 150",
            "index": "117420",
        },
    ]
    courts.extend(moscow_courts)

    # Пример: Санкт-Петербург
    spb_courts = [
        {
            "region": "Санкт-Петербург",
            "district": "Центральный",
            "section_num": 12,
            "name": "Мировой судья судебного участка № 12 Центрального района г. Санкт-Петербурга",
            "address": "г. Санкт-Петербург, Невский пр., д. 100",
            "index": "191025",
        },
        {
            "region": "Санкт-Петербург",
            "district": "Центральный",
            "section_num": 45,
            "name": "Мировой судья судебного участка № 45 Центрального района г. Санкт-Петербурга",
            "address": "191025, г. Санкт-Петербург, Невский проспект, д. 10",
            "index": "191025",
        },
    ]
    courts.extend(spb_courts)

    return courts


def load_passport_codes(cursor: sqlite3.Cursor) -> None:
    """Загружает коды подразделений паспортов (префикс 3 цифры → регион)."""
    codes = [
        ("770", "Москва", "г. Москва"),
        ("771", "Московская область", "Московская обл."),
        ("450", "Москва", "г. Москва"),
        ("451", "Москва", "г. Москва"),
        ("504", "Санкт-Петербург", "г. Санкт-Петербург"),
        ("780", "Санкт-Петербург", "г. Санкт-Петербург"),
        ("773", "Краснодарский край", "Краснодарский край"),
        ("502", "Свердловская область", "Свердловская обл."),
        ("524", "Нижегородская область", "Нижегородская обл."),
        ("550", "Новосибирская область", "Новосибирская обл."),
        ("590", "Пермский край", "Пермский край"),
        ("610", "Ростовская область", "Ростовская обл."),
        ("630", "Самарская область", "Самарская обл."),
        ("360", "Республика Татарстан", "Республика Татарстан"),
        ("160", "Республика Башкортостан", "Республика Башкортостан"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO passport_codes (code_prefix, region, oblast) VALUES (?, ?, ?)",
        codes,
    )


def create_courts_database(db_path: Path = None) -> int:
    """
    Создаёт courts.sqlite: таблицы courts и passport_codes, заполняет примерами.
    Возвращает количество записей в таблице courts.
    """
    db_path = db_path or DB_PATH
    init_db()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Таблица кодов паспортов (дополнительно к courts)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS passport_codes (
            code_prefix TEXT PRIMARY KEY,
            region TEXT,
            oblast TEXT
        )
        """
    )

    # Очистка и заполнение courts
    cursor.execute("DELETE FROM courts")

    print("Загрузка данных судов...")
    courts_data = load_courts_from_open_sources()

    print("Загрузка кодов паспортов...")
    load_passport_codes(cursor)

    print("Заполнение БД...")
    for court in courts_data:
        cursor.execute(
            """
            INSERT INTO courts (region, district, section_num, court_name, address, postal_index, coordinates)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                court.get("region"),
                court.get("district"),
                court.get("section_num"),
                court.get("name"),
                court.get("address"),
                court.get("index", ""),
                court.get("coordinates", ""),
            ),
        )

    conn.commit()
    count = len(courts_data)
    print(f"БД создана: {db_path} ({count} записей судов)")
    conn.close()
    return count


if __name__ == "__main__":
    create_courts_database()
