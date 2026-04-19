"""
Тест модуля court_locator. Запуск из корня проекта:
  python -m court_locator.test_court_locator
  python court_locator/test_court_locator.py
"""
import sys
from pathlib import Path

# Корень проекта в path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Загрузка .env
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def test_court_locator():
    from court_locator.main import CourtLocator

    finder = CourtLocator()

    # Тест 1: по адресу (требуется YANDEX_GEO_KEY или DADATA_TOKEN и заполненная БД судов)
    result = finder.locate_court(address="г. Москва, ул. Тверская, д. 15")
    if result:
        print(f"[OK] По адресу: {result.get('court_name', '')[:60]}")
        print(f"     Адрес суда: {result.get('address', '')[:60]}")
        print(f"     Источник: {result.get('source', '')}")
    else:
        print("[--] По адресу: суд не найден (проверьте YANDEX_GEO_KEY/DADATA_TOKEN и БД courts.sqlite)")

    # Тест 2: по координатам (Москва, центр)
    result = finder.locate_court(lat=55.7558, lng=37.6173)
    if result:
        print(f"[OK] По координатам: {result.get('court_name', '')[:60]}")
        print(f"     Источник: {result.get('source', '')}")
    else:
        print("[--] По координатам: суд не найден (нужны суды с coordinates в БД или court_districts с полигонами)")

    finder.close()
    print("\nТесты завершены.")


if __name__ == "__main__":
    test_court_locator()
