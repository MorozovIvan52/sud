"""
Каскад нормализации: ФИАС (DaData) → шаблон ФССП → очистка строки.
Поля settlement/street/house — лёгкое дополнение к parse_address из court_locator.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from unified_jurisdiction.models import UnifiedAddress

if TYPE_CHECKING:
    pass

_ROOT = Path(__file__).resolve().parent.parent


def _ensure_paths():
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    if str(_ROOT / "parser") not in sys.path:
        sys.path.insert(0, str(_ROOT / "parser"))


def _extract_street_house(text: str) -> tuple:
    street, house = None, None
    if not text:
        return street, house
    m = re.search(
        r"(?:ул\.?|улица|проспект|пр-кт|переулок|пер\.?)\s+"
        r"([А-Яа-яёЁ0-9\-\s]+?)(?:,\s*д\.?\s*([0-9]+[а-яА-Яa-zA-Z/-]?))",
        text,
        re.IGNORECASE,
    )
    if m:
        street = (m.group(1) or "").strip() or None
        house = (m.group(2) or "").strip() or None
    m2 = re.search(r"\bд\.?\s*([0-9]+[а-яА-Яa-zA-Z/-]?)\b", text, re.IGNORECASE)
    if m2 and not house:
        house = m2.group(1).strip()
    return street, house


def normalize_to_unified(raw_address: str) -> UnifiedAddress:
    _ensure_paths()
    raw = (raw_address or "").strip()

    try:
        from batch_processing.services.address_normalization import (
            normalize_address_fias,
            normalize_address_fssp,
        )

        normalized = normalize_address_fias(raw) or ""
        if not normalized:
            normalized = normalize_address_fssp(raw) or raw
    except Exception:
        normalized = raw

    try:
        from court_locator.address_parser import parse_address

        parsed = parse_address(normalized)
        region = parsed.get("region")
        district = parsed.get("district")
    except Exception:
        region, district = None, None

    street, house = _extract_street_house(normalized)
    settlement = district

    return UnifiedAddress(
        raw=raw,
        normalized=normalized or raw,
        region=region,
        district=district,
        settlement=settlement,
        street=street,
        house=house,
        latitude=None,
        longitude=None,
    )
