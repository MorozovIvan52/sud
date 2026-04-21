#!/usr/bin/env python3
"""
Этап 1 плана улучшения системы определения подсудности:
  1) Запуск сбора данных по Нижегородской области (DaData → courts.sqlite → courts_geo.sqlite)
  2) Проверка корректности загруженных данных

Запуск из корня проекта:
  python scripts/stage1_run_and_verify.py              # запустить сбор + проверка
  python scripts/stage1_run_and_verify.py --verify-only # только проверка (после ручного запуска сбора)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def run_collect(regions: str = "Нижегородская область", no_geocode: bool = False) -> bool:
    """Запуск parser/run_courts_collect_geocode_load.py."""
    script = ROOT / "parser" / "run_courts_collect_geocode_load.py"
    if not script.exists():
        print(f"Скрипт не найден: {script}")
        return False
    cmd = [sys.executable, str(script), "--regions", regions]
    if no_geocode:
        cmd.append("--no-geocode")
    print("Запуск:", " ".join(cmd))
    try:
        subprocess.run(cmd, cwd=str(ROOT), check=True)
        return True
    except subprocess.CalledProcessError as e:
        print("Ошибка сбора:", e)
        return False


def verify_counts():
    """Проверка количества загруженных судов (courts.sqlite и courts_geo.sqlite)."""
    sys.path.insert(0, str(ROOT / "parser"))
    from courts_db import get_courts_count, get_courts_geo_count, DB_PATH

    courts_count = get_courts_count()
    geo_count = get_courts_geo_count()

    print("\n--- Проверка загруженных данных ---")
    print(f"  courts.sqlite:     {courts_count} записей")
    print(f"  courts_geo.sqlite: {geo_count} записей с координатами")
    print(f"  Путь к БД:         {DB_PATH}")

    if courts_count == 0:
        print("\n  Внимание: таблица courts пуста. Запустите сбор с DADATA_TOKEN в .env:")
        print('    python parser/run_courts_collect_geocode_load.py --regions "Нижегородская область"')
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Этап 1: сбор данных по Нижегородской области и проверка")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Только проверить количество судов (не запускать сбор)",
    )
    parser.add_argument(
        "--regions",
        default="Нижегородская область",
        help="Регионы для сбора (по умолчанию: Нижегородская область)",
    )
    parser.add_argument(
        "--no-geocode",
        action="store_true",
        help="Не выполнять геокодирование (только DaData → courts.sqlite)",
    )
    args = parser.parse_args()

    if not args.verify_only:
        ok = run_collect(regions=args.regions, no_geocode=args.no_geocode)
        if not ok:
            sys.exit(1)

    verify_counts()
    print("\nГотово.")


if __name__ == "__main__":
    main()
