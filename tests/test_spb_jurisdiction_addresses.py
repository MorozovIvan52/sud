"""
Десять сценариев проверки подсудности по адресу для региона «Санкт-Петербург».

Используется изолированная БД с контролируемыми правилами law_rules (уникальные
токены улиц), чтобы тесты не зависели от качества импорта PDF и были стабильны в CI.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest

from court_locator.database import Database
from court_locator.law_rules import LawRuleMatcher


def _build_fixture_rules() -> List[Dict[str, Any]]:
    """
    10 правил с непересекающимися литералами в regex (иначе fuzzy-леммы
    могут сопоставить неверное правило раньше точного совпадения).
    """
    base_id = 90000
    rows: List[Dict[str, Any]] = []

    # Префиксы по 4+ символа должны различаться: иначе law_rules_nlp_fuzzy
    # сопоставляет «по началу» и первое правило перехватывает все адреса.
    tokens = [
        "ALPHA01SPB",
        "BETA02SPB",
        "GAMMA03SPB",
        "DELTA04SPB",
        "EPSLN05SPB",
        "ZETA06SPB",
        "ETA07SPB",
        "THETA08SPB",
        "IOTA09SPB",
        "KAPPA10SPB",
    ]

    for i, tok in enumerate(tokens[:8], start=1):
        rows.append(
            {
                "id": base_id + i,
                "section_num": str(i),
                "region": "Санкт-Петербург",
                "area_text": "",
                "street_pattern": rf"(?i){tok}",
                "house_from": None,
                "house_to": None,
                "house_parity": None,
                "house_suffix": None,
                "house_step": None,
                "law_reference": "fixture_spb",
            }
        )

    rows.append(
        {
            "id": base_id + 9,
            "section_num": "9",
            "region": "Санкт-Петербург",
            "area_text": "",
            "street_pattern": r"(?i)IOTA09SPB",
            "house_from": 10,
            "house_to": 20,
            "house_parity": None,
            "house_suffix": None,
            "house_step": None,
            "law_reference": "fixture_spb",
        }
    )

    rows.append(
        {
            "id": base_id + 10,
            "section_num": "10",
            "region": "Санкт-Петербург",
            "area_text": "",
            "street_pattern": r"(?i)KAPPA10SPB",
            "house_from": None,
            "house_to": None,
            "house_parity": "odd",
            "house_suffix": None,
            "house_step": None,
            "law_reference": "fixture_spb",
        }
    )

    return rows


@pytest.fixture(scope="module")
def spb_matcher_fixture() -> LawRuleMatcher:
    fd, path_str = __import__("tempfile").mkstemp(suffix=".sqlite")
    __import__("os").close(fd)
    path = Path(path_str)
    try:
        db = Database(districts_db_path=str(path))
        db.init_schema()
        db.update_law_rules(_build_fixture_rules(), clear_before=True)
        matcher = LawRuleMatcher(db)
        db.close()
        yield matcher
    finally:
        try:
            path.unlink()
        except OSError:
            pass


# 10 пользовательских проверок (параметризация даёт ровно 10 вызовов assert)
ADDRESS_CASES = [
    ("191028, г. Санкт-Петербург, ул. ALPHA01SPB, д. 1", 1),
    ("Санкт-Петербург, BETA02SPB ул., дом 2", 2),
    ("196000, г. Санкт-Петербург, пр-т GAMMA03SPB, д. 3", 3),
    ("г Санкт-Петербург, переулок DELTA04SPB, д. 4", 4),
    ("Россия, Санкт-Петербург, EPSLN05SPB, стр. 5", 5),
    ("адрес: Санкт-Петербург ZETA06SPB д. 6", 6),
    ("г. Санкт-Петербург, ул. ETA07SPB, д. 7", 7),
    ("191123, Санкт-Петербург, THETA08SPB набережная, д. 8", 8),
    ("Санкт-Петербург, ул. IOTA09SPB, д. 15", 9),
    ("Санкт-Петербург, ул. KAPPA10SPB, д. 11", 10),
]


@pytest.mark.parametrize("address,expected_section", ADDRESS_CASES)
def test_spb_jurisdiction_matches_section(
    spb_matcher_fixture: LawRuleMatcher,
    address: str,
    expected_section: int,
):
    """Адрес в Санкт-Петербурге → ожидаемый номер участка из fixture."""
    res = spb_matcher_fixture.match(address)
    assert res is not None, f"Нет совпадения для: {address}"
    assert int(res.get("section_num") or 0) == expected_section
    assert res.get("region") == "Санкт-Петербург"
