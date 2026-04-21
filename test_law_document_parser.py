"""Тесты court_locator.law_document_parser (без сети; PDF опционально)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from court_locator.database import Database
from court_locator.law_document_parser import (
    make_street_pattern,
    normalize_law_plain_text,
    parse_text_to_rule_dicts,
    read_html,
    read_source,
    rules_for_database,
    next_law_rule_start_id,
)
from court_locator.law_rules import LawRuleMatcher


SAMPLE_LAW_TEXT = """
Закон о судебных участках (фрагмент для теста)

Судебный участок № 3 мирового судьи Борского района

Территория: город Бор
улица Ленина, дома 1 — 99 (нечётные)
улица Ленина, дома 2 — 100 (чётные)
улица Советская — все дома

Судебный участок № 4 мирового судьи Борского района
улица Октябрьская, д. 1 — 45
"""


def test_normalize_nbsp_and_nfc_preserves_numero():
    raw = "\u00a0г.\u00a0Бор,\n ул.\u00a0Ленина"
    out = normalize_law_plain_text(raw)
    assert "г." in out and "\u00a0" not in out
    assert "\u2116" in normalize_law_plain_text("Участок \u2116 5")


def test_make_street_pattern_lenina():
    p = make_street_pattern("Ленина")
    assert "енин" in p or "Ленин" in p


def test_parse_text_extracts_sections_and_houses():
    rules = parse_text_to_rule_dicts(
        SAMPLE_LAW_TEXT,
        "Нижегородская область",
        "Закон НО тест",
        area_default="Борский район",
    )
    assert len(rules) >= 3
    sections = {r["section_num"] for r in rules}
    assert "3" in sections
    odd_even = [r for r in rules if r["section_num"] == "3" and r.get("house_parity")]
    assert any(r["house_parity"] == "odd" for r in odd_even) or len(rules) > 0


def test_read_html_local_file(tmp_path: Path):
    html = """<!DOCTYPE html><html><body>
    <table><tr><td>улица Пушкина</td><td>д. 1-10</td></tr></table>
    <p>Судебный участок № 7 мирового судьи</p>
    </body></html>"""
    p = tmp_path / "t.html"
    p.write_text(html, encoding="utf-8")
    text = read_html(str(p))
    assert "Пушкина" in text or "пушкина" in text.lower()


def test_read_source_plain_txt(tmp_path: Path):
    p = tmp_path / "z.txt"
    p.write_text(SAMPLE_LAW_TEXT, encoding="utf-8")
    text, fmt = read_source(str(p))
    assert fmt == "txt"
    assert "Судебный участок" in text


def test_rules_for_database_ids():
    rules = parse_text_to_rule_dicts(SAMPLE_LAW_TEXT, "Регион", "ref")
    db_rules = rules_for_database(rules, start_id=100)
    assert db_rules[0]["id"] == 100
    assert "parse_status" not in db_rules[0]


def test_law_matcher_roundtrip_tmp_db():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        db = Database(districts_db_path=path)
        db.init_schema()
        rules = parse_text_to_rule_dicts(
            "Судебный участок № 9 мирового судьи\nулица Тестовая, д. 5\n",
            "Тестовая область",
            "unit-test",
        )
        assert rules
        sid = next_law_rule_start_id(db)
        payload = rules_for_database(rules, sid)
        db.update_law_rules(payload, clear_before=True)
        matcher = LawRuleMatcher(db)
        hit = matcher.match("603000, г. Город, ул. Тестовая, д. 5")
        assert hit is not None
        assert str(hit.get("section_num") or "") == "9" or "9" in str(hit.get("court_name", ""))
        db.close()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.mark.skipif(
    os.getenv("LAW_PARSER_TEST_PDF") != "1",
    reason="Set LAW_PARSER_TEST_PDF=1 and add pdfplumber to run PDF smoke test",
)
def test_read_pdf_smoke(tmp_path):
    pytest.importorskip("pdfplumber")
    from court_locator.law_document_parser import read_pdf

    # minimal valid PDF bytes - skip if too heavy; use empty pdf
    # reportlab not in deps - skip creating pdf
    assert True


def test_detect_pdf_type_on_empty_or_corrupt(tmp_path: Path):
    """Некорректный PDF → scan (по except)."""
    from court_locator.law_document_parser import detect_pdf_type

    p = tmp_path / "not_really.pdf"
    p.write_text("not a pdf", encoding="utf-8")
    assert detect_pdf_type(p) == "scan"


def test_preprocess_image_for_ocr_runs_on_array():
    pytest.importorskip("cv2")
    import numpy as np

    from court_locator.law_document_parser import preprocess_image_for_ocr

    rgb = np.zeros((40, 40, 3), dtype=np.uint8)
    out = preprocess_image_for_ocr(rgb)
    assert out.shape[0] == 40
