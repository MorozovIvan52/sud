"""
Извлечение территориальной подсудности из HTML: статусы и отсутствие исключений.

Соответствует чеклисту docs/JURISDICTION_HTML_SCRAPING_RU.md (блок не найден, PDF, картинка, слабая эвристика).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from court_locator.html_jurisdiction_status import analyze_territorial_jurisdiction_html
from court_locator.dagalin_page_parse import parse_dagalin_detail_html


def test_no_jurisdiction_block_not_found() -> None:
    html = """<!DOCTYPE html><html><body>
    <h1>Мировой судебный участок № 1</h1>
    <p>Адрес: г. Москва, ул. Примерная, д. 1</p>
    <p>Телефон: +7 495 000-00-00</p>
    </body></html>"""
    r = analyze_territorial_jurisdiction_html(html, "https://example.com/u1")
    assert r.status == "not_found"
    assert not r.text_snippet
    assert not r.pdf_urls


def test_jurisdiction_text_in_cell_ok() -> None:
    # Оба ключевых фрагмента должны быть в одной ячейке (как часто бывает в одной колонке «описание»).
    html = """<html><body><table>
    <tr><td>Территориальная подсудность судебного участка: к участку относятся жители по ул. Ленина, д. 1–10.</td></tr>
    </table></body></html>"""
    r = analyze_territorial_jurisdiction_html(html, "https://example.com/")
    assert r.status == "ok"
    assert "Ленина" in r.text_snippet
    assert "территориальн" in r.text_snippet.lower()


def test_pdf_link_near_keyword_likely_pdf() -> None:
    html = """<html><body>
    <h2>Территориальная подсудность</h2>
    <p>Скачайте описание: <a href="/docs/boundary.pdf">границы участка (PDF)</a></p>
    </body></html>"""
    r = analyze_territorial_jurisdiction_html(html, "https://sudrf.ru/mir/")
    assert r.status == "likely_pdf_only"
    assert r.pdf_urls
    assert any("boundary.pdf" in u for u in r.pdf_urls)


def test_image_link_likely_image() -> None:
    # Ключевые слова только в общем тексте (не в td/div из шага 1), рядом — ссылка на PNG.
    html = """<html><body>
    <span class="seo">Территориальная подсудность (схема)</span>
    <p>См. файл: <a href="/map/zona.png">zona.png</a></p>
    </body></html>"""
    r = analyze_territorial_jurisdiction_html(html, "https://example.com/")
    assert r.status == "likely_image_only"
    assert r.image_urls


def test_weak_snippet_granic() -> None:
    html = "<html><body><p>Описание границ участка по улицам центра.</p></body></html>"
    r = analyze_territorial_jurisdiction_html(html, "https://example.com/")
    assert r.status == "weak_snippet"
    assert "границ" in r.text_snippet.lower()


def test_parse_dagalin_detail_includes_report_and_no_exception() -> None:
    html = """<html><head><title>Участок 5</title></head><body>
    <h1>Мировой судебный участок № 5</h1>
    <table>
    <tr><td>Адрес</td><td>г. Тула, ул. Советская, 1</td></tr>
    <tr><td>Территориальная подсудность: жители микрорайона А.</td></tr>
    </table></body></html>"""
    parsed = parse_dagalin_detail_html(html, "https://dagalin.org/courts/71/wc/avt5")
    assert "jurisdiction_html_report" in parsed
    assert parsed["jurisdiction_html_report"]["status"] == "ok"
    assert "микрорайон" in (parsed["court_card"].get("boundary_snippet") or "")


def test_malformed_html_still_returns_report() -> None:
    r = analyze_territorial_jurisdiction_html("<html>незакрытый", "https://x/")
    assert r.status in ("not_found", "weak_snippet", "ok", "error")
    assert isinstance(r.reasons, list)


def test_dagalin_requisites_row_inn_extracted_not_raises() -> None:
    html = """<html><body><h1>Участок 2</h1><table>
    <tr><td>ИНН</td><td>7707083893</td></tr>
    <tr><td>КПП</td><td>770701001</td></tr>
    </table></body></html>"""
    parsed = parse_dagalin_detail_html(html, "https://dagalin.org/courts/71/wc/avt2")
    req = parsed.get("state_fee_requisites") or {}
    assert req.get("inn") == "7707083893"
    assert req.get("kpp") == "770701001"
