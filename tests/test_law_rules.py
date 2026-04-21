import os
import tempfile

import pytest

from court_locator.database import Database
from court_locator.law_rules import LawRuleMatcher


def test_law_rule_match_street_and_house():
    # temp db file
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    db = Database(districts_db_path=path)
    db.init_schema()
    db.update_law_rules(
        [
            {
                "id": 1,
                "section_num": "1",
                "region": "Нижегородская область",
                "area_text": "Нижний Новгород",
                "street_pattern": r"ул\.\s*Ватутина",
                "house_from": 1,
                "house_to": 20,
                "law_reference": "Закон НО",
            }
        ],
        clear_before=True,
    )
    matcher = LawRuleMatcher(db)
    res = matcher.match("603950, г. Нижний Новгород, ул. Ватутина, д. 10А")
    assert res is not None
    assert res.get("section") == "1" or res.get("section_num") == "1" or "1" in res.get("court_name", "")
    assert res.get("source") in (
        "law_rules",
        "law_rules_nlp",
        "law_rules_nlp_fuzzy",
        "law_rules_area",
    )
    db.close()


def test_fuzzy_lemma_matches_genitive_street():
    """Fuzzy: в правиле основа «Октябрьск», в адресе «Октябрьской» — леммы совпадают по корню."""
    pytest.importorskip("spacy")
    from court_locator.law_rules import _fuzzy_pattern_lemma_match
    from court_locator.ru_nlp import spacy_lemmas

    addr = "г. Самара, ул. Октябрьской, д. 5"
    lemmas = spacy_lemmas(addr)
    assert _fuzzy_pattern_lemma_match(r"(?i)октябрьск", lemmas)
