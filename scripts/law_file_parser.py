#!/usr/bin/env python3
"""
Парсинг файла закона о судебных участках (PDF / DOCX / HTML / URL / текст)
и заготовка CSV для law_rules + опциональный импорт в court_districts.sqlite.

Примеры:
  python scripts/law_file_parser.py закон.pdf --region "Нижегородская область"
  python scripts/law_file_parser.py https://docs.cntd.ru/document/... --region "Тамбовская область"
  python scripts/law_file_parser.py закон.docx --region "НО" --law-ref "168-З" --import

  Скан PDF / принудительный OCR:
  python scripts/law_file_parser.py zakon.pdf --region "Тамбовская область" --ocr --dpi 400
  python scripts/law_file_parser.py zakon.pdf --region "Регион" --poppler "C:\\poppler\\Library\\bin"

См. также: GISmap/backend/services/law_parser.py (продвинутый разбор для загрузки в GISmap API).
Требования OCR: Tesseract (rus+eng), Poppler в PATH или --poppler; pip: pdf2image pytesseract opencv-python-headless.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from court_locator.database import Database
from court_locator.law_document_parser import (
    parse_text_to_rule_dicts,
    read_source,
    rules_for_database,
    next_law_rule_start_id,
    write_draft_csv,
)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description="Закон → черновик law_rules (CSV) / опционально БД")
    ap.add_argument("source", help="Путь к PDF/DOCX/HTML/txt или URL")
    ap.add_argument("--region", required=True, help="Субъект РФ (как в law_rules.region)")
    ap.add_argument("--law-ref", default="", help="Подпись к закону для law_reference")
    ap.add_argument(
        "--out",
        default="",
        help="Путь к CSV или каталог (по умолчанию data/law_drafts/law_rules_draft_<region>.csv)",
    )
    ap.add_argument(
        "--import",
        dest="do_import",
        action="store_true",
        help="Записать правила в parser/court_districts.sqlite через Database.update_law_rules",
    )
    ap.add_argument(
        "--db",
        default=str(ROOT / "parser" / "court_districts.sqlite"),
        help="Путь к SQLite с таблицей law_rules",
    )
    ap.add_argument(
        "--clear-before",
        action="store_true",
        help="Очистить таблицу law_rules перед импортом (осторожно)",
    )
    ap.add_argument(
        "--ocr",
        action="store_true",
        help="Принудительный OCR даже для «цифровых» PDF",
    )
    ap.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI для OCR (300 по умолчанию; 400 для мелкого текста)",
    )
    ap.add_argument(
        "--poppler",
        default=None,
        help=r"Каталог bin Poppler (Windows: например C:\poppler\Library\bin)",
    )
    ap.add_argument(
        "--tesseract",
        default=None,
        help=r"Путь к tesseract.exe, если не в PATH",
    )
    ap.add_argument(
        "--ocr-basic",
        action="store_true",
        help="Простой OCR (image_to_string), иначе режим таблиц image_to_data",
    )
    args = ap.parse_args()

    law_ref = (args.law_ref or args.source).strip()
    print(f"Читаю: {args.source}")
    text, fmt = read_source(
        args.source,
        poppler_path=args.poppler,
        force_ocr=args.ocr,
        dpi=args.dpi,
        ocr_tables=not args.ocr_basic,
        tesseract_cmd=args.tesseract,
    )
    print(f"Формат: {fmt}, символов: {len(text):,}")

    rules = parse_text_to_rule_dicts(text, args.region, law_ref)
    print(f"Извлечено черновых правил: {len(rules)}")

    if not rules:
        print("Ничего не найдено — проверьте формат приложения к закону.")
        print("Первые 600 символов текста:")
        print(text[:600])
        sys.exit(1)

    by_sec: dict[str, int] = {}
    for r in rules:
        sn = str(r.get("section_num") or "")
        by_sec[sn] = by_sec.get(sn, 0) + 1
    print("По участкам:")
    for sec in sorted(by_sec.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        print(f"  №{sec}: {by_sec[sec]} строк")

    safe = re.sub(r"[^\w\-]", "_", args.region)[:80]
    default_csv = ROOT / "data" / "law_drafts" / f"law_rules_draft_{safe}.csv"
    if args.out:
        out_path = Path(args.out)
        if out_path.suffix.lower() == ".csv":
            csv_path = out_path
            csv_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path.mkdir(parents=True, exist_ok=True)
            csv_path = out_path / f"law_rules_draft_{safe}.csv"
    else:
        csv_path = default_csv

    write_draft_csv(rules, csv_path)
    print(f"CSV: {csv_path.resolve()}")

    if args.do_import:
        db = Database(districts_db_path=args.db)
        db.init_schema()
        start_id = 1 if args.clear_before else next_law_rule_start_id(db)
        payload = rules_for_database(rules, start_id)
        db.update_law_rules(payload, clear_before=args.clear_before)
        db.close()
        print(f"Импортировано в {args.db}: {len(payload)} правил (clear_before={args.clear_before})")


if __name__ == "__main__":
    main()
