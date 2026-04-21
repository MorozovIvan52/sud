#!/usr/bin/env python3
"""
Улучшенный разбор PDF закона о мировых судьях (таблицы pdfplumber + fill-down section_num).

Отличия от law_file_parser.py (текстовый поток):
  - извлечение таблиц ``extract_tables``, перенос номера участка на строки с пустой ячейкой;
  - заголовки вида «Участок мирового судьи № N»;
  - дома: диапазоны, перечисления через запятую, зачатки корпусов.

Импорт в БД через ``court_locator.database.Database`` (как в v1).

Запуск:
  python scripts/law_file_parser_v2.py path.pdf --region "Санкт-Петербург" --law-ref "..." --csv-out data/law_drafts/spb_v2.csv
  python scripts/law_file_parser_v2.py path.pdf --region "Санкт-Петербург" --import --clear-region --db parser/court_districts.sqlite
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pdfplumber

from court_locator.database import Database
from court_locator.law_document_parser import (
    make_street_pattern,
    normalize_law_plain_text,
    next_law_rule_start_id,
    parse_text_to_rule_dicts,
    rules_for_database,
    write_draft_csv,
)

# Заголовки участка (в т.ч. СПб)
RE_SECTION = re.compile(
    r"(?:"
    r"судебн\w*\s+участ\w*"
    r"|участок\s+мирового\s+судьи"
    r"|участ\w*\s+мирового\s+судьи"
    r")\s*[№#\u2116N]?\s*(\d+)",
    re.IGNORECASE,
)

RE_STREET = re.compile(
    r"(?:ул(?:ица)?\.?\s*|пер(?:еулок)?\.?\s*|пр(?:-кт|оспект)?\.?\s*"
    r"|б(?:ульвар)?\.?\s*|наб(?:ережная)?\.?\s*|ш(?:оссе)?\.?\s*"
    r"|линия\s*|дор(?:ога)?\.?\s*|пл(?:ощадь)?\.?\s*|проспект\s*)"
    r"([А-Яа-яЁё0-9\s\-\.«»\"]+?)(?=\s*,|\s*д\.|\s*дом|\s*$|\n)",
    re.IGNORECASE,
)

RE_RANGE = re.compile(
    r"д(?:ом)?\.?\s*(\d+)\s*[-—–]\s*(\d+)"
    r"(?:\s*[,(]?\s*(нечёт\w*|нечет\w*|чётн\w*|четн\w*|всех?\s*дом\w*)?\s*[)]?)?",
    re.IGNORECASE,
)

RE_SINGLE = re.compile(r"(?:д(?:ом)?\.?)\s*(\d+)([а-яА-Я]?)", re.IGNORECASE)

# Перечисление: д. 1, 3, 5 или 1, 3, 5 после контекста "дом"
RE_COMMA_NUMS = re.compile(
    r"(?:д(?:ом)?\.?\s*)?((?:\d{1,4}[а-яА-Я]?\s*,\s*)+\d{1,4}[а-яА-Я]?)",
    re.IGNORECASE,
)

PARITY_MAP = {
    "нечёт": "odd",
    "нечет": "odd",
    "чётн": "even",
    "четн": "even",
}


def _parity_from(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    sl = s.lower().replace("ё", "е")
    for k, v in PARITY_MAP.items():
        if k in sl:
            return v
    if "все" in sl:
        return None
    return None


def _house_int(x: Any) -> Optional[int]:
    if x is None or x == "":
        return None
    try:
        return int(str(x).strip())
    except ValueError:
        return None


def parse_house_cell(text: str) -> List[Dict[str, Any]]:
    """Диапазоны, одиночные дома, перечисления через запятую."""
    if not text:
        return []
    t = re.sub(r"\s+", " ", text.strip())
    out: List[Dict[str, Any]] = []

    for m in RE_RANGE.finditer(t):
        out.append(
            {
                "house_from": int(m.group(1)),
                "house_to": int(m.group(2)),
                "house_parity": _parity_from(m.group(3)),
                "house_suffix": None,
            }
        )

    if out:
        return out

    cm = RE_COMMA_NUMS.search(t)
    if cm:
        chunk = cm.group(1)
        parts = [p.strip() for p in chunk.split(",")]
        nums: List[int] = []
        suffixes: List[Optional[str]] = []
        for p in parts:
            mm = re.match(r"^(\d{1,4})([а-яА-Я]?)$", p.strip())
            if mm:
                nums.append(int(mm.group(1)))
                suf = mm.group(2).strip()
                suffixes.append(suf.lower() if suf else None)
        if len(nums) >= 2:
            step = nums[1] - nums[0]
            if step == 2 and all(nums[i + 1] - nums[i] == 2 for i in range(len(nums) - 1)):
                out.append(
                    {
                        "house_from": min(nums),
                        "house_to": max(nums),
                        "house_parity": "odd" if nums[0] % 2 else "even",
                        "house_suffix": None,
                    }
                )
                return out
        for n, suf in zip(nums, suffixes):
            out.append(
                {
                    "house_from": n,
                    "house_to": n,
                    "house_parity": None,
                    "house_suffix": suf,
                }
            )
        if out:
            return out

    for m in RE_SINGLE.finditer(t):
        suf = (m.group(2) or "").strip().lower() or None
        out.append(
            {
                "house_from": int(m.group(1)),
                "house_to": int(m.group(1)),
                "house_parity": None,
                "house_suffix": suf,
            }
        )
    return out


def _pick_columns(header: List[Any]) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    col_section = col_territory = col_street = col_house = None
    for i, cell in enumerate(header or []):
        c = str(cell or "").lower()
        if ("участ" in c or "номер" in c) and ("№" in c or "номер" in c or "участ" in c):
            col_section = i
        elif "территор" in c or "район" in c or "округ" in c:
            col_territory = i
        elif "улиц" in c or "адрес" in c or "наименован" in c or "улица" in c:
            col_street = i
        elif "дом" in c or "строен" in c:
            col_house = i
    return col_section, col_territory, col_street, col_house


def parse_table(
    table: List[List[Any]],
    carry_section: Optional[str],
    page_num: int,
    law_ref: str,
    region: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    rules: List[Dict[str, Any]] = []
    if not table:
        return rules, carry_section

    header = table[0] if table else []
    col_section, col_territory, col_street, col_house = _pick_columns(header)

    # Заголовок не распознан — типичная раскладка 4 колонок
    if col_section is None:
        col_section = 0
    if col_street is None:
        col_street = min(2, len(header) - 1) if header else 2
    if col_house is None:
        col_house = min(3, len(header) - 1) if header else 3

    def cell(row: List[Any], i: Optional[int]) -> str:
        if i is None or i >= len(row) or row[i] is None:
            return ""
        return str(row[i]).strip()

    current_section = carry_section
    start_row = 1 if header else 0

    for row in table[start_row:]:
        if not row:
            continue
        raw_sec = cell(row, col_section)
        m_sec = RE_SECTION.search(raw_sec) if raw_sec else None
        if m_sec:
            current_section = m_sec.group(1)
        elif raw_sec and raw_sec.isdigit():
            current_section = raw_sec

        if not current_section:
            continue

        street_text = cell(row, col_street)
        house_text = cell(row, col_house)
        area_text = cell(row, col_territory) if col_territory is not None else ""

        block = f"{street_text}\n{house_text}"
        streets = re.split(r"[;\n]+", street_text)
        for street_raw in streets:
            street_raw = street_raw.strip()
            if len(street_raw) < 2:
                continue
            m_str = RE_STREET.search(street_raw)
            if m_str:
                street_name = m_str.group(1).strip()
            else:
                if len(street_raw) > 3 and not street_raw[0].isdigit():
                    street_name = street_raw
                else:
                    continue

            pattern = make_street_pattern(street_name)
            houses_src = house_text or street_raw
            house_rules = parse_house_cell(houses_src)

            if house_rules:
                for hr in house_rules:
                    rules.append(
                        {
                            "section_num": current_section,
                            "region": region,
                            "area_text": area_text,
                            "street_pattern": pattern,
                            "house_from": hr.get("house_from"),
                            "house_to": hr.get("house_to"),
                            "house_parity": hr.get("house_parity"),
                            "house_suffix": hr.get("house_suffix"),
                            "house_step": None,
                            "law_reference": law_ref,
                            "parse_status": "auto_v2_table",
                            "source_line": f"p{page_num}_table",
                        }
                    )
            else:
                rules.append(
                    {
                        "section_num": current_section,
                        "region": region,
                        "area_text": area_text,
                        "street_pattern": pattern,
                        "house_from": None,
                        "house_to": None,
                        "house_parity": None,
                        "house_suffix": None,
                        "house_step": None,
                        "law_reference": law_ref,
                        "parse_status": "auto_v2_table_no_house",
                        "source_line": f"p{page_num}_table",
                    }
                )

    return rules, current_section


def parse_text_page_lines(
    text: str,
    carry_section: Optional[str],
    page_num: int,
    law_ref: str,
    region: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Страница без таблиц — построчно с теми же заголовками участка."""
    rules: List[Dict[str, Any]] = []
    current = carry_section
    t = normalize_law_plain_text(text)
    for line in t.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = RE_SECTION.search(line)
        if m:
            current = m.group(1)
            continue
        if not current:
            continue
        m_str = RE_STREET.search(line)
        if not m_str:
            continue
        street_name = m_str.group(1).strip()
        pattern = make_street_pattern(street_name)
        hrs = parse_house_cell(line)
        if hrs:
            for hr in hrs:
                rules.append(
                    {
                        "section_num": current,
                        "region": region,
                        "area_text": "",
                        "street_pattern": pattern,
                        "house_from": hr.get("house_from"),
                        "house_to": hr.get("house_to"),
                        "house_parity": hr.get("house_parity"),
                        "house_suffix": hr.get("house_suffix"),
                        "house_step": None,
                        "law_reference": law_ref,
                        "parse_status": "auto_v2_text",
                        "source_line": f"p{page_num}_text",
                    }
                )
        else:
            rules.append(
                {
                    "section_num": current,
                    "region": region,
                    "area_text": "",
                    "street_pattern": pattern,
                    "house_from": None,
                    "house_to": None,
                    "house_parity": None,
                    "house_suffix": None,
                    "house_step": None,
                    "law_reference": law_ref,
                    "parse_status": "auto_v2_text_no_house",
                    "source_line": f"p{page_num}_text",
                }
            )
    return rules, current


def extract_from_pdf(
    pdf_path: Path,
    law_ref: str,
    region: str,
) -> List[Dict[str, Any]]:
    """Таблицы + текстовый fallback по страницам; carry section между страницами."""
    all_rules: List[Dict[str, Any]] = []
    carry: Optional[str] = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables() or []
            if tables:
                for table in tables:
                    chunk, carry = parse_table(table, carry, page_num, law_ref, region)
                    all_rules.extend(chunk)
            else:
                text = page.extract_text() or ""
                if text.strip():
                    chunk, carry = parse_text_page_lines(text, carry, page_num, law_ref, region)
                    all_rules.extend(chunk)

    # Дополнительно: общий текстовый проход как v1 (подхватывает то, что таблицы не дали)
    full_text_parts: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pdf.pages:
            full_text_parts.append(p.extract_text() or "")
    full_text = "\n".join(full_text_parts)
    v1_rules = parse_text_to_rule_dicts(full_text, region, law_ref + " | v1_merge")
    for r in v1_rules:
        r["parse_status"] = str(r.get("parse_status", "")) + "|v1_merge"

    # Объединяем и дедуплицируем по ключевым полям
    key = lambda x: (
        x.get("section_num"),
        x.get("street_pattern"),
        x.get("house_from"),
        x.get("house_to"),
        x.get("house_parity"),
        x.get("area_text"),
    )
    seen = set()
    merged: List[Dict[str, Any]] = []
    for r in all_rules + v1_rules:
        k = key(r)
        if k in seen:
            continue
        seen.add(k)
        merged.append(r)
    return merged


def main() -> None:
    ap = argparse.ArgumentParser(description="PDF закона → law_rules (таблицы + fill-down)")
    ap.add_argument("pdf", type=Path, help="Путь к PDF")
    ap.add_argument("--region", required=True)
    ap.add_argument("--law-ref", default="", help="law_reference")
    ap.add_argument("--db", default=str(ROOT / "parser" / "court_districts.sqlite"))
    ap.add_argument("--csv-out", default="", help="CSV (по умолчанию data/law_drafts/law_rules_v2_<region>.csv)")
    ap.add_argument("--import", dest="do_import", action="store_true")
    ap.add_argument("--clear-region", action="store_true", help="DELETE law_rules для этого региона перед импортом")
    args = ap.parse_args()

    pdf_path = args.pdf.resolve()
    if not pdf_path.is_file():
        print(f"Файл не найден: {pdf_path}")
        sys.exit(1)

    law_ref = args.law_ref or pdf_path.name
    print(f"Разбор: {pdf_path.name}")
    rules = extract_from_pdf(pdf_path, law_ref, args.region)

    sections = {str(r["section_num"]) for r in rules if r.get("section_num")}
    print(f"Строк правил (после дедуп с v1-merge): {len(rules)}")
    print(f"Уникальных section_num: {len(sections)}")

    safe = re.sub(r"[^\w\-]", "_", args.region)[:80]
    csv_path = Path(args.csv_out) if args.csv_out else ROOT / "data" / "law_drafts" / f"law_rules_v2_{safe}.csv"
    write_draft_csv(rules, csv_path)
    print(f"CSV: {csv_path.resolve()}")

    if args.do_import:
        db_path = Path(args.db)
        db = Database(districts_db_path=str(db_path))
        db.init_schema()
        if args.clear_region:
            conn = db._get_districts_conn()
            deleted = conn.execute(
                "DELETE FROM law_rules WHERE region = ?", (args.region,)
            ).rowcount
            conn.commit()
            print(f"Удалено строк региона [{args.region}]: {deleted}")

        start_id = next_law_rule_start_id(db)
        payload = rules_for_database(rules, start_id)
        db.update_law_rules(payload, clear_before=False)
        db.close()
        print(f"Импортировано записей: {len(payload)} → {db_path}")


if __name__ == "__main__":
    main()
