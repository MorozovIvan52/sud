"""
Сводный запуск тестов. Из корня проекта: python tests_run.py
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


def run_parser_tests():
    print("\n=== Parser (run_tests.py) ===")
    sys.path.insert(0, str(ROOT / "parser"))
    try:
        from run_tests import test_imports, test_podsudnost
        test_imports()
        test_podsudnost()
        print("Parser: OK")
        return True
    except Exception as e:
        print("Parser: FAIL:", e)
        return False


def run_court_locator_tests():
    print("\n=== Court locator ===")
    try:
        from court_locator.main import CourtLocator
        finder = CourtLocator()
        # По координатам (должен найти суд при наличии в БД с coordinates)
        r = finder.locate_court(lat=55.7558, lng=37.6173)
        ok_coord = r and r.get("court_name")
        if ok_coord:
            print("[OK] По координатам:", r.get("court_name", "")[:50], "| источник:", r.get("source"))
        else:
            print("[--] По координатам: суд не найден")
        # По адресу (зависит от DaData/Yandex и БД)
        r2 = finder.locate_court(address="г. Москва, ул. Тверская, д. 15")
        ok_addr = r2 and r2.get("court_name")
        if ok_addr:
            print("[OK] По адресу:", r2.get("court_name", "")[:50], "| источник:", r2.get("source"))
        else:
            print("[--] По адресу: суд не найден (нужны YANDEX_GEO_KEY/DADATA_TOKEN или БД по району)")
        finder.close()
        print("Court locator: OK (хотя бы один способ)")
        return ok_coord or ok_addr
    except Exception as e:
        print("Court locator: FAIL:", e)
        return False


def run_parser_locator_alignment_test():
    """
    Интеграционный тест: для одного и того же места (Москва, Тверская) суд от Parser
    и суд от court_locator должны совпадать по court_name (или по номеру участка/району).
    """
    print("\n=== Согласованность Parser и Court locator ===")
    try:
        sys.path.insert(0, str(ROOT / "parser"))
        from courts_db import init_db, seed_example_data
        from jurisdiction import determine_jurisdiction

        init_db()
        seed_example_data()

        # Те же данные, что в test_podsudnost: паспорт 7709 (Москва) + адрес с Тверской
        data = {
            "fio": "Иванов Иван Иванович",
            "passport": "7709 123456",
            "address": "г. Москва, ул. Тверская, д. 15",
            "debt_amount": 150000.0,
        }
        parser_result = determine_jurisdiction(data)
        parser_court = (parser_result.court_name or "").strip()
        parser_has_district = "Тверского" in parser_court and "123" in parser_court

        from court_locator.main import CourtLocator
        finder = CourtLocator()
        locator_by_addr = finder.locate_court(address="г. Москва, ул. Тверская, д. 15")
        locator_by_coord = finder.locate_court(lat=55.7558, lng=37.6173)
        finder.close()

        locator_court_addr = (locator_by_addr.get("court_name") or "").strip() if locator_by_addr else ""
        locator_court_coord = (locator_by_coord.get("court_name") or "").strip() if locator_by_coord else ""

        # Совпадение по адресу: тот же суд (по имени или по участку/району)
        if parser_court and locator_court_addr:
            same_by_name = parser_court == locator_court_addr
            same_by_section = "123" in parser_court and "123" in locator_court_addr and "Тверского" in locator_court_addr
            if same_by_name or same_by_section:
                print("[OK] По адресу: Parser и Court locator вернули один суд (№ 123 Тверского района)")
            else:
                print("[!!] По адресу: расхождение — Parser:", parser_court[:50], "| Locator:", locator_court_addr[:50])
        else:
            print("[--] По адресу: сравнение пропущено (Parser=%s, Locator=%s)" % (bool(parser_court), bool(locator_court_addr)))

        # По координатам: при наличии YANDEX_GEO_KEY ожидаем тот же суд (coordinates_district или address_district)
        if parser_court and locator_court_coord:
            same_coord = parser_court == locator_court_coord or ("123" in parser_court and "123" in locator_court_coord and "Тверского" in locator_court_coord)
            if same_coord:
                print("[OK] По координатам: Parser и Court locator вернули один суд")
            else:
                print("[--] По координатам: другой источник (нужен YANDEX_GEO_KEY для coordinates_district) — Locator:", locator_court_coord[:50])
        else:
            print("[--] По координатам: сравнение пропущено")

        ok = True
        if parser_has_district and locator_court_addr and parser_court != locator_court_addr:
            if "123" not in locator_court_addr or "Тверского" not in locator_court_addr:
                ok = False
        print("Согласованность: OK" if ok else "Согласованность: проверьте вручную")
        return ok
    except Exception as e:
        print("Согласованность: FAIL:", e)
        return False


def run_check_apis():
    print("\n=== Проверка API (кроме DaData) ===")
    try:
        import parser.check_apis as check_apis
        check_apis.main()
    except Exception as e:
        print("Check APIs error:", e)


def main():
    print("Запуск тестов проекта ПарсерСуд")
    results = []
    results.append(("Parser", run_parser_tests()))
    results.append(("Court locator", run_court_locator_tests()))
    results.append(("Parser vs Locator", run_parser_locator_alignment_test()))
    run_check_apis()

    print("\n" + "=" * 50)
    print("Результаты тестов:")
    for name, ok in results:
        print("  %s: %s" % (name, "PASS" if ok else "FAIL"))
    all_ok = all(r[1] for r in results)
    print("=" * 50)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
