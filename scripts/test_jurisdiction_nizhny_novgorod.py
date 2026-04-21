#!/usr/bin/env python3
"""Тест подсудности: клиенты из Нижнего Новгорода (формат файла от клиента)."""
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
    path = ROOT / "data" / "test_clients_nizhny_novgorod.csv"
    if not path.exists():
        print(f"Файл не найден: {path}")
        return

    debtors = read_file(path)
    print(f"Прочитано записей: {len(debtors)}")
    results = process_batch(debtors)

    print("\n=== Подсудность: Нижний Новгород ===\n")
    for i, (d, r) in enumerate(zip(debtors, results), 1):
        fio = d.get("fio", "—")
        addr = d.get("address", "—")
        court = r.get("Наименование суда", "—")
        source = r.get("Источник данных", "—")
        prod = r.get("Тип производства", "—")
        err = r.get("_error_code", "")
        print(f"{i}. {fio}")
        print(f"   Адрес: {addr}")
        print(f"   Суд: {court}")
        print(f"   Источник: {source}")
        print(f"   Тип: {prod}")
        if err:
            print(f"   Ошибка: {err}")
        print()


if __name__ == "__main__":
    main()
