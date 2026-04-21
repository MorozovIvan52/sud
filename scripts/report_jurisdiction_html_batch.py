#!/usr/bin/env python3
"""
Сводка по jurisdiction_html_report из JSON скрапера сайтов судов.

Примеры:
  python scripts/report_jurisdiction_html_batch.py --latest
  python scripts/report_jurisdiction_html_batch.py --input batch_outputs/court_sites_scrape_123.json
  python scripts/report_jurisdiction_html_batch.py --latest --json > summary.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from court_locator.jurisdiction_scrape_aggregate import (
    aggregate_scraper_rows,
    find_latest_scraper_json,
    format_text_report,
    load_scraper_json,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Агрегация jurisdiction_html_report по JSON скрапера.")
    ap.add_argument("--input", type=Path, help="Путь к court_sites_scrape_*.json")
    ap.add_argument("--latest", action="store_true", help="Самый свежий JSON в --latest-dir")
    ap.add_argument(
        "--latest-dir",
        type=Path,
        default=ROOT / "batch_outputs",
        help="Каталог с court_sites_scrape_*.json (по умолчанию batch_outputs)",
    )
    ap.add_argument("--output", type=Path, help="Файл отчёта (иначе stdout)")
    ap.add_argument("--json", action="store_true", help="Вывод машинного JSON вместо текста")
    args = ap.parse_args()

    if args.input:
        path = str(args.input.resolve())
    elif args.latest:
        path = find_latest_scraper_json(str(args.latest_dir.resolve()))
    else:
        ap.error("Укажите --input ПУТЬ.json или --latest")

    rows = load_scraper_json(path)
    summary = aggregate_scraper_rows(rows)
    summary["source_file"] = path

    if args.json:
        out = json.dumps(summary, ensure_ascii=False, indent=2)
    else:
        out = format_text_report(summary, title=f"Файл: {path}")

    if args.output:
        args.output.write_text(out + ("\n" if not out.endswith("\n") else ""), encoding="utf-8")
        print(f"Записано: {args.output}", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
