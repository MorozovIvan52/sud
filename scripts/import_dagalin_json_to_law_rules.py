from __future__ import annotations

"""
Импорт правил law_rules из выгрузки dagalin.org (JSON из court_sites_scraper).
- Для каждого элемента:
  - создаём правило по адресу (street_pattern, house_from/to, suffix)
  - парсим текст подсудности на улицы/диапазоны: сначала boundary_snippet (детальная
    страница), при пустом — jurisdiction_teaser со страницы списка, затем detailed_jurisdiction
- Добавляем в таблицу law_rules без очистки (append)

В JSON можно передавать region_name (название субъекта РФ с dagalin) — оно попадёт в колонку region.

Запуск:
  python scripts/import_dagalin_json_to_law_rules.py batch_outputs/court_sites_scrape_XXXXX.json
  python scripts/import_dagalin_rf_law_rules.py   # все субъекты РФ с dagalin → law_rules
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from court_locator.database import Database

# Регексы как в build_law_rules_from_nizhny_boundaries
STREET_TOKEN_RE = re.compile(
    r"(улиц[аы]|ул\.?|проспект[а]?|пр\.|пр-кт|бульвар[а]?|бул\.?|площад[ьи]|пл\.?|переулок|пер\.?|проезд|шоссе|набережная|наб\.?)\s+([A-ЯЁA-Z][\w\-\.\s\"’']+?)(?=,|;|\.|$)",
    re.IGNORECASE,
)
HOUSE_NUM_WITH_SUFFIX_RE = re.compile(r"N?\s*([0-9]{1,4})([А-Яа-яA-Za-z]?)", re.IGNORECASE)
HOUSE_SINGLE_RE = re.compile(r"(?:д\.?|дом)\s*([0-9]{1,4})([А-Яа-яA-Za-z]?)", re.IGNORECASE)
EVEN_ODD_RE = re.compile(r"(четн\w*|нечетн\w*)", re.IGNORECASE)
SECTION_IN_NAME_RE = re.compile(r"участк\w*\s*№?\s*(\d+)", re.IGNORECASE)
AREA_IN_NAME_RE = re.compile(r"([А-ЯЁA-Яё\s\-]+района)", re.IGNORECASE)

# Пропускаем «заглушки» парсера, чтобы перейти к jurisdiction_teaser
_BOUNDARY_PLACEHOLDER_RE = re.compile(
    r"детальн\w+\s+информаци\w+\s+не\s+найдена|ошибка\s+загрузки",
    re.IGNORECASE,
)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _usable_boundary_fragment(raw: str) -> str:
    t = clean(str(raw or ""))
    if not t or _BOUNDARY_PLACEHOLDER_RE.search(t):
        return ""
    return t


def effective_boundary_text(item: Dict[str, Any]) -> str:
    """Текст подсудности: детальная страница, иначе тизер списка, иначе detailed_jurisdiction."""
    for key in ("boundary_snippet", "jurisdiction_teaser", "detailed_jurisdiction"):
        t = _usable_boundary_fragment(item.get(key))
        if t:
            return t
    return ""


def parse_section(name: str) -> str:
    m = SECTION_IN_NAME_RE.search(name or "")
    if m:
        return m.group(1)
    return ""


def parse_area(name: str) -> str:
    m = AREA_IN_NAME_RE.search(name or "")
    if m:
        return clean(m.group(1))
    return ""


def normalize_area(area: str) -> str:
    if not area:
        return area
    low = area.lower()
    if "район" in low:
        return area
    return f"{area} район"


def parse_house_range(text: str) -> Tuple[Optional[int], Optional[int], Optional[str], Optional[int], Optional[str]]:
    parity = None
    m_parity = EVEN_ODD_RE.search(text)
    if m_parity:
        w = m_parity.group(1).lower()
        if "нечет" in w:
            parity = "odd"
        elif "чет" in w:
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


def rules_from_boundary(
    boundary: str, section: str, area: str, region: str = "Нижегородская область"
) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    if not boundary:
        return rules
    area_norm = normalize_area(area)
    reg = (region or "").strip() or "Нижегородская область"
    fragments = re.split(r"[.;]", boundary)
    for frag in fragments:
        frag = frag.strip()
        if not frag:
            continue
        for m in STREET_TOKEN_RE.finditer(frag):
            street_name = m.group(2).strip()
            hfrom = hto = None
            parity = None
            step = None
            suffix = None
            frag_after = frag[m.end() :]
            hfrom, hto, parity, step, suffix = parse_house_range(frag_after)
            street_pattern = rf"(?i){re.escape(street_name)}"
            rules.append(
                {
                    "section_num": section,
                    "region": reg,
                    "area_text": area_norm,
                    "street_pattern": street_pattern,
                    "house_from": hfrom,
                    "house_to": hto,
                    "house_parity": parity,
                    "house_suffix": suffix,
                    "house_step": step,
                    "law_reference": "dagalin_boundary",
                }
            )
        # Дополнительно: если список улиц без префиксов после "Улицы:"
        if "улиц" in frag.lower():
            tail_parts = re.split(r"улиц[аы]:", frag, flags=re.IGNORECASE)
            if len(tail_parts) > 1:
                tail = tail_parts[1]
                for raw in tail.split(","):
                    name = raw.strip()
                    if not name:
                        continue
                    name = re.sub(r"\(.*?\)", "", name)
                    name = re.split(r"дома|дом\s|N", name, flags=re.IGNORECASE)[0].strip()
                    if len(name) < 2:
                        continue
                    street_pattern = rf"(?i){re.escape(name)}"
                    rules.append(
                        {
                            "section_num": section,
                            "region": reg,
                            "area_text": area_norm,
                            "street_pattern": street_pattern,
                            "house_from": None,
                            "house_to": None,
                            "house_parity": None,
                            "house_suffix": None,
                            "house_step": None,
                            "law_reference": "dagalin_boundary",
                        }
                    )
    return rules


def rule_from_address(
    address: str, section: str, area: str, region: str = "Нижегородская область"
) -> Optional[Dict[str, Any]]:
    if not address:
        return None
    area_norm = normalize_area(area)
    reg = (region or "").strip() or "Нижегородская область"
    m = STREET_TOKEN_RE.search(address)
    if not m:
        return None
    street_name = m.group(2).strip()
    hfrom = hto = None
    suffix = None
    hm = HOUSE_SINGLE_RE.search(address)
    if hm:
        try:
            hfrom = int(hm.group(1))
            hto = hfrom
            suffix = (hm.group(2) or "").strip().lower() or None
        except ValueError:
            hfrom = hto = None
    street_pattern = rf"(?i){re.escape(street_name)}"
    return {
        "section_num": section,
        "region": reg,
        "area_text": area_norm,
        "street_pattern": street_pattern,
        "house_from": hfrom,
        "house_to": hto,
        "house_parity": None,
        "house_suffix": suffix,
        "house_step": None,
        "law_reference": "dagalin_address",
    }


def infer_region_for_item(item: Dict[str, Any]) -> str:
    """Субъект РФ для правила: явное поле или fallback."""
    for key in ("region_name", "subject", "region_display"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "Нижегородская область"


def items_to_deduped_law_rules(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Преобразует элементы выгрузки dagalin (как в JSON скрапера) в уникальные law_rules."""
    all_rules: List[Dict[str, Any]] = []
    for item in data:
        name = item.get("name") or item.get("court_name") or ""
        section = parse_section(name)
        if (not section) and item.get("section_numbers"):
            section = str(item["section_numbers"][0])
        area = parse_area(name)
        if not area and "Автозавод" in name:
            area = "Автозаводский район"
        if not area and "Саровск" in name:
            area = "Саровский район"
        region_subj = infer_region_for_item(item)
        boundary = effective_boundary_text(item)
        addr = item.get("address") or ""
        addr_rule = rule_from_address(addr, section, area, region_subj)
        if addr_rule:
            all_rules.append(addr_rule)
        boundary_rules = rules_from_boundary(boundary, section, area, region_subj)
        all_rules.extend(boundary_rules)
        teaser_only = _usable_boundary_fragment(item.get("jurisdiction_teaser"))
        if not boundary_rules and teaser_only and teaser_only != boundary:
            all_rules.extend(rules_from_boundary(teaser_only, section, area, region_subj))

    uniq: Dict[tuple, Dict[str, Any]] = {}
    for r in all_rules:
        key = (
            r.get("region"),
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
    return list(uniq.values())


def load_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python import_dagalin_json_to_law_rules.py <json_path> [--clear-dagalin]")
        sys.exit(1)
    src = Path(sys.argv[1])
    clear_dagalin = "--clear-dagalin" in sys.argv[2:]
    data = load_json(src)
    deduped = items_to_deduped_law_rules(data)

    db = Database()
    db.init_schema()
    if clear_dagalin:
        conn = db._get_districts_conn()
        conn.execute("DELETE FROM law_rules WHERE law_reference LIKE 'dagalin%'")
        conn.commit()
    db.update_law_rules(deduped, clear_before=False)
    db.close()
    print(f"Imported {len(deduped)} rules from {src}")


if __name__ == "__main__":
    main()
