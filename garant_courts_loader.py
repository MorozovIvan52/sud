#!/usr/bin/env python3
"""
Загрузка данных о судах с сайта ГАРАНТ (base.garant.ru/152940).

Источник: «Адреса и телефоны судов Российской Федерации»
  https://base.garant.ru/152940/

Загружаются разделы справочника: верховные суды субъектов (таблица), кассационные,
апелляционные, арбитражные округа и апелляционные арбитражные (блочная разметка).
Данные дополняют таблицу courts в courts.sqlite (court_type, phone, website с версии схемы с миграцией).

Запуск из корня проекта:
  python parser/garant_courts_loader.py
  python parser/garant_courts_loader.py --dry-run
  python parser/garant_courts_loader.py --sections verhovnye  # только верховные

Требуется: requests, beautifulsoup4 (pip install requests beautifulsoup4).
"""
import re
import sys
from pathlib import Path
from typing import List, Dict, Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Установите: pip install requests beautifulsoup4")
    sys.exit(1)

GARANT_152940_URL = "https://base.garant.ru/152940/"
USER_AGENT = "ParserSupreme/1.0 (courts loader)"

# Разделы ГАРАНТ: (url, тип суда, способ парсинга, ключ для --sections)
GARANT_SECTIONS = [
    ("https://base.garant.ru/3919615/", "Верховные краевые, областные, республиканские суды общей юрисдикции", "table", "verhovnye"),
    ("https://base.garant.ru/77682883/", "Кассационные суды общей юрисдикции", "blocks", "kassation"),
    ("https://base.garant.ru/77682884/", "Апелляционные суды общей юрисдикции", "blocks", "apellacia"),
    ("https://base.garant.ru/152083/", "Арбитражные суды округов", "blocks", "arbitr_okrug"),
    ("https://base.garant.ru/3984031/", "Арбитражные апелляционные суды", "blocks", "arbitr_apell"),
]


def _normalize_region_from_court_name(court_name: str) -> str:
    """Из названия суда извлекает регион для соответствия ALL_REGIONS_RF."""
    try:
        from regions_rf import ALL_REGIONS_RF
    except ImportError:
        from parser.regions_rf import ALL_REGIONS_RF

    name = (court_name or "").strip()
    if not name:
        return ""

    # Прямое совпадение
    for region in ALL_REGIONS_RF:
        if region.lower() in name.lower():
            return region

    # «Верховный суд Республики Адыгея» -> Республика Адыгея
    m = re.search(r"Республики\s+([^»]+?)(?:\s*\-?\s*Алания)?(?:\s*$|,)", name, re.I)
    if m:
        sub = m.group(1).strip()
        for region in ALL_REGIONS_RF:
            if sub in region or region in sub or (sub.replace(" (Якутия)", "") in region):
                return region
        if "Алания" in name or "Осетия" in sub:
            return "Республика Северная Осетия"
        if "Якутия" in sub:
            return "Республика Саха (Якутия)"
        return f"Республика {sub}"

    # «Нижегородский областной суд» -> Нижегородская область
    m = re.search(r"(\w+)(?:ский|кой)\s+областной", name, re.I)
    if m:
        base = m.group(1)
        for region in ALL_REGIONS_RF:
            if region.startswith(base) and "область" in region:
                return region

    # «Алтайский краевой» -> Алтайский край
    m = re.search(r"(\w+)(?:ский|кой)\s+краевой", name, re.I)
    if m:
        base = m.group(1)
        for region in ALL_REGIONS_RF:
            if region.startswith(base) and "край" in region:
                return region

    # Москва, СПб
    if "Москва" in name and "область" not in name.lower():
        return "Москва"
    if "Петербург" in name or "Санкт-Петербург" in name:
        return "Санкт-Петербург"

    return ""


def _extract_postal_index(address: str) -> str:
    """Из адреса извлекает почтовый индекс (6 цифр в начале)."""
    if not address:
        return ""
    m = re.match(r"^\s*(\d{6})", address.strip())
    return m.group(1) if m else ""


def _parse_garant_table(soup: BeautifulSoup, court_type: str) -> List[Dict[str, Any]]:
    """Парсит страницу ГАРАНТ с таблицей (напр. 3919615). Возвращает список dict с court_name, address, region, postal_index, phone, url, court_type."""
    rows = []
    tables = soup.find_all("table")
    for table in tables:
        trs = table.find_all("tr")
        for idx, tr in enumerate(trs):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 5:
                continue
            texts = [c.get_text(separator=" ", strip=True) for c in cells]
            name = texts[0] if texts else ""
            if idx == 0:
                continue
            if not name or len(name) < 5:
                continue
            name_lower = name.lower()
            if "верховный" not in name_lower and "краевой" not in name_lower and "областной" not in name_lower and "городской" not in name_lower:
                continue
            addr = texts[4] if len(texts) > 4 else ""
            phone = texts[3] if len(texts) > 3 else ""
            url = texts[5] if len(texts) > 5 else ""
            if url and not re.match(r"^https?://", url):
                url = ""
            region = _normalize_region_from_court_name(name)
            rows.append({
                "court_name": name,
                "address": addr or "",
                "region": region,
                "postal_index": _extract_postal_index(addr),
                "phone": phone or "",
                "url": url or "",
                "court_type": court_type,
            })
    return rows


def _parse_garant_blocks(soup: BeautifulSoup, court_type: str) -> List[Dict[str, Any]]:
    """Парсит страницу ГАРАНТ с блочной разметкой (Адрес / Телефон / Интернет после заголовка суда)."""
    text = soup.get_text(separator="\n")
    lines = [s.strip() for s in text.split("\n") if s.strip()]
    rows = []
    i = 0
    court_name_pattern = re.compile(r"\bсуд\b", re.I)

    while i < len(lines):
        line = lines[i]
        # Заголовок блока — название суда (длинная строка с «суд»)
        if len(line) > 18 and court_name_pattern.search(line) and not line.startswith(("Адрес", "Телефон", "Факс", "Интернет", "E-mail", "Председатель")):
            court_name = line
            address, phone, url = "", "", ""
            i += 1
            while i < len(lines):
                cur = lines[i]
                if len(cur) > 18 and court_name_pattern.search(cur) and cur not in ("Адрес", "Телефон", "Интернет") and not cur.startswith(("Адрес", "Телефон", "Факс", "Интернет", "E-mail", "Председатель")):
                    break
                if cur == "Адрес" and i + 1 < len(lines):
                    address = lines[i + 1]
                    i += 2
                    continue
                if cur == "Телефон" and i + 1 < len(lines):
                    phone = lines[i + 1]
                    i += 2
                    continue
                if cur == "Интернет" and i + 1 < len(lines):
                    url = lines[i + 1]
                    if not re.match(r"^https?://", url):
                        url = ""
                    i += 2
                    continue
                i += 1
            if court_name:
                rows.append({
                    "court_name": court_name,
                    "address": address,
                    "region": "",
                    "postal_index": _extract_postal_index(address),
                    "phone": phone,
                    "url": url,
                    "court_type": court_type,
                })
            continue
        i += 1
    return rows


def _fetch_garant_page(url: str) -> BeautifulSoup:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "windows-1251"
    return BeautifulSoup(r.text, "html.parser")


def _fetch_all_garant_sections(sections_filter: List[str] = None) -> List[Dict[str, Any]]:
    """Собирает суды со всех (или выбранных) разделов ГАРАНТ. sections_filter: например ['verhovnye','kassation']; None = все."""
    all_courts = []
    for url, court_type, parser_type, section_key in GARANT_SECTIONS:
        if sections_filter and section_key not in sections_filter:
            continue
        try:
            soup = _fetch_garant_page(url)
            if parser_type == "table":
                rows = _parse_garant_table(soup, court_type)
            else:
                rows = _parse_garant_blocks(soup, court_type)
            all_courts.extend(rows)
        except Exception as e:
            print(f"Пропуск {url}: {e}")
    return all_courts


def load_garant_courts_into_db(dry_run: bool = False, sections: List[str] = None) -> int:
    """Загружает суды с ГАРАНТ в courts.sqlite. sections: список ключей (verhovnye, kassation, apellacia, arbitr_okrug, arbitr_apell) или None = все."""
    if sys.path[0] != str(SCRIPT_DIR):
        sys.path.insert(0, str(SCRIPT_DIR))
    from courts_db import init_db, DB_PATH
    import sqlite3

    courts = _fetch_all_garant_sections(sections_filter=sections)
    if not courts:
        print("Не удалось извлечь данные с ГАРАНТ. Проверьте разделы и доступ к base.garant.ru")
        return 0

    if dry_run:
        print(f"Dry-run: найдено {len(courts)} судов. Примеры:")
        for c in courts[:5]:
            print(f"  {c.get('court_type', '')[:30]} | {c['court_name'][:40]} | {c.get('address', '')[:40]}")
        return len(courts)

    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA encoding = 'UTF-8'")
    cur = conn.cursor()
    added = 0
    for c in courts:
        if not c.get("court_name"):
            continue
        cur.execute(
            """
            INSERT INTO courts (region, district, section_num, court_name, address, postal_index, coordinates, court_type, phone, website)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                c.get("region") or None,
                None,
                None,
                c["court_name"],
                c.get("address") or None,
                c.get("postal_index") or None,
                None,
                c.get("court_type") or None,
                c.get("phone") or None,
                c.get("url") or None,
            ),
        )
        added += 1
    conn.commit()
    conn.close()
    print(f"Добавлено записей с ГАРАНТ: {added}. Всего в БД: запустите parser/verify_courts_db.py")
    return added


def main():
    import argparse
    p = argparse.ArgumentParser(description="Загрузка данных о судах с base.garant.ru/152940")
    p.add_argument("--dry-run", action="store_true", help="Не писать в БД, только показать найденное")
    p.add_argument("--sections", type=str, default=None, metavar="KEYS", help="Разделы через запятую: verhovnye,kassation,apellacia,arbitr_okrug,arbitr_apell. По умолчанию — все.")
    args = p.parse_args()
    sections = [s.strip() for s in args.sections.split(",")] if args.sections else None
    load_garant_courts_into_db(dry_run=args.dry_run, sections=sections)


if __name__ == "__main__":
    main()
