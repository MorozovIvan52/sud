#!/usr/bin/env python3
"""
Подготовка к запуску и первый тест определения подсудности.
Пример: новый адрес и ФИО (Санкт-Петербург, Невский проспект).
Запуск из корня проекта: python first_test_jurisdiction.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def prepare():
    """Инициализация БД судов и тестовые данные (Москва + СПб)."""
    print("=== Подготовка БД ===")
    sys.path.insert(0, str(ROOT / "parser"))
    from courts_db import init_db, seed_example_data
    init_db()
    seed_example_data()
    print("БД courts.sqlite инициализирована, добавлены тестовые суды (Москва Тверской, СПб Центральный).")
    print()


def first_test_parser():
    """Первый тест: Parser (подсудность по ФИО, паспорту, адресу)."""
    sys.path.insert(0, str(ROOT / "parser"))
    from courts_db import init_db, seed_example_data
    from super_parser import super_determine_jurisdiction, state_duty_from_debt

    init_db()
    seed_example_data()

    # Новый пример: ФИО и адрес (Санкт-Петербург, Невский проспект)
    data = {
        "fio": "Петрова Мария Сергеевна",
        "passport": "780 456789",
        "address": "г. Санкт-Петербург, Невский проспект, д. 5",
        "debt_amount": 75000.0,
    }

    print("=== Тест 1: Parser (подсудность) ===")
    print("Входные данные:")
    print("  ФИО:", data["fio"])
    print("  Паспорт:", data["passport"])
    print("  Адрес:", data["address"])
    print("  Сумма долга:", data["debt_amount"], "руб.")
    print()

    result = super_determine_jurisdiction(data, use_cache=True)
    print("Результат:")
    print("  Суд:", result.court_name)
    print("  Адрес суда:", result.court_address)
    print("  Источник:", result.source)
    print("  Уверенность:", result.confidence)
    if getattr(result, "rekvizity_url", None):
        print("  Реквизиты:", result.rekvizity_url)
    if getattr(result, "kbk", None):
        print("  КБК:", result.kbk)

    duty = state_duty_from_debt(data["debt_amount"])
    print("  Госпошлина (ориентир):", duty, "руб.")
    print()
    return result


def first_test_court_locator():
    """Первый тест: court_locator (поиск суда по адресу и по координатам)."""
    from court_locator.main import CourtLocator

    # Тот же адрес и координаты центра СПб (Невский)
    address = "г. Санкт-Петербург, Невский проспект, д. 5"
    lat, lng = 59.9343, 30.3351

    print("=== Тест 2: Court locator ===")
    print("По адресу:", address)
    finder = CourtLocator(use_cache=True)
    by_address = finder.locate_court(address=address)
    if by_address:
        print("  Суд:", by_address.get("court_name", "")[:60])
        print("  Адрес суда:", by_address.get("address", "")[:60])
        print("  Источник:", by_address.get("source"))
    else:
        print("  Суд не найден")
    print()

    print("По координатам (Невский пр.): lat=%s, lng=%s" % (lat, lng))
    by_coords = finder.locate_court(lat=lat, lng=lng)
    if by_coords:
        print("  Суд:", by_coords.get("court_name", "")[:60])
        print("  Источник:", by_coords.get("source"))
    else:
        print("  Суд не найден")
    finder.close()
    print()


def main():
    print("ПарсерСуд — первый тест определения подсудности")
    print("=" * 60)
    prepare()
    first_test_parser()
    first_test_court_locator()
    print("=" * 60)
    print("Первый тест завершён. Подробности — в выводе выше.")


if __name__ == "__main__":
    main()
