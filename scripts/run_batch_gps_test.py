#!/usr/bin/env python3
"""
Тест пакетной обработки по GPS-координатам (без парсинга адресов).
"""
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

from batch_processing import process_debtor_gps, process_batch_gps
from batch_processing.utils.file_handler import read_file_gps, validate_coordinates
from batch_processing.services.output_generator import generate_xlsx


def main():
    print("=== Тест одного запроса по GPS ===")
    r = process_debtor_gps(55.7558, 37.6173, debt_amount=15000, case_type="Гражданское")
    print(f"Суд: {r.get('Наименование суда')}")
    print(f"Госпошлина: {r.get('Госпошлина, руб.')}")
    print()

    print("=== Валидация координат ===")
    ok, err = validate_coordinates(55.0, 37.0)
    print(f"55, 37: ok={ok}")
    ok, err = validate_coordinates(100, 37)
    print(f"100, 37: {err}")
    print()

    print("=== Тест батча из CSV ===")
    csv_path = ROOT / "parser" / "data" / "batch_gps_test.csv"
    if csv_path.exists():
        rows = read_file_gps(csv_path)
        print(f"Прочитано {len(rows)} записей")
        results = process_batch_gps(rows)
        for i, res in enumerate(results):
            print(f"  {i+1}. {res.get('Наименование суда', '—')[:50]}")
        out = ROOT / "batch_outputs" / "test_batch_gps.xlsx"
        out.parent.mkdir(exist_ok=True)
        generate_xlsx(results, out)
        print(f"Сохранено: {out}")
    else:
        print(f"Файл не найден: {csv_path}")
    print("Готово.")


if __name__ == "__main__":
    main()
