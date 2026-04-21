"""
Скрипт «всё полезное из DaData»: баланс, статистика за день, версии справочников.
Опционально — выгрузка списка мировых судов в CSV для импорта в БД.

Запуск из каталога parser (с подгруженным .env):
  python dadata_fetch_all.py
  python dadata_fetch_all.py --dump-courts   # + выгрузка судов в data/magistrates_dadata.csv
"""
import argparse
import os
import sys
from pathlib import Path

# Подгрузка .env из корня проекта
SCRIPT_DIR = Path(__file__).resolve().parent
_root = SCRIPT_DIR.parent
_env = _root / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        pass

from dadata_api import get_balance, get_daily_stats, get_versions, _get_token, _get_secret


def main():
    parser = argparse.ArgumentParser(description="DaData: баланс, статистика, версии; опционально выгрузка судов")
    parser.add_argument("--dump-courts", action="store_true", help="Выгрузить мировые суды в CSV (dump_magistrates_to_csv)")
    parser.add_argument("--json", action="store_true", help="Вывести сырой JSON ответов")
    args = parser.parse_args()

    token = _get_token()
    secret = _get_secret()
    if not token:
        print("Задайте DADATA_TOKEN в .env или окружении.", file=sys.stderr)
        sys.exit(1)

    print("=== DaData Profile ===\n")

    # Баланс
    balance = get_balance(token, secret)
    if balance is not None:
        b = balance.get("balance")
        if b is not None:
            print(f"Баланс: {b} руб.")
        elif args.json:
            print("Balance:", balance)
    else:
        print("Баланс: не удалось (проверьте DADATA_TOKEN и DADATA_SECRET)")

    # Статистика за сегодня
    stats = get_daily_stats(token, secret)
    if stats is not None and stats:
        print("\nСтатистика за сегодня:")
        for k, v in sorted(stats.items()):
            if isinstance(v, dict):
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {v}")
        if args.json:
            print("Daily stats (raw):", stats)
    elif stats is not None:
        print("\nСтатистика за сегодня: пусто или нет данных")
    else:
        print("\nСтатистика за сегодня: запрос не удался")

    # Версии
    versions = get_versions(token, secret)
    if versions is not None and versions:
        print("\nВерсии / актуальность справочников:")
        for k, v in sorted(versions.items()):
            print(f"  {k}: {v}")
        if args.json:
            print("Versions (raw):", versions)
    elif versions is not None:
        print("\nВерсии: пусто")
    else:
        print("\nВерсии: запрос не удался")

    # Опционально — выгрузка судов
    if args.dump_courts:
        print("\n=== Выгрузка мировых судов (DaData suggest/court, court_type=MS) ===")
        try:
            from dump_magistrates_to_csv import dump_magistrates_to_csv
            out = dump_magistrates_to_csv()
            print(f"Сохранено в {out}. Импорт в БД: скопируйте в data/magistrates.csv и запустите import_courts.py")
        except Exception as e:
            print(f"Ошибка выгрузки судов: {e}", file=sys.stderr)
            sys.exit(1)

    print("\nГотово.")


if __name__ == "__main__":
    main()
