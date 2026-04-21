"""
Исправление «кривого» magistrates_dadata.csv:
  - регион подставляется из адреса (а не из запрошенного региона);
  - дедупликация по (court_name, address) — одна запись на суд.

Запуск из каталога parser:
  python normalize_magistrates_csv.py
  python normalize_magistrates_csv.py --input data/magistrates_dadata.csv --output data/magistrates_fixed.csv
"""
import csv
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
DEFAULT_INPUT = DATA_DIR / "magistrates_dadata.csv"
DEFAULT_OUTPUT = DATA_DIR / "magistrates_fixed.csv"


def _region_from_address(address: str) -> str:
    """Из адреса извлекает регион (Тамбовская обл → Тамбовская область и т.д.)."""
    if not address or not isinstance(address, str):
        return ""
    addr = address.strip()
    m = re.search(r"([А-Яа-яёЁ\-]+\s+обл\.?)", addr)
    if m:
        s = m.group(1).rstrip(".")
        return s.replace(" обл", " область").strip()
    if "Московская обл" in addr or "г Москва" in addr or ", Москва," in addr:
        return "Москва" if ("г Москва" in addr or ", Москва," in addr) else "Московская область"
    if "Санкт-Петербург" in addr or "СПб" in addr:
        return "Санкт-Петербург"
    m = re.search(r"([А-Яа-яёЁ\-]+\s+область)", addr)
    if m:
        return m.group(1).strip()
    m = re.search(r"([А-Яа-яёЁ\-]+\s+край)", addr)
    if m:
        return m.group(1).strip()
    m = re.search(r"(Республика [А-Яа-яёЁ\-]+)", addr)
    if m:
        return m.group(1).strip()
    m = re.search(r"([А-Яа-яёЁ\-]+\s+АО)", addr)
    if m:
        return m.group(1).strip()
    return ""


def _section_from_name(name: str) -> str:
    m = re.search(r"№\s*(\d+)", name or "", re.IGNORECASE)
    return m.group(1) if m else ""


def _district_from_name(name: str) -> str:
    """Из названия суда извлекает район (Тверского района → Тверской район и т.п.)."""
    if not name:
        return ""
    m = re.search(r"(\w+(?:ов|ев|ий|ой|ого|его)\s+района?)", name, re.IGNORECASE)
    if m:
        s = m.group(1).strip()
        s = re.sub(r"ого\s+района?$", "ий район", s, flags=re.I)
        s = re.sub(r"его\s+района?$", "ий район", s, flags=re.I)
        return s
    return ""


def normalize_csv(input_path: Path, output_path: Path, delimiter: str = ";"):
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists():
        print(f"Файл не найден: {input_path}", file=sys.stderr)
        return 0

    rows_by_key = {}  # (court_name, address) -> row
    with input_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        fieldnames = reader.fieldnames or ["region", "district", "section_num", "court_name", "address", "postal_index", "coordinates"]
        for r in reader:
            name = (r.get("court_name") or r.get("Наименование суда") or "").strip()
            address = (r.get("address") or r.get("Адрес") or "").strip()
            if not name:
                continue
            key = (name, address)
            if key in rows_by_key:
                continue
            region_from_addr = _region_from_address(address)
            region = (r.get("region") or r.get("Регион") or "").strip()
            # Если в адресе явно другой регион — берём из адреса (исправление «кривых» данных)
            if region_from_addr and region_from_addr != region:
                region = region_from_addr
            if not region and region_from_addr:
                region = region_from_addr
            section = r.get("section_num") or r.get("Участок") or _section_from_name(name)
            district = r.get("district") or r.get("Район") or _district_from_name(name)
            postal = r.get("postal_index") or r.get("Индекс") or ""
            coordinates = r.get("coordinates") or ""
            rows_by_key[key] = {
                "region": region,
                "district": district,
                "section_num": section,
                "court_name": name,
                "address": address,
                "postal_index": postal,
                "coordinates": coordinates,
            }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames_out = ["region", "district", "section_num", "court_name", "address", "postal_index", "coordinates"]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames_out, delimiter=delimiter)
        w.writeheader()
        w.writerows(rows_by_key.values())

    print(f"Записей было (в файле): ~{sum(1 for _ in input_path.open(encoding='utf-8')) - 1}")
    print(f"Уникальных судов после нормализации: {len(rows_by_key)}")
    print(f"Сохранено в {output_path}")
    return len(rows_by_key)


def main():
    import argparse
    p = argparse.ArgumentParser(description="Нормализация CSV мировых судов: регион из адреса, дедупликация")
    p.add_argument("--input", "-i", type=Path, default=DEFAULT_INPUT, help="Входной CSV")
    p.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT, help="Выходной CSV")
    p.add_argument("--delimiter", "-d", default=";", help="Разделитель (по умолчанию ;)")
    args = p.parse_args()
    normalize_csv(args.input, args.output, args.delimiter)


if __name__ == "__main__":
    main()
