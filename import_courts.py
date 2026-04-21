"""
Импорт CSV мировых судей в courts.sqlite.

Формат из docs/howto_fill_courts_db.md: разделитель ;, кодировка UTF-8.
Колонки (англ. или рус.): region/Регион, district/Район, section_num/Участок,
court_name/Наименование суда, address/Адрес, postal_index/Индекс, coordinates (опц.),
court_type/Тип суда, phone/Телефон, website/Сайт (опц.).
"""
import csv
import sqlite3
from pathlib import Path
from typing import Optional

from courts_db import DB_PATH, init_db

# Формат CSV из docs/howto_fill_courts_db.md
CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8"
CSV_COLUMNS_EN = ("region", "district", "section_num", "court_name", "address", "postal_index", "coordinates")
CSV_COLUMNS_RU = ("Регион", "Район", "Участок", "Наименование суда", "Адрес", "Индекс", "")
CSV_PATH = Path(__file__).parent / "data" / "magistrates.csv"


def _normalize_cell(value) -> Optional[str]:
    """Приведение значения из CSV к строке UTF-8 или None (защита от «чуши» и неверной кодировки)."""
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode(CSV_ENCODING)
        except Exception:
            return None
    s = str(value).strip()
    return s if s else None


def import_courts_from_csv(csv_path: Optional[Path] = None, append: bool = False):
    """Импорт CSV в courts. append=True: не очищать таблицу (дополнить), иначе таблица очищается перед вставкой."""
    csv_path = csv_path or CSV_PATH
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA encoding = 'UTF-8'")
    cur = conn.cursor()

    if not append:
        cur.execute("DELETE FROM courts")
    inserted = 0

    with csv_path.open("r", encoding=CSV_ENCODING) as f:
        reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
        for row in reader:
            region = _normalize_cell(row.get("region") or row.get("Регион"))
            district = _normalize_cell(row.get("district") or row.get("Район"))
            section_num = _normalize_cell(row.get("section_num") or row.get("Участок"))
            court_name = _normalize_cell(row.get("court_name") or row.get("Наименование суда"))
            address = _normalize_cell(row.get("address") or row.get("Адрес"))
            postal_index = _normalize_cell(row.get("postal_index") or row.get("Индекс"))
            coordinates = _normalize_cell(row.get("coordinates") or "")
            court_type = _normalize_cell(row.get("court_type") or row.get("Тип суда"))
            phone = _normalize_cell(row.get("phone") or row.get("Телефон"))
            website = _normalize_cell(row.get("website") or row.get("Сайт"))

            try:
                section_num_int = int(section_num) if section_num else None
            except (ValueError, TypeError):
                section_num_int = None

            cur.execute(
                """
                INSERT INTO courts (region, district, section_num, court_name, address, postal_index, coordinates, court_type, phone, website)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    region,
                    district,
                    section_num_int,
                    court_name,
                    address,
                    postal_index,
                    coordinates,
                    court_type,
                    phone,
                    website,
                ),
            )
            inserted += 1

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM courts")
    total = cur.fetchone()[0]
    conn.close()
    print(f"Импорт завершён из {csv_path}: вставлено строк {inserted}, всего в таблице courts: {total}")


if __name__ == "__main__":
    import_courts_from_csv()
