#!/usr/bin/env python3
"""
Тест пакетной обработки: создаёт тестовый CSV, обрабатывает через pipeline, выводит результат.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Загрузка .env
_env = ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass

from batch_processing.utils.file_handler import read_csv, read_file
from batch_processing.services.pipeline import process_batch, process_debtor
from batch_processing.services.output_generator import generate_xlsx, generate_csv


def main():
    # 1. Тест одного должника
    print("=== Тест одного должника ===")
    r = process_debtor(
        fio="Петрова Мария Сергеевна",
        address="г. Санкт-Петербург, Невский проспект, д. 5",
        debt_amount=15000,
    )
    print(f"Суд: {r.get('Наименование суда')}")
    print(f"Госпошлина: {r.get('Госпошлина, руб.')}")
    print()

    # 2. Тест батча из списка
    print("=== Тест батча ===")
    debtors = [
        {"fio": "Иванов И.И.", "address": "Москва, ул. Тверская 1", "debt_amount": 20000},
        {"fio": "Сидорова А.А.", "address": "Санкт-Петербург, Невский пр. 10", "debt_amount": 5000},
    ]
    results = process_batch(debtors)
    for i, res in enumerate(results):
        print(f"  {i+1}. {res.get('Наименование суда', '—')[:50]}")
    print()

    # 3. Создать тестовый CSV и обработать
    test_csv = ROOT / "parser" / "data" / "batch_test.csv"
    test_csv.parent.mkdir(parents=True, exist_ok=True)
    test_csv.write_text(
        "ФИО;Адрес;Сумма\n"
        "Петров П.П.;Москва, ул. Тверская 1;15000\n"
        "Сидорова А.А.;Санкт-Петербург, Невский пр. 10;20000\n",
        encoding="utf-8-sig",
    )
    print(f"Создан тестовый файл: {test_csv}")

    debtors = read_file(test_csv)
    results = process_batch(debtors)
    out_xlsx = ROOT / "batch_outputs" / "test_batch.xlsx"
    out_xlsx.parent.mkdir(exist_ok=True)
    generate_xlsx(results, out_xlsx)
    print(f"Результат сохранён: {out_xlsx}")
    print("Готово.")


if __name__ == "__main__":
    main()
