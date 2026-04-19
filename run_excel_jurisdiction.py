#!/usr/bin/env python3
"""
Excel / CSV → подсудность (мировой суд): один скрипт из корня репозитория.

Требования: pip install -r requirements.txt (и python -m spacy download ru_core_news_sm)

Перед запуском скопируйте env.quickstart.example в .env и вставьте ключи API.

Примеры:
  python run_excel_jurisdiction.py адреса.xlsx
  python run_excel_jurisdiction.py адреса.xlsx -o результат.xlsx
  python run_excel_jurisdiction.py --template шаблон.xlsx
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _env_hints() -> None:
    from court_locator.config import use_postgis_for_spatial_search

    y = (os.getenv("YANDEX_GEO_KEY") or os.getenv("YANDEX_GEOCODER_API_KEY") or "").strip()
    d = (os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or "").strip()
    print("Проверка ключей (.env):")
    print(f"  YANDEX_GEO_KEY:     {'задан' if y else 'НЕТ — геокод хуже, возможны промахи'}")
    print(f"  DADATA_TOKEN:       {'задан' if d else 'НЕТ — без подсказки суда по ФИАС-адресу'}")
    spatial = use_postgis_for_spatial_search()
    pg = (os.getenv("PG_DSN") or "").strip()
    if spatial and pg:
        print("  PostGIS полигоны:   включены (COURTS_SPATIAL_BACKEND=postgis + PG_DSN)")
    elif spatial and not pg:
        print("  PostGIS:            включён в .env, но PG_DSN пуст — откат на SQLite-полигоны")
    else:
        print("  PostGIS полигоны:   выкл. (SQLite court_districts.sqlite при наличии файла)")
    print()


def _write_template(path: Path) -> None:
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "ФИО": "Иванов Иван Иванович",
                "Адрес": "г. Москва, ул. Тверская, д. 1",
                "Сумма": 15000,
            }
        ]
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False)
    print(f"Шаблон сохранён: {path.resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Определение подсудности по Excel/CSV (колонка «Адрес» обязательна).",
    )
    parser.add_argument(
        "input",
        type=str,
        nargs="?",
        default=None,
        help="Путь к .xlsx / .xls / .csv",
    )
    parser.add_argument("--out", "-o", type=str, default=None, help="Выходной XLSX")
    parser.add_argument("--limit", "-n", type=int, default=None, help="Только первые N строк")
    parser.add_argument(
        "--template",
        type=str,
        metavar="FILE",
        help="Создать пример входного Excel и выйти",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Не выводить подсказки по .env")
    args = parser.parse_args()

    if args.template:
        _write_template(Path(args.template))
        return 0

    if not args.input:
        parser.error("Укажите файл или используйте --template шаблон.xlsx")

    path = Path(args.input)
    if not path.exists():
        print(f"Файл не найден: {path}", file=sys.stderr)
        return 1

    if not args.quiet:
        _env_hints()

    from batch_processing.services.output_generator import generate_xlsx
    from batch_processing.services.pipeline import process_batch
    from batch_processing.utils.file_handler import read_file

    try:
        debtors = read_file(path)
    except Exception as e:
        print(f"Ошибка чтения файла: {e}", file=sys.stderr)
        return 1

    if not debtors:
        print(
            "Нет строк с колонкой «ФИО» или «Адрес». Нужны заголовки: Адрес (или address), "
            "опционально ФИО, Сумма, Широта/Долгота.",
            file=sys.stderr,
        )
        print(f"Создайте пример: python {Path(__file__).name} --template шаблон.xlsx", file=sys.stderr)
        return 1

    if args.limit:
        debtors = debtors[: args.limit]

    print(f"Обработка записей: {len(debtors)}…")
    results = process_batch(debtors)

    out_path = Path(args.out) if args.out else path.parent / f"{path.stem}_подсудность.xlsx"
    generate_xlsx(results, out_path)

    try:
        import pandas as pd

        summary = []
        for d, r in zip(debtors, results):
            summary.append(
                {
                    "ID": d.get("id", ""),
                    "Номер договора": d.get("contract_number", ""),
                    "Адрес регистрации": d.get("address", ""),
                    "Наименование суда": r.get("Наименование суда", ""),
                    "Адрес суда": r.get("Адрес суда", ""),
                    "Код суда": r.get("Код суда", ""),
                    "Тип производства": r.get("Тип производства", ""),
                    "Источник данных": r.get("Источник данных", ""),
                }
            )
        with pd.ExcelWriter(out_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            pd.DataFrame(summary).to_excel(writer, sheet_name="Сводка", index=False)
    except Exception:
        pass

    ok = sum(1 for r in results if r.get("Наименование суда"))
    err = len(results) - ok
    print(f"Готово: {out_path.resolve()}")
    print(f"Успешно (найден суд): {ok}, с ошибкой / не найдено: {err}")
    if err and not (os.getenv("YANDEX_GEO_KEY") or os.getenv("DADATA_TOKEN")):
        print("Подсказка: задайте YANDEX_GEO_KEY и DADATA_TOKEN в .env для лучшего качества.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
