"""
Агрегация поля jurisdiction_html_report из JSON выхода scripts/court_sites_scraper.py.

См. docs/JURISDICTION_HTML_SCRAPING_RU.md (п. 7.4 — отчёт «что помешало»).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple


def normalize_jurisdiction_report(value: Any) -> Optional[Dict[str, Any]]:
    """Из ячейки JSON/CSV-экспорта получить dict отчёта или None."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def status_from_row(row: Dict[str, Any]) -> str:
    rep = normalize_jurisdiction_report(row.get("jurisdiction_html_report"))
    if rep is None:
        return "missing_report"
    st = rep.get("status")
    if st is None or (isinstance(st, str) and not st.strip()):
        return "missing_status"
    return str(st).strip()


def aggregate_scraper_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Сводка по списку записей (как в court_sites_scrape_*.json).

    Возвращает total_rows, by_status (dict str->int), sample_urls_by_status (не-ok, до N URL на статус).
    """
    by_status: Counter[str] = Counter()
    urls_by_status: Dict[str, List[str]] = defaultdict(list)
    max_samples = 5

    for row in rows:
        if not isinstance(row, dict):
            continue
        st = status_from_row(row)
        by_status[st] += 1
        url = str(row.get("source_url") or "").strip()
        if url and st not in ("ok",) and len(urls_by_status[st]) < max_samples:
            urls_by_status[st].append(url)

    return {
        "total_rows": len(rows),
        "by_status": dict(sorted(by_status.items(), key=lambda x: (-x[1], x[0]))),
        "sample_urls_by_status": {k: v for k, v in urls_by_status.items() if v},
    }


def format_text_report(summary: Dict[str, Any], title: str = "") -> str:
    lines: List[str] = []
    if title:
        lines.append(title)
        lines.append("")
    total = summary.get("total_rows", 0)
    by_status = summary.get("by_status") or {}
    samples = summary.get("sample_urls_by_status") or {}
    lines.append(f"Всего записей: {total}")
    lines.append("")
    lines.append("По статусу jurisdiction_html_report:")
    for st, cnt in sorted(by_status.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"  {st}: {cnt}")
    lines.append("")
    if samples:
        lines.append("Примеры URL (не «ok», до 5 на статус):")
        for st in sorted(samples.keys()):
            for u in samples[st]:
                lines.append(f"  [{st}] {u}")
    return "\n".join(lines)


def load_scraper_json(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Ожидается JSON-массив записей скрапера")
    out: List[Dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out


def find_latest_scraper_json(directory: str) -> str:
    from pathlib import Path

    d = Path(directory)
    if not d.is_dir():
        raise FileNotFoundError(f"Нет каталога: {directory}")
    candidates: List[Tuple[float, Path]] = []
    for p in d.glob("court_sites_scrape_*.json"):
        try:
            candidates.append((p.stat().st_mtime, p))
        except OSError:
            continue
    if not candidates:
        raise FileNotFoundError(f"В {directory} нет court_sites_scrape_*.json")
    candidates.sort(key=lambda x: x[0], reverse=True)
    return str(candidates[0][1])
