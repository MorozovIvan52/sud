"""
Поиск мирового участка по адресу через справочник dagalin (текст подсудности в БД) + разбор карточки на сайте.

Цепочка: нормализованный адрес → токены → SQL по jurisdiction_text/court_name → скоринг строк →
HTTP на source_url (или кэш detail_json) → словарь суда. Локальная courts.sqlite при наличии строки
дополняет пустые поля.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("court_locator.dagalin_address_search")

# Субъект РФ (фрагмент из unified.region) → region_code в dagalin_mirovye_courts (узкий фильтр SQL)
_REGION_TO_DAGALIN_CODE: List[tuple[str, str]] = [
    ("нижегород", "niz"),
    ("воронеж", "vor"),
    ("москов", "mos"),
    ("москва", "mos"),
    ("санкт-петербург", "len"),
    ("петербург", "len"),
    ("ленинград", "len"),
    ("самар", "sam"),
    ("свердлов", "sve"),
    ("новосибир", "nvs"),
    ("краснояр", "kya"),
    ("челябин", "che"),
    ("ростов", "ros"),
    ("республика татарстан", "ta"),
    ("татарстан", "ta"),
    ("башкортостан", "ba"),
    ("перм", "per"),
    ("волгоград", "vlg"),
    ("краснодар", "kda"),
    ("саратов", "sar"),
    ("тюмен", "tyu"),
    ("ижевск", "ud"),
    ("удмурт", "ud"),
    ("барнаул", "alt"),
    ("иркутск", "irk"),
    ("хабаров", "kha"),
    ("оренбург", "ore"),
    ("рязан", "rya"),
    ("астрахан", "ast"),
    ("пензен", "pen"),
    ("липецк", "lip"),
    ("киров", "kir"),
    ("чуваш", "chu"),
    ("калининград", "kgd"),
    ("тульск", "tul"),
    ("курск", "krs"),
    ("ставрополь", "sta"),
    ("тверск", "tve"),
    ("брянск", "bry"),
    ("иванов", "iva"),
    ("белгород", "bel"),
    ("владимир", "vla"),
    ("калужск", "klg"),
    ("смоленск", "smo"),
    ("мурманск", "mur"),
    ("владивосток", "pri"),
    ("приморск", "pri"),
    ("адыг", "ad"),
    ("алтайск", "alt"),
    ("амур", "amu"),
    ("архангель", "ark"),
]


def infer_dagalin_region_code(region: Optional[str]) -> Optional[str]:
    if not region:
        return None
    rl = region.lower().replace("ё", "е")
    for needle, code in _REGION_TO_DAGALIN_CODE:
        if needle in rl:
            return code
    return None


def _street_stem_variants(street: Optional[str]) -> List[str]:
    if not street:
        return []
    s = street.strip().lower().replace("ё", "е")
    v = [s]
    if len(s) >= 5 and s[-1] in "аяуюеоыи":
        v.append(s[:-1])
    if len(s) >= 6 and s[-2:] in ("ого", "его", "ому", "ему"):
        v.append(s[:-2])
    return list(dict.fromkeys([x for x in v if len(x) >= 3]))


def _tokens_from_unified(u: Any) -> List[str]:
    parts = [u.normalized or "", u.district or "", u.settlement or "", u.street or "", u.raw or ""]
    words: List[str] = []
    for part in parts:
        for w in re.split(r"[^\wа-яА-ЯёЁ]+", part, flags=re.IGNORECASE):
            w = w.strip().lower().replace("ё", "е")
            if len(w) >= 3:
                words.append(w)
    seen: set[str] = set()
    out: List[str] = []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    stop = {
        "г",
        "дом",
        "д",
        "обл",
        "край",
        "респ",
        "город",
        "проспект",
        "улица",
        "переулок",
    }
    out = [w for w in out if w not in stop]
    for stem in _street_stem_variants(getattr(u, "street", None) or None):
        if stem not in seen:
            seen.add(stem)
            out.insert(0, stem)
    comb = " ".join(parts).lower().replace("ё", "е")
    if re.search(r"пр[-.\s]*кт", comb) or "проспект" in comb:
        if "проспект" not in seen:
            seen.add("проспект")
            out.insert(0, "проспект")
    return out[:16]


def _house_even_odd_adjustment(house: Any, blob: str) -> int:
    """Разведение соседних участков (пр. Ильича в Н.Новгороде: чётные / нечётные)."""
    if not house:
        return 0
    m = re.match(r"^(\d+)", str(house).strip())
    if not m:
        return 0
    n = int(m.group(1))
    bl = blob.lower().replace("ё", "е")
    if "ильич" not in bl:
        return 0
    il_even = bool(re.search(r"ильича[^.;]{0,48}дома\s+чет", bl))
    il_odd = bool(re.search(r"ильича[^.;]{0,48}дома\s+нечет", bl))
    if n % 2 == 1:
        if il_odd:
            return 55
        if il_even:
            return -52
    else:
        if il_even:
            return 55
        if il_odd:
            return -52
    return 0


def _score_row(u: Any, row: Dict[str, Any]) -> int:
    blob = f"{row.get('court_name') or ''} {row.get('jurisdiction_text') or ''}".lower().replace("ё", "е")
    score = 0
    for t in _tokens_from_unified(u):
        if t in blob:
            score += min(len(t), 12)
    if u.street:
        st = u.street.lower().replace("ё", "е")
        if st in blob:
            score += 28
        for stem in _street_stem_variants(u.street):
            if stem != st and stem in blob:
                score += 14
    if u.district:
        d = u.district.lower().replace("ё", "е")
        if d in blob:
            score += 22
        for part in d.split():
            if len(part) >= 4 and part in blob:
                score += 10
    if u.house:
        h = str(u.house).strip()
        if h and re.search(rf"(?:д\.?|дом|№)\s*{re.escape(h)}\b", blob):
            score += 40
        elif h and len(h) <= 5 and h in blob:
            score += 18
    score += _house_even_odd_adjustment(u.house, blob)
    return score


def build_court_from_dagalin_url(
    db: Any,
    source_url: str,
    match_score: int,
) -> Optional[Dict[str, Any]]:
    """Карточка с dagalin.org + при отказе сети — имя и блоки из detail_json."""
    from court_locator.dagalin_live import (
        apply_detail_json_to_court,
        apply_parsed_dagalin_to_court,
        fetch_dagalin_html,
    )
    from court_locator.dagalin_page_parse import dagalin_detail_to_json_str, parse_dagalin_detail_html

    row = db.get_dagalin_row_by_url(source_url)
    court: Dict[str, Any] = {
        "court_name": (row or {}).get("court_name") or "",
        "address": "",
        "phone": "",
        "email": "",
        "schedule": "",
        "region": "",
        "district": "",
        "section_num": 0,
        "postal_index": "",
        "judge_name": "",
        "source": "dagalin_address_match",
        "dagalin_match_score": match_score,
        "dagalin_source_url": source_url,
    }
    html = fetch_dagalin_html(source_url)
    if html:
        try:
            parsed = parse_dagalin_detail_html(html, source_url)
            apply_parsed_dagalin_to_court(court, parsed)
            dj = dagalin_detail_to_json_str(parsed)
            if dj:
                db.update_dagalin_detail_json(source_url, dj)
        except Exception as e:
            logger.debug("dagalin parse %s: %s", source_url, e)
    if row and row.get("detail_json") and str(row["detail_json"]).strip():
        try:
            detail = json.loads(row["detail_json"])
            if isinstance(detail, dict):
                apply_detail_json_to_court(court, detail)
        except json.JSONDecodeError:
            pass
    if not court.get("court_name") and row:
        court["court_name"] = row.get("court_name") or ""
    return court if (court.get("court_name") or "").strip() else None


def merge_local_court_sqlite(db: Any, court: Dict[str, Any], u: Any) -> None:
    """Дополняет ответ из courts.sqlite, если для региона/района есть запись."""
    if not u.region or not u.district:
        return
    row = db.get_court_by_district(u.region, u.district)
    if not row:
        return
    from court_locator.utils import court_row_to_result

    loc = court_row_to_result(row, "sqlite_merge")
    for k in ("address", "phone", "email", "postal_index", "judge_name", "region", "district"):
        v = loc.get(k)
        if v and not (court.get(k) or "").strip():
            court[k] = v
    sn = loc.get("section_num")
    if sn and int(sn or 0) > 0 and not int(court.get("section_num") or 0):
        court["section_num"] = int(sn)


def find_court_by_dagalin_address_index(db: Any, u: Any) -> Optional[Dict[str, Any]]:
    """
    Главная точка входа: поиск по индексу dagalin + разбор страницы.
    Возвращает None, если таблица пуста или нет достаточного совпадения.
    """
    from court_locator.dagalin_seed import ensure_dagalin_catalog_loaded

    ensure_dagalin_catalog_loaded(db)

    tokens = _tokens_from_unified(u)
    if len(tokens) < 2:
        return None

    min_score = int((os.environ.get("DAGALIN_ADDRESS_MIN_SCORE") or "12").strip() or "12")
    rcode = infer_dagalin_region_code(u.region)

    key_for_sql = sorted(tokens, key=len, reverse=True)[:8]
    rows = db.find_dagalin_rows_by_text_tokens(key_for_sql, region_code=rcode)
    if not rows and rcode:
        rows = db.find_dagalin_rows_by_text_tokens(key_for_sql, region_code=None)
    if not rows:
        return None

    scored = [(_score_row(u, r), r) for r in rows]
    scored.sort(key=lambda x: -x[0])
    best_s, best_r = scored[0]
    second_s = scored[1][0] if len(scored) > 1 else 0

    if best_s < min_score:
        return None

    court = build_court_from_dagalin_url(db, best_r["source_url"], best_s)
    if not court:
        return None

    merge_local_court_sqlite(db, court, u)

    if best_s - second_s < 8 and second_s >= min_score:
        court["needs_manual_review"] = True

    return court
