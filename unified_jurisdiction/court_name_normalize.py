"""
Нормализация названий судов для сравнения источников (DaData, Dagalin, БД).
"""
from __future__ import annotations

import re
from typing import Optional


_PREFIX_RE = re.compile(
    r"^\s*(судебный\s+участок|мировой\s+судебный\s+участок|"
    r"мировой\s+судья|участок\s+мирового\s+судьи)\s*[№n]?\s*",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"№\s*(\d+)|(\d+)\s*[-–]?\s*участ", re.IGNORECASE)


def normalize_court_name(name: Optional[str]) -> str:
    """Синоним для ключа сравнения (название суда после нормализации)."""
    return normalize_court_key(name)


def normalize_court_key(name: Optional[str]) -> str:
    """
    Ключ для сопоставления источников: нижний регистр, без ё, префиксы убраны,
    остаётся номер участка и региональные маркеры по возможности.
    """
    if not name or not str(name).strip():
        return ""
    s = str(name).lower().replace("ё", "е")
    s = _PREFIX_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_section_number(name: Optional[str]) -> Optional[int]:
    """Номер участка из названия, если удаётся вытащить."""
    if not name:
        return None
    m = _NUM_RE.search(name)
    if not m:
        m = re.search(r"№\s*(\d+)", name, re.IGNORECASE)
    if not m:
        return None
    g = m.group(1) or m.group(2)
    try:
        return int(g)
    except (TypeError, ValueError):
        return None


def courts_same_by_key(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    ka, kb = normalize_court_key(a), normalize_court_key(b)
    if ka == kb and ka:
        return True
    na, nb = extract_section_number(a), extract_section_number(b)
    if na is not None and na == nb:
        return True
    return False
