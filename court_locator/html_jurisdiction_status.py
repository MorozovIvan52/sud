"""
Диагностика извлечения «территориальной подсудности» из HTML страницы суда.

Цель: не падать; явно помечать случаи «блок не найден», «только PDF/картинка», слабые эвристики.
Используется скраперами и тестами (docs/JURISDICTION_HTML_SCRAPING_RU.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# Ключевые фразы для поиска блока (расширяйте при смене шаблонов сайтов)
JURISDICTION_KEY_PHRASES = (
    "территориальн",
    "подсудност",
    "к подсудности судебного участка",
    "в пределах территории",
    "границ территории",
)

PDF_EXT = (".pdf",)
IMG_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _text_has_jurisdiction_kw(low: str) -> bool:
    return any(p in low for p in JURISDICTION_KEY_PHRASES)


@dataclass
class TerritorialJurisdictionHtmlReport:
    """Итог разбора HTML с точки зрения подсудности."""

    status: str
    """ok | not_found | likely_pdf_only | likely_image_only | weak_snippet | error"""

    text_snippet: str = ""
    """Лучший извлечённый текст из HTML (может быть пустым)."""

    reasons: List[str] = field(default_factory=list)
    """Человекочитаемые причины / зацепки для логов и отчётов."""

    pdf_urls: List[str] = field(default_factory=list)
    image_urls: List[str] = field(default_factory=list)


def analyze_territorial_jurisdiction_html(html: str, base_url: str = "") -> TerritorialJurisdictionHtmlReport:
    """
    Анализирует HTML без сетевых запросов.

    - При отсутствии осмысленного текста, но со ссылками на PDF рядом с ключевыми словами — likely_pdf_only.
    - Картинки с подписью/рядом с ключевыми словами — likely_image_only.
    - Текст с «территориальн»+«подсудн» в ячейке — ok.
    """
    reasons: List[str] = []
    pdf_urls: List[str] = []
    image_urls: List[str] = []
    text_snippet = ""

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        return TerritorialJurisdictionHtmlReport(
            status="error",
            reasons=[f"BeautifulSoup: {e}"],
        )

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    full_text = _clean(soup.get_text(" "))
    full_low = full_text.lower()

    # 1) Текст в ячейках (как dagalin)
    best_len = 0
    for cell in soup.find_all(["td", "th", "p", "div", "li", "section", "article"]):
        ctext = _clean(cell.get_text())
        low = ctext.lower()
        if "территориальн" in low and "подсудн" in low:
            if len(ctext) > best_len:
                text_snippet = ctext
                best_len = len(ctext)

    if text_snippet:
        reasons.append("Найден HTML-блок с «территориальн» и «подсудн».")
        return TerritorialJurisdictionHtmlReport(
            status="ok",
            text_snippet=text_snippet,
            reasons=reasons,
            pdf_urls=pdf_urls,
            image_urls=image_urls,
        )

    # 2) Ссылки PDF / изображения рядом с якорным текстом
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        low_h = href.lower()
        is_pdf = low_h.endswith(PDF_EXT)
        is_img = any(low_h.endswith(ext) for ext in IMG_EXT)
        if not is_pdf and not is_img:
            continue
        ctx = _clean((a.get_text() or "") + " " + _clean(a.parent.get_text() if a.parent else ""))
        ctx_low = ctx.lower()
        par_low = ""
        if a.parent and a.parent.parent:
            par_low = _clean(a.parent.parent.get_text()).lower()
        blob = ctx_low + " " + par_low
        if _text_has_jurisdiction_kw(blob) or _text_has_jurisdiction_kw(full_low):
            abs_url = urljoin(base_url, href) if base_url else href
            if is_pdf:
                pdf_urls.append(abs_url)
                reasons.append(f"Ссылка на PDF рядом с контекстом подсудности: {abs_url[:80]}")
            else:
                image_urls.append(abs_url)
                reasons.append(f"Ссылка на изображение: {abs_url[:80]}")

    pdf_urls = list(dict.fromkeys(pdf_urls))
    image_urls = list(dict.fromkeys(image_urls))

    if pdf_urls and not text_snippet:
        return TerritorialJurisdictionHtmlReport(
            status="likely_pdf_only",
            text_snippet="",
            reasons=reasons or ["Подсудность вероятно только в PDF (HTML-текста нет)."],
            pdf_urls=pdf_urls,
            image_urls=image_urls,
        )
    if image_urls and not text_snippet:
        return TerritorialJurisdictionHtmlReport(
            status="likely_image_only",
            text_snippet="",
            reasons=reasons or ["Подсудность вероятно в виде изображения/скана."],
            pdf_urls=pdf_urls,
            image_urls=image_urls,
        )

    # 3) Слабая эвристика — только «границ» (как в court_sites_scraper)
    if "границ" in full_low:
        idx = full_low.find("границ")
        frag = _clean(full_text[max(0, idx - 80) : idx + 220])
        reasons.append("Только фрагмент по слову «границ» без явного блока подсудности.")
        return TerritorialJurisdictionHtmlReport(
            status="weak_snippet",
            text_snippet=frag,
            reasons=reasons,
            pdf_urls=pdf_urls,
            image_urls=image_urls,
        )

    if _text_has_jurisdiction_kw(full_low):
        reasons.append("Ключевые слова есть в общем тексте, но выделить блок не удалось (разметка).")
        return TerritorialJurisdictionHtmlReport(
            status="weak_snippet",
            text_snippet=full_text[:500],
            reasons=reasons,
            pdf_urls=pdf_urls,
            image_urls=image_urls,
        )

    reasons.append("Блок территориальной подсудности в HTML не обнаружен.")
    return TerritorialJurisdictionHtmlReport(
        status="not_found",
        text_snippet="",
        reasons=reasons,
        pdf_urls=pdf_urls,
        image_urls=image_urls,
    )


def report_to_dict(r: TerritorialJurisdictionHtmlReport) -> dict:
    return {
        "status": r.status,
        "text_snippet": r.text_snippet,
        "reasons": list(r.reasons),
        "pdf_urls": list(r.pdf_urls),
        "image_urls": list(r.image_urls),
    }
