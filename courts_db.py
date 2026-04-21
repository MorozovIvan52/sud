import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List, Union


def resolve_courts_sqlite(script_or_dir: Optional[Union[Path, str]] = None) -> Path:
    """
    Путь к parser/courts.sqlite от любого места в репозитории.

    Без аргументов — как раньше: файл рядом с модулем (parser/courts.sqlite).

    Из своего скрипта передайте Path(__file__), тогда каталог скрипта может быть корнем проекта,
    каталогом parser/, scripts/ и т.д. Поиск: courts.sqlite рядом со скриптом в parser/,
    затем подъём по родителям до .../parser/courts.sqlite.
    """
    if script_or_dir is None:
        anchor = Path(__file__).resolve().parent
    else:
        p = Path(script_or_dir).resolve()
        # Каталог скрипта: и для существующего .py, и если передали путь к файлу по шаблону
        if p.is_file() or (p.suffix.lower() in (".py", ".pyw") and not p.is_dir()):
            anchor = p.parent
        else:
            anchor = p
    direct = anchor / "courts.sqlite"
    if direct.is_file():
        return direct
    for base in [anchor, *anchor.parents]:
        cand = base / "parser" / "courts.sqlite"
        if cand.is_file():
            return cand
    for base in [anchor, *anchor.parents]:
        if (base / "parser").is_dir():
            return base / "parser" / "courts.sqlite"
    return anchor / "parser" / "courts.sqlite"


DB_PATH = resolve_courts_sqlite()


def _migrate_add_columns(cur):
    """Добавляем court_type, phone, website если их ещё нет (миграция под исследование источников)."""
    for col_name, col_type in [
        ("court_type", "TEXT"),
        ("phone", "TEXT"),
        ("website", "TEXT"),
        ("email", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE courts ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError as e:
            if "duplicate" not in str(e).lower():
                raise


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA encoding = 'UTF-8'")
    cur = conn.cursor()
    cur.execute(
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
    _migrate_add_columns(cur)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_courts_region ON courts(region);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_courts_district ON courts(district);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_courts_region_district ON courts(region, district);")
    conn.commit()
    conn.close()


def seed_example_data():
    """
    Заглушка: для продакшена сюда грузим актуальный CSV/JSON мировых судей
    по конкретному региону.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Пример для Москвы и СПб — для тестов
    cur.execute("DELETE FROM courts")

    sample_rows = [
        (
            1,
            "Москва",
            "Тверской",
            123,
            "Мировой судья судебного участка № 123 Тверского района г. Москвы",
            "125009, г. Москва, ул. Правосудия, д. 10",
            "125009",
            "55.7558,37.6176",
        ),
        (
            2,
            "Санкт-Петербург",
            "Центральный",
            45,
            "Мировой судья судебного участка № 45 Центрального района г. Санкт-Петербурга",
            "191025, г. Санкт-Петербург, Невский проспект, д. 10",
            "191025",
            "59.9343,30.3351",
        ),
    ]
    cur.executemany(
        """
        INSERT INTO courts (id, region, district, section_num, court_name, address, postal_index, coordinates)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sample_rows,
    )
    conn.commit()
    conn.close()


def get_court_by_district(region: str, district: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM courts
        WHERE LOWER(region) = LOWER(?)
          AND LOWER(district) = LOWER(?)
        LIMIT 1
        """,
        (region, district),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def get_all_courts() -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM courts")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_courts_count(db_path: Optional[Path] = None) -> int:
    """Количество записей в таблице courts (для проверки после загрузки)."""
    path = db_path or DB_PATH
    if not path.exists():
        return 0
    conn = sqlite3.connect(path)
    n = conn.execute("SELECT COUNT(*) FROM courts").fetchone()[0]
    conn.close()
    return n


def get_courts_geo_count() -> int:
    """Количество записей с координатами в courts_geo.sqlite."""
    geo_path = Path(__file__).parent / "courts_geo.sqlite"
    if not geo_path.exists():
        return 0
    conn = sqlite3.connect(geo_path)
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM courts_geo WHERE lat IS NOT NULL AND lon IS NOT NULL"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        n = 0
    finally:
        conn.close()
    return n
