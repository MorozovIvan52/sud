"""
Выгрузка списка мировых судов из DaData в CSV для последующего импорта в courts.sqlite.

Требуется DADATA_TOKEN в окружении или .env.
Запуск: из каталога parser: python dump_magistrates_to_csv.py

Результат: data/magistrates_dadata.csv (разделитель ;).
Импорт: скопировать в data/magistrates.csv и запустить import_courts.py
        или передать путь: import_courts_from_csv(Path("data/magistrates_dadata.csv")).
"""
import os
import re
import sys
import time
from pathlib import Path

# Для импорта court_locator при запуске из parser/
_script_dir = Path(__file__).resolve().parent
if str(_script_dir.parent) not in sys.path:
    sys.path.insert(0, str(_script_dir.parent))

from dadata_api import suggest_court, court_suggestion_to_result, DADATA_COURT_TYPE_MS

try:
    from regions_rf import ALL_REGIONS_RF
    REGIONS = list(ALL_REGIONS_RF.keys())  # все 85 субъектов РФ
except ImportError:
    REGIONS = [
        "Москва", "Санкт-Петербург", "Московская область", "Ленинградская область",
        "Краснодарский край", "Свердловская область", "Нижегородская область",
        "Республика Татарстан", "Ростовская область", "Самарская область",
    ]

SCRIPT_DIR = _script_dir
OUTPUT_CSV = SCRIPT_DIR / "data" / "magistrates_dadata.csv"


def _section_from_name(name: str) -> str:
    """Из названия суда извлекает номер участка (например «№ 185» -> 185)."""
    if not name:
        return ""
    m = re.search(r"№\s*(\d+)", name, re.IGNORECASE)
    return m.group(1) if m else ""


def _district_from_name(name: str) -> str:
    """Пытается извлечь район из названия (например «Тверского района»)."""
    if not name:
        return ""
    m = re.search(r"(\w+(?:ов|ев|ий|ой)\s+район)", name, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _region_from_address(address: str) -> str:
    """
    Извлекает регион из строки адреса (каноническое имя для courts.region).
    Использует court_locator.address_parser при доступности, иначе встроенную логику.
    """
    if not address or not isinstance(address, str):
        return ""
    try:
        from court_locator.address_parser import extract_region
        r = extract_region(address)
        return r or ""
    except ImportError:
        pass
    addr = address.strip()
    parts = [p.strip() for p in re.split(r"[,;]", addr, maxsplit=3)]
    for p in parts:
        if not p:
            continue
        p = re.sub(r"^\d{6}\s*,?\s*", "", p).strip() or p
        if " обл" in p.lower() or p.lower().endswith(" обл"):
            return re.sub(r"\s+обл\.?\s*$", " область", p, flags=re.IGNORECASE).strip() or p.replace(" обл", " область")
        if "край" in p.lower() or "республика" in p.lower() or "ао" in p.lower():
            return p
        if "москва" in p.lower() and "область" not in p.lower():
            return "Москва" if "г " in p.lower() or p.lower() == "москва" else p
        if "санкт-петербург" in p.lower() or "спб" in p.lower():
            return "Санкт-Петербург"
        if "область" in p.lower():
            return p
    return ""


def dump_magistrates_to_csv(
    regions: list = None,
    output_path: Path = None,
    delay_sec: float = 0.5,
    count_per_request: int = 20,
) -> Path:
    """
    Перебирает регионы, запрашивает у DaData мировые суды (court_type=MS),
    дедуплицирует по названию и сохраняет CSV.
    """
    regions = regions or REGIONS
    output_path = output_path or OUTPUT_CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)

    token = (os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or "").strip()
    if not token:
        raise RuntimeError("Задайте DADATA_TOKEN или DADATA_API_KEY в .env или окружении")

    seen = set()  # (court_name, address) — дедупликация по суду, чтобы не дублировать один суд на каждый запрошенный регион
    rows = []

    for region in regions:
        suggestions = suggest_court(
            query="мировой суд",
            region=region,
            count=count_per_request,
            court_type=DADATA_COURT_TYPE_MS,
        )
        for s in suggestions:
            row = court_suggestion_to_result(s)
            if not row:
                continue
            name = (row.get("court_name") or "").strip()
            address = row.get("address") or ""
            if not name:
                continue
            key = (name, address)
            if key in seen:
                continue
            seen.add(key)
            # Регион: адрес → название суда (часто там «… Тамбовской области», а адрес без региона) → DaData → регион запроса
            region_name = (
                _region_from_address(address)
                or _region_from_address(name)
                or (row.get("region") or "").strip()
                or region
            )
            postal = row.get("postal_index") or ""
            section = _section_from_name(name)
            district = _district_from_name(name)
            rows.append({
                "region": region_name,
                "district": district,
                "section_num": section,
                "court_name": name,
                "address": address,
                "postal_index": postal,
                "coordinates": "",
            })
        time.sleep(delay_sec)

    with output_path.open("w", encoding="utf-8", newline="") as f:
        import csv
        w = csv.DictWriter(f, fieldnames=["region", "district", "section_num", "court_name", "address", "postal_index", "coordinates"], delimiter=";")
        w.writeheader()
        w.writerows(rows)

    print(f"Сохранено {len(rows)} записей в {output_path}")
    return output_path


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(SCRIPT_DIR.parent / ".env")
    dump_magistrates_to_csv()
