#!/usr/bin/env python3
"""Тест подсудности: первые 10 клиентов из файла."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_env = ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass

from batch_processing.utils.file_handler import read_file
from batch_processing.services.pipeline import process_batch


def main():
    path = ROOT / "data" / "test_clients_jurisdiction.csv"
    if not path.exists():
        print(f"Файл не найден: {path}")
        return

    debtors = read_file(path)
    print(f"Прочитано записей: {len(debtors)}")
    results = process_batch(debtors[:10])

    print("\n=== Первые 10 результатов ===\n")
    for i, (d, r) in enumerate(zip(debtors[:10], results), 1):
        addr = d.get("address", "—")
        court = r.get("Наименование суда", "—")
        prod = r.get("Тип производства", "—")
        err = r.get("_error_code", "")
        print(f"{i}. Адрес: {addr}")
        print(f"   Суд: {court}")
        print(f"   Тип: {prod}")
        if err:
            print(f"   Ошибка: {err}")
        print()


if __name__ == "__main__":
    main()
