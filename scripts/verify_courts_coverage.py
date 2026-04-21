"""
Проверка покрытия БД courts по всем 85 субъектам РФ.
Запуск: python scripts/verify_courts_coverage.py
"""
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from parser.regions_rf import ALL_REGIONS_RF
except ImportError:
    ALL_REGIONS_RF = {}

COURTS_DB = PROJECT_ROOT / "parser" / "courts.sqlite"


def main():
    if not COURTS_DB.exists():
        print(f"БД не найдена: {COURTS_DB}")
        print("Заполните импортом: python -c \"from parser.import_courts import import_courts_from_csv; from pathlib import Path; import_courts_from_csv(Path('parser/data/magistrates_dadata.csv'))\"")
        return 1

    conn = sqlite3.connect(str(COURTS_DB))
    cur = conn.execute(
        "SELECT region, COUNT(*) FROM courts WHERE region IS NOT NULL AND TRIM(region) != '' GROUP BY region"
    )
    rows = cur.fetchall()
    conn.close()

    regions_in_db = {r.strip() for r, _ in rows if r}
    total_courts = sum(c for _, c in rows)

    print(f"Регионов в БД: {len(regions_in_db)}")
    print(f"Всего судов: {total_courts}")

    if ALL_REGIONS_RF:
        all_regions = set(ALL_REGIONS_RF.keys())
        missing = sorted(all_regions - regions_in_db)
        extra = sorted(regions_in_db - all_regions)

        if missing:
            print(f"\nОтсутствуют регионы ({len(missing)} из 85):")
            for r in missing:
                code = ALL_REGIONS_RF.get(r, "?")
                print(f"  - {r} ({code})")
        else:
            print("\nВсе 85 субъектов РФ представлены в БД.")

        if extra:
            print(f"\nДополнительные регионы в БД (не в ALL_REGIONS_RF): {len(extra)}")
            for r in extra[:20]:
                print(f"  + {r}")
            if len(extra) > 20:
                print(f"  ... и ещё {len(extra) - 20}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
