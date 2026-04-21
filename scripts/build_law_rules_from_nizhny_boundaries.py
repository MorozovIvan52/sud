"""
Генерация law_rules из boundary_text в batch_outputs/nizhny_sections_from_text.csv.

Эвристика (без natasha):
- Ищем упоминания улиц/проспектов/шоссе/площадей/проездов/переулков/бульваров/набережных.
- Для каждого фрагмента пытаемся извлечь диапазон домов: "дома с N по N", "дома N 1, 2", "дома N 7/1".
- Записываем в law_rules: section_num, region="Нижегородская область", area_text=district, street_pattern=(?i)escaped name, house_from, house_to, law_reference="text_import".

Запуск:
  python scripts/build_law_rules_from_nizhny_boundaries.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from court_locator.database import Database

INPUT_CSV = ROOT / "batch_outputs" / "nizhny_sections_from_text.csv"

STREET_TOKEN_RE = re.compile(
    r"(улиц[аы]|ул\.?|проспект[а]?|пр\.|пр-кт|бульвар[а]?|бул\.?|площад[ьи]|пл\.?|переулок|пер\.?|проезд|шоссе|набережная|наб\.?)\s+([A-ЯЁA-Z][\w\-\.\s\"’']+?)(?=,|;|\.|$)",
    re.IGNORECASE,
)
# номера домов с необязательной литерой (для boundary_text и адреса)
HOUSE_NUM_WITH_SUFFIX_RE = re.compile(r"N?\s*([0-9]{1,4})([А-Яа-яA-Za-z]?)", re.IGNORECASE)
HOUSE_SINGLE_RE = re.compile(r"(?:д\.?|дом)\s*([0-9]{1,4})([А-Яа-яA-Za-z]?)", re.IGNORECASE)
EVEN_ODD_RE = re.compile(r"(четн\w*|нечетн\w*)", re.IGNORECASE)


def normalize_area_text(district: str) -> str:
    """Добавляем суффикс 'район' при отсутствии для более стабильного поиска по district."""
    if not district:
        return district
    low = district.lower()
    if "район" in low:
        return district
    return f"{district} район"


def _parse_house_range(text: str) -> (Optional[int], Optional[int], Optional[str], Optional[int], Optional[str]):
    """
    Парсим диапазон/список домов и возвращаем (from, to, parity, step, suffix).
    parity: 'even'/'odd' если встретили слова четные/нечетные.
    step: 2, если есть parity.
    suffix: если все найденные дома с одинаковой литерой (a/b/к/с), вернем её.
    """
    parity = None
    m_parity = EVEN_ODD_RE.search(text)
    if m_parity:
        word = m_parity.group(1).lower()
        if "нечет" in word:
            parity = "odd"
        elif "чет" in word:
            parity = "even"
    nums: List[int] = []
    suffixes: List[str] = []
    for n, suf in HOUSE_NUM_WITH_SUFFIX_RE.findall(text):
        try:
            nums.append(int(n))
            suffixes.append((suf or "").strip().lower())
        except ValueError:
            continue
    if not nums:
        return None, None, parity, None, None
    hfrom = min(nums)
    hto = max(nums)
    suffix_unique = None
    clean_suffixes = [s for s in suffixes if s]
    if clean_suffixes and len(set(clean_suffixes)) == 1:
        suffix_unique = clean_suffixes[0]
    step = 2 if parity else None
    return hfrom, hto, parity, step, suffix_unique


def extract_rules(boundary_text: str, district: str, section_num: str) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    if not boundary_text:
        return rules
    area_text = normalize_area_text(district)
    # split boundary text into fragments by period/semicolon
    fragments = re.split(r"[.;]", boundary_text)
    for frag in fragments:
        frag = frag.strip()
        if not frag:
            continue
        for m in STREET_TOKEN_RE.finditer(frag):
            street_raw = m.group(0).strip()
            street_name = m.group(2).strip()
            # house range in same fragment
            hfrom = hto = None
            parity = None
            step = None
            suffix = None
            frag_after = frag[m.end() :]
            hfrom, hto, parity, step, suffix = _parse_house_range(frag_after)
            street_pattern = rf"(?i){re.escape(street_name)}"
            rules.append(
                {
                    "section_num": section_num,
                    "region": "Нижегородская область",
                    "area_text": area_text,
                    "street_pattern": street_pattern,
                    "house_from": hfrom,
                    "house_to": hto,
                    "house_parity": parity,
                    "house_suffix": suffix,
                    "house_step": step,
                    "law_reference": "text_import",
                }
            )
    return rules


ADDRESS_STREET_RE = re.compile(
    r"(улиц[аы]|ул\.?|проспект[а]?|пр\.|пр-кт|бульвар[а]?|бул\.?|площад[ьи]|пл\.?|переулок|пер\.?|проезд|шоссе|набережная|наб\.?)\s*([A-ЯЁA-Z][\w\-\.\s\"’']+)",
    re.IGNORECASE,
)


def extract_address_rule(address: str, district: str, section_num: str) -> Optional[Dict[str, Any]]:
    if not address:
        return None
    area_text = normalize_area_text(district)
    m = ADDRESS_STREET_RE.search(address)
    if not m:
        return None
    street_name = m.group(2).strip()
    street_pattern = rf"(?i){re.escape(street_name)}"
    hfrom = hto = None
    house_suffix = None
    house_step = None
    hm = HOUSE_SINGLE_RE.search(address)
    if hm:
        try:
            hfrom = int(hm.group(1))
            hto = hfrom
            house_suffix = (hm.group(2) or "").strip().lower() or None
        except ValueError:
            hfrom = hto = None
    return {
        "section_num": section_num,
        "region": "Нижегородская область",
        "area_text": area_text,
        "street_pattern": street_pattern,
        "house_from": hfrom,
        "house_to": hto,
        "house_parity": None,
        "house_suffix": house_suffix,
        "house_step": house_step,
        "law_reference": "address_import",
    }


def load_sections() -> List[Dict[str, str]]:
    with INPUT_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def main() -> None:
    sections = load_sections()
    all_rules: List[Dict[str, Any]] = []
    for s in sections:
        section_num = s.get("section_num") or ""
        district = s.get("district") or ""
        boundary_text = s.get("boundary_text") or ""
        rules = extract_rules(boundary_text, district, section_num)
        all_rules.extend(rules)
        addr_rule = extract_address_rule(s.get("address") or "", district, section_num)
        if addr_rule:
            all_rules.append(addr_rule)

    # deduplicate by (section, street_pattern, house_from, house_to, house_parity, house_suffix)
    uniq = {}
    for r in all_rules:
        key = (
            r["section_num"],
            r["street_pattern"],
            r["house_from"],
            r["house_to"],
            r.get("house_parity"),
            r.get("house_suffix"),
            r.get("house_step"),
        )
        if key not in uniq:
            uniq[key] = r
    deduped = list(uniq.values())

    # write CSV preview
    out_csv = ROOT / "batch_outputs" / "nizhny_law_rules_auto.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "section_num",
                "region",
                "area_text",
                "street_pattern",
                "house_from",
                "house_to",
                "house_parity",
                "house_suffix",
                "house_step",
                "law_reference",
            ],
        )
        writer.writeheader()
        writer.writerows(deduped)

    # load into DB
    db = Database()
    db.init_schema()
    db.update_law_rules(deduped, clear_before=True)
    db.close()
    print(f"Loaded {len(deduped)} rules into law_rules and saved preview to {out_csv}")


if __name__ == "__main__":
    main()
