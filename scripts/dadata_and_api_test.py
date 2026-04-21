#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сценарий получения данных из DaData и тестирования court_locator API.

1. DaData: Profile API (баланс, статистика, версии) + suggest/court (суды по адресу)
2. Court Locator API: health, find-jurisdiction, find-jurisdiction-by-address

Запуск из корня проекта:
  python scripts/dadata_and_api_test.py
  python scripts/dadata_and_api_test.py --api-url http://localhost:8000
  python scripts/dadata_and_api_test.py --no-dadata   # только тест API (без DaData)
  python scripts/dadata_and_api_test.py --no-api     # только DaData (без запуска API)
"""
import argparse
import io
import sys

# UTF-8 для Windows-консоли
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Загрузка .env
_env = ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass


def section_dadata():
    """Сценарий DaData: Profile API + suggest court."""
    print("\n" + "=" * 60)
    print("ЧАСТЬ 1: СЦЕНАРИЙ ПОЛУЧЕНИЯ ДАННЫХ ИЗ DADATA")
    print("=" * 60)

    token = (os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or "").strip()
    secret = (os.getenv("DADATA_SECRET") or "").strip()

    if not token:
        print("  [SKIP] DADATA_TOKEN не задан в .env — пропускаем DaData")
        return None

    results = {"profile": {}, "suggest": [], "find_court": []}

    # --- 1.1 Profile API ---
    print("\n1.1 Profile API (баланс, статистика, версии)")
    print("-" * 40)

    try:
        from parser.dadata_api import (
            get_balance,
            get_daily_stats,
            get_versions,
            suggest_court,
            find_court_by_address,
            court_suggestion_to_result,
            DADATA_COURT_TYPE_MS,
        )
    except ImportError:
        sys.path.insert(0, str(ROOT / "parser"))
        from dadata_api import (
            get_balance,
            get_daily_stats,
            get_versions,
            suggest_court,
            find_court_by_address,
            court_suggestion_to_result,
            DADATA_COURT_TYPE_MS,
        )

    balance = get_balance(token, secret)
    if balance is not None:
        b = balance.get("balance")
        print(f"  Баланс: {b} руб.")
        results["profile"]["balance"] = balance
    else:
        print("  Баланс: не удалось (проверьте DADATA_TOKEN и DADATA_SECRET)")
        results["profile"]["balance"] = None

    stats = get_daily_stats(token, secret)
    if stats is not None:
        print(f"  Статистика за сегодня: {len(stats)} записей")
        for k, v in list(stats.items())[:5]:
            print(f"    {k}: {v}")
        results["profile"]["daily_stats"] = stats
    else:
        print("  Статистика: запрос не удался")
        results["profile"]["daily_stats"] = None

    versions = get_versions(token, secret)
    if versions is not None:
        print(f"  Версии справочников: {list(versions.keys())[:3]}...")
        results["profile"]["versions"] = versions
    else:
        print("  Версии: запрос не удался")
        results["profile"]["versions"] = None

    # --- 1.2 suggest_court (подсказки судов) ---
    print("\n1.2 suggest_court — поиск судов по запросу")
    print("-" * 40)

    test_queries = [
        ("мировой суд", "Москва", DADATA_COURT_TYPE_MS),
        ("Нижний Новгород, ул. Рождественская 1", "Нижегородская область", None),
        ("Санкт-Петербург, Невский проспект 1", "Санкт-Петербург", None),
    ]

    for query, region, court_type in test_queries:
        print(f"\n  Запрос: «{query}» | регион: {region} | court_type: {court_type or 'любой'}")
        suggestions = suggest_court(
            query=query,
            region=region,
            count=3,
            token=token,
            court_type=court_type,
        )
        if suggestions:
            for i, s in enumerate(suggestions[:3], 1):
                row = court_suggestion_to_result(s)
                if row:
                    name = row.get("court_name", "")[:60]
                    addr = (row.get("address") or "")[:50]
                    print(f"    {i}. {name} | {addr}")
                    results["suggest"].append({"query": query, "region": region, "result": row})
        else:
            print("    (пусто)")
            results["suggest"].append({"query": query, "region": region, "result": None})

    # --- 1.3 find_court_by_address ---
    print("\n1.3 find_court_by_address — суд по адресу (первый подходящий)")
    print("-" * 40)

    test_addresses = [
        "Москва, ул. Тверская 1",
        "Нижний Новгород, ул. Большая Покровская 1",
        "Санкт-Петербург, Дворцовая площадь 1",
    ]

    for addr in test_addresses:
        print(f"\n  Адрес: «{addr}»")
        row = find_court_by_address(addr, token=token)
        if row:
            print(f"    Суд: {row.get('court_name', '')[:60]}")
            print(f"    Адрес суда: {(row.get('address') or '')[:60]}")
            print(f"    Регион: {row.get('region', '')}")
            results["find_court"].append({"address": addr, "result": row})
        else:
            print("    (не найден)")
            results["find_court"].append({"address": addr, "result": None})

    print("\n" + "-" * 60)
    print("DaData: сценарий завершён.")
    return results


def section_api_test(api_url: str):
    """Тестирование court_locator REST API."""
    print("\n" + "=" * 60)
    print("ЧАСТЬ 2: ТЕСТИРОВАНИЕ COURT_LOCATOR API")
    print("=" * 60)

    base = api_url.rstrip("/")
    results = {}

    try:
        import requests
    except ImportError:
        print("  [SKIP] requests не установлен: pip install requests")
        return None

    # --- 2.1 Health ---
    print("\n2.1 GET /api/health")
    print("-" * 40)
    try:
        r = requests.get(f"{base}/api/health", timeout=5)
        data = r.json() if r.ok else {}
        print(f"  HTTP {r.status_code}: {json.dumps(data, ensure_ascii=False)}")
        results["health"] = {"status_code": r.status_code, "body": data}
    except Exception as e:
        print(f"  Ошибка: {e}")
        results["health"] = {"error": str(e)}
        print("\n  [ВНИМАНИЕ] API недоступен. Запустите: python run_court_locator_api.py")
        return results

    # --- 2.2 find-jurisdiction (координаты) ---
    print("\n2.2 POST /api/find-jurisdiction (координаты)")
    print("-" * 40)

    test_coords = [
        (55.7558, 37.6176, "Москва, Красная площадь"),
        (56.3269, 44.0056, "Нижний Новгород, центр"),
        (59.9343, 30.3351, "Санкт-Петербург, центр"),
    ]

    for lat, lng, desc in test_coords:
        print(f"\n  Координаты: ({lat}, {lng}) — {desc}")
        try:
            r = requests.post(
                f"{base}/api/find-jurisdiction",
                json={"lat": lat, "lng": lng},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                jur = data.get("jurisdiction", {})
                print(f"    HTTP 200 | response_time_ms: {data.get('response_time_ms')}")
                print(f"    Суд: {(jur.get('court_name') or '')[:55]}")
                print(f"    Источник: {jur.get('source', '')}")
                results[f"coords_{lat}_{lng}"] = data
            else:
                print(f"    HTTP {r.status_code}: {r.text[:100]}")
                results[f"coords_{lat}_{lng}"] = {"status_code": r.status_code, "text": r.text[:200]}
        except Exception as e:
            print(f"    Ошибка: {e}")
            results[f"coords_{lat}_{lng}"] = {"error": str(e)}

    # --- 2.3 find-jurisdiction-by-address ---
    print("\n2.3 POST /api/find-jurisdiction-by-address")
    print("-" * 40)

    test_addresses = [
        "Москва, ул. Тверская 1",
        "Нижний Новгород, ул. Большая Покровская 1",
    ]

    for addr in test_addresses:
        print(f"\n  Адрес: «{addr}»")
        try:
            r = requests.post(
                f"{base}/api/find-jurisdiction-by-address",
                json={"address": addr},
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                jur = data.get("jurisdiction", {})
                print(f"    HTTP 200 | response_time_ms: {data.get('response_time_ms')}")
                print(f"    Суд: {(jur.get('court_name') or '')[:55]}")
                print(f"    Источник: {jur.get('source', '')}")
                results[f"address_{addr[:20]}"] = data
            else:
                print(f"    HTTP {r.status_code}: {r.text[:100]}")
                results[f"address_{addr[:20]}"] = {"status_code": r.status_code, "text": r.text[:200]}
        except Exception as e:
            print(f"    Ошибка: {e}")
            results[f"address_{addr[:20]}"] = {"error": str(e)}

    # --- 2.4 boundaries (GeoJSON) ---
    print("\n2.4 GET /api/boundaries")
    print("-" * 40)
    try:
        r = requests.get(f"{base}/api/boundaries", timeout=10)
        if r.status_code == 200:
            data = r.json()
            features = data.get("features", [])
            print(f"  HTTP 200 | features: {len(features)}")
            results["boundaries"] = {"features_count": len(features)}
        else:
            print(f"  HTTP {r.status_code}")
            results["boundaries"] = {"status_code": r.status_code}
    except Exception as e:
        print(f"  Ошибка: {e}")
        results["boundaries"] = {"error": str(e)}

    # --- 2.5 metrics ---
    print("\n2.5 GET /api/metrics")
    print("-" * 40)
    try:
        r = requests.get(f"{base}/api/metrics", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"  HTTP 200 | count: {data.get('count', 0)} | last_ms: {data.get('last_ms')}")
            results["metrics"] = data
        else:
            print(f"  HTTP {r.status_code}")
            results["metrics"] = {"status_code": r.status_code}
    except Exception as e:
        print(f"  Ошибка: {e}")
        results["metrics"] = {"error": str(e)}

    print("\n" + "-" * 60)
    print("API: тестирование завершено.")
    return results


def main():
    parser = argparse.ArgumentParser(description="DaData + court_locator API тест")
    parser.add_argument("--api-url", default="http://localhost:8000", help="URL court_locator API")
    parser.add_argument("--no-dadata", action="store_true", help="Пропустить DaData")
    parser.add_argument("--no-api", action="store_true", help="Пропустить тест API")
    parser.add_argument("--json", action="store_true", help="Вывести итоговый JSON")
    args = parser.parse_args()

    dadata_results = None
    api_results = None

    if not args.no_dadata:
        dadata_results = section_dadata()
    else:
        print("\n[--no-dadata] Пропуск DaData")

    if not args.no_api:
        api_results = section_api_test(args.api_url)
    else:
        print("\n[--no-api] Пропуск теста API")

    # Итог
    print("\n" + "=" * 60)
    print("ИТОГ СЦЕНАРИЯ")
    print("=" * 60)

    if dadata_results:
        print("\nDaData:")
        print(f"  - Profile API: баланс {'OK' if dadata_results.get('profile', {}).get('balance') else 'FAIL'}")
        print(f"  - suggest_court: {len(dadata_results.get('suggest', []))} запросов")
        print(f"  - find_court_by_address: {len(dadata_results.get('find_court', []))} адресов")

    if api_results:
        health = api_results.get("health", {})
        if "status_code" in health and health["status_code"] == 200:
            print("\nCourt Locator API: доступен")
        elif "error" in health:
            print("\nCourt Locator API: недоступен (запустите run_court_locator_api.py)")

    if args.json:
        out = {"dadata": dadata_results, "api": api_results}
        print("\n--- JSON ---")
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))

    print("\nГотово.")


if __name__ == "__main__":
    main()
