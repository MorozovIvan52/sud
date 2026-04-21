"""Агрегация jurisdiction_html_report по JSON скрапера."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from court_locator.jurisdiction_scrape_aggregate import (
    aggregate_scraper_rows,
    format_text_report,
    load_scraper_json,
    normalize_jurisdiction_report,
    status_from_row,
)


def test_normalize_string_and_dict() -> None:
    d = {"status": "ok", "reasons": []}
    assert normalize_jurisdiction_report(d) == d
    assert normalize_jurisdiction_report(json.dumps(d, ensure_ascii=False)) == d
    assert normalize_jurisdiction_report(None) is None
    assert normalize_jurisdiction_report("") is None


def test_aggregate_counts_and_samples() -> None:
    rows = [
        {
            "source_url": "https://a.example/u1",
            "jurisdiction_html_report": {"status": "ok"},
        },
        {
            "source_url": "https://a.example/u2",
            "jurisdiction_html_report": json.dumps({"status": "likely_pdf_only"}, ensure_ascii=False),
        },
        {
            "source_url": "https://a.example/u3",
            "jurisdiction_html_report": {"status": "likely_pdf_only"},
        },
        {"source_url": "https://a.example/u4", "jurisdiction_html_report": None},
    ]
    s = aggregate_scraper_rows(rows)
    assert s["total_rows"] == 4
    assert s["by_status"]["ok"] == 1
    assert s["by_status"]["likely_pdf_only"] == 2
    assert s["by_status"]["missing_report"] == 1
    text = format_text_report(s)
    assert "likely_pdf_only: 2" in text
    assert "https://a.example/u2" in text or "https://a.example/u3" in text


def test_load_scraper_json_roundtrip() -> None:
    payload = [
        {"source_url": "https://x", "jurisdiction_html_report": {"status": "not_found", "reasons": ["a"]}},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        name = f.name
    try:
        loaded = load_scraper_json(name)
        assert loaded == payload
    finally:
        Path(name).unlink(missing_ok=True)


def test_status_from_row_missing_status() -> None:
    assert status_from_row({"jurisdiction_html_report": {}}) == "missing_status"
