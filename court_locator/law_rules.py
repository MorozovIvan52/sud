from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from court_locator.database import Database
from court_locator.utils import court_row_to_result

# spaCy/Natasha: опционально усиливают матчинг (леммы, падежи)
try:
    from court_locator.ru_nlp import nlp_match_variants, spacy_lemmas
except ImportError:
    nlp_match_variants = None  # type: ignore[assignment,misc]
    spacy_lemmas = None  # type: ignore[assignment,misc]


HOUSE_RE = re.compile(r"\b(\d{1,4})([А-Яа-яA-Za-z\-]*)")

_REGION_STOP = frozenset(
    {
        "область",
        "республика",
        "автономная",
        "округ",
        "федерации",
        "край",
        "края",
        "округа",
    }
)


def _rule_region_tokens(rule_region: str) -> List[str]:
    r = (rule_region or "").lower().replace("ё", "е")
    return [
        w
        for w in re.findall(r"[а-яё]{3,}", r)
        if w not in _REGION_STOP and len(w) >= 4
    ]


def _pattern_cyrillic_tokens(pattern: str) -> List[str]:
    """Извлекает значимые кириллические фрагменты из regex (для fuzzy к леммам)."""
    s = re.sub(r"^\(\?i\)", "", pattern or "", flags=re.IGNORECASE)
    s = re.sub(r"[^\w\u0400-\u04FF\-]+", " ", s)
    return [w.lower() for w in s.split() if len(w) >= 3]


def _fuzzy_pattern_lemma_match(pattern: str, lemmas: List[str]) -> bool:
    """
    Если regex не ловит падеж («Ленина» vs лемма «ленин»), сопоставляем ключевые слова из pattern с леммами.
    Не применяется к сложным regex (альтернативы, классы символов).
    """
    if not pattern or len(pattern) > 220:
        return False
    if "|" in pattern or "[" in pattern:
        return False
    words = _pattern_cyrillic_tokens(pattern)
    if not words:
        return False
    for w in words:
        ok = False
        for lem in lemmas:
            if lem == w or (
                len(w) >= 4
                and len(lem) >= 4
                and (lem.startswith(w[:4]) or w.startswith(lem[:4]))
            ):
                ok = True
                break
        if not ok:
            return False
    return True


def _match_street_pattern_with_source(
    rule_pattern: str, addr: str, variants: List[str], lemmas: List[str]
) -> Tuple[bool, str]:
    """
    Совпадение street_pattern: полный адрес → строка лемм spaCy → fuzzy леммы к словам из pattern.
    Возвращает (успех, метка для source: law_rules | law_rules_nlp | law_rules_nlp_fuzzy).
    """
    if not rule_pattern:
        return False, ""
    try:
        if re.search(rule_pattern, addr, flags=re.IGNORECASE):
            return True, "law_rules"
        for text in variants[1:]:
            if text and re.search(rule_pattern, text, flags=re.IGNORECASE):
                return True, "law_rules_nlp"
        if lemmas and _fuzzy_pattern_lemma_match(rule_pattern, lemmas):
            return True, "law_rules_nlp_fuzzy"
    except re.error:
        return False, ""
    return False, ""


def _rule_region_compatible(rule_region: str, addr_l: str) -> bool:
    """Если в правиле указан субъект, в адресе должен быть узнаваемый фрагмент названия."""
    if not (rule_region or "").strip():
        return True
    addr_l = addr_l.lower().replace("ё", "е")
    rr = rule_region.lower().replace("ё", "е").strip()
    # Областной центр без слова «Нижегородская» в строке адреса
    if "нижегородск" in rr and "нижний" in addr_l and "новгород" in addr_l:
        return True
    for t in _rule_region_tokens(rule_region):
        if t in addr_l:
            return True
    if len(rr) >= 10 and rr in addr_l:
        return True
    return False


@dataclass
class LawRule:
    id: int
    section_num: str
    region: str
    area_text: str
    street_pattern: str
    house_from: Optional[int]
    house_to: Optional[int]
    house_parity: Optional[str]
    house_suffix: Optional[str]
    house_step: Optional[int]
    law_reference: str


def _extract_house(addr: str) -> (Optional[int], Optional[str]):
    m = HOUSE_RE.search(addr or "")
    if not m:
        return None, None
    try:
        num = int(m.group(1))
    except Exception:
        return None, None
    suffix = m.group(2) or ""
    suffix = suffix.strip().lower() or None
    return num, suffix


class LawRuleMatcher:
    """
    Сопоставление адреса с правилами law_rules:
    - regex по полному адресу (source: law_rules);
    - тот же regex по строке лемм spaCy (law_rules_nlp), если установлены spacy + ru_core_news_*;
    - сопоставление ключевых слов из pattern с леммами при разных падежах (law_rules_nlp_fuzzy);
    - house_from/to, чётность, суффикс дома;
    - фильтр по субъекту (region) по вхождению в адрес;
    - слабое совпадение по area_text (law_rules_area).
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self._rules: List[LawRule] = []
        self._load()

    def _load(self) -> None:
        rows = self.db.get_law_rules()
        self._rules = [
            LawRule(
                id=r.get("id") or 0,
                section_num=str(r.get("section_num") or ""),
                region=str(r.get("region") or ""),
                area_text=str(r.get("area_text") or ""),
                street_pattern=str(r.get("street_pattern") or ""),
                house_from=r.get("house_from"),
                house_to=r.get("house_to"),
                house_parity=r.get("house_parity"),
                house_suffix=r.get("house_suffix"),
                house_step=r.get("house_step"),
                law_reference=str(r.get("law_reference") or ""),
            )
            for r in rows
        ]

    def match(self, address: str) -> Optional[Dict]:
        addr = (address or "").strip()
        addr_l = addr.lower()
        house_num, house_suffix = _extract_house(addr_l)

        variants: List[str] = [addr]
        lemmas: List[str] = []
        if nlp_match_variants is not None:
            try:
                variants = nlp_match_variants(addr)
            except Exception:
                variants = [addr]
        if spacy_lemmas is not None:
            try:
                lemmas = spacy_lemmas(addr)
            except Exception:
                lemmas = []

        # 1) street_pattern + optional house range (текст, леммы spaCy, fuzzy леммы)
        for rule in self._rules:
            if rule.street_pattern:
                ok, src = _match_street_pattern_with_source(
                    rule.street_pattern, addr, variants, lemmas
                )
                if not ok:
                    continue
                if rule.house_from and house_num is not None and house_num < rule.house_from:
                    continue
                if rule.house_to and house_num is not None and house_num > rule.house_to:
                    continue
                if rule.house_parity and house_num is not None:
                    if rule.house_parity == "even" and house_num % 2 != 0:
                        continue
                    if rule.house_parity == "odd" and house_num % 2 != 1:
                        continue
                if rule.house_step and rule.house_from and house_num is not None:
                    try:
                        if (house_num - rule.house_from) % int(rule.house_step) != 0:
                            continue
                    except Exception:
                        pass
                if rule.house_suffix and rule.house_suffix.lower():
                    if (house_suffix or "").lower() != rule.house_suffix.lower():
                        continue
                if not _rule_region_compatible(rule.region, addr_l):
                    continue
                return court_row_to_result(
                    {
                        "section_num": rule.section_num,
                        "region": rule.region,
                        "law_reference": rule.law_reference,
                        "court_name": f"Судебный участок №{rule.section_num}" if rule.section_num else "",
                    },
                    src,
                )

        # 2) area_text match (weaker)
        for rule in self._rules:
            if rule.area_text and rule.area_text.lower() in addr_l:
                if not _rule_region_compatible(rule.region, addr_l):
                    continue
                return court_row_to_result(
                    {
                        "section_num": rule.section_num,
                        "region": rule.region,
                        "law_reference": rule.law_reference,
                        "court_name": f"Судебный участок №{rule.section_num}" if rule.section_num else "",
                    },
                    "law_rules_area",
                )

        return None
