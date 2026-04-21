#!/usr/bin/env python3
"""
Диагностика: какие номера участков из диапазона 1..211 отсутствуют в law_rules для региона.

  python scripts/check_spb_gaps.py
  python scripts/check_spb_gaps.py --db parser/court_districts.sqlite --region "Санкт-Петербург" --max 211
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def law_rule_section_gaps(
    db_path: Path,
    region: str,
    min_sec: int,
    max_sec: int,
) -> list[int]:
    """
    Номера участков из диапазона min_sec..max_sec, которых нет в law_rules для региона.
    Пустой список — полное покрытие диапазона.
    """
    if not db_path.is_file():
        raise FileNotFoundError(str(db_path))
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT DISTINCT section_num FROM law_rules WHERE region = ?",
            (region,),
        ).fetchall()
    finally:
        conn.close()

    found: set[int] = set()
    for (sn,) in rows:
        if sn is None:
            continue
        s = str(sn).strip()
        if s.isdigit():
            found.add(int(s))

    expected = set(range(min_sec, max_sec + 1))
    return sorted(expected - found)


def main() -> None:
    ap = argparse.ArgumentParser(description="Пропуски section_num в law_rules")
    ap.add_argument("--db", default=str(ROOT / "parser" / "court_districts.sqlite"))
    ap.add_argument("--region", default="Санкт-Петербург")
    ap.add_argument("--min", type=int, default=1, dest="min_sec")
    ap.add_argument("--max", type=int, default=211, dest="max_sec")
    args = ap.parse_args()

    db_path = Path(args.db)
    try:
        missing = law_rule_section_gaps(db_path, args.region, args.min_sec, args.max_sec)
    except FileNotFoundError:
        print(f"БД не найдена: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT DISTINCT section_num FROM law_rules WHERE region = ?",
        (args.region,),
    ).fetchall()
    conn.close()
    found_n = len(
        {
            int(str(sn).strip())
            for (sn,) in rows
            if sn is not None and str(sn).strip().isdigit()
        }
    )

    print(f"Регион: {args.region}")
    print(f"Диапазон проверки: {args.min_sec}..{args.max_sec}")
    print(f"Уникальных номеров в БД (цифры): {found_n}")
    print(f"Ожидалось номеров в диапазоне: {args.max_sec - args.min_sec + 1}")
    print(f"Пропущено в диапазоне: {len(missing)}")
    if missing:
        # компактный вывод длинных списков
        if len(missing) <= 60:
            print(f"Пропущенные номера: {missing}")
        else:
            print(f"Первые 40 пропущенных: {missing[:40]}")
            print(f"... всего {len(missing)} шт.")


if __name__ == "__main__":
    main()
