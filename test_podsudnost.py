# Тест определения подсудности. Запуск из папки parser: python test_podsudnost.py

import sys
import time
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parent))

from courts_db import init_db, seed_example_data
from super_parser import super_determine_jurisdiction, state_duty_from_debt


@contextmanager
def timing(action_name: str):
    start = time.time()
    try:
        yield
    finally:
        print(f"Время выполнения {action_name}: {time.time() - start:.2f} сек")


def main():
    with timing("Инициализация БД"):
        init_db()
        seed_example_data()

    data = {
        "fio": "Иванов Иван Иванович",
        "passport": "7709 123456",
        "address": "Москва, ул. Ленина 15",
        "debt_amount": 150000.0,
    }

    with timing("Определение подсудности"):
        result = super_determine_jurisdiction(data, use_cache=True)
        print("Суд:", result.court_name)
        print("Адрес суда:", result.court_address)
        print("Confidence:", result.confidence)
        print("Источник:", result.source)
        print("Реквизиты:", result.rekvizity_url)
        print("КБК:", result.kbk)

    with timing("Расчет госпошлины"):
        duty = state_duty_from_debt(data["debt_amount"])
        print("Госпошлина (ориентир):", duty, "руб.")

    print("\n[OK] Тест подсудности пройден.")


if __name__ == "__main__":
    main()
