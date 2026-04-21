#!/usr/bin/env python3
"""Быстрый тест только по индексу Dagalin (50 адресов). Результат: data/test_50_nizhny_jurisdiction_results.csv"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))
sys.stdout.reconfigure(encoding="utf-8")

from court_locator.dagalin_address_search import find_court_by_dagalin_address_index
from court_locator.database import Database
from nizhny_regression_addresses import build_fifty_sample_addresses
from unified_jurisdiction.normalizer import normalize_to_unified


def main():
    picks, nn_len, obl_len = build_fifty_sample_addresses(ROOT)
    db = Database()
    rows = []
    ok = 0

    for i, r in enumerate(picks, 1):
        addr = r.get("address") or ""
        unified = normalize_to_unified(addr)
        c = find_court_by_dagalin_address_index(db, unified) or {}
        success = bool((c.get("court_name") or "").strip())
        if success:
            ok += 1
        rows.append(
            {
                "idx": i,
                "group": "NN" if i <= nn_len else "NIZ_OBL",
                "input_address": addr,
                "expected_hint": r.get("name") or "",
                "success": success,
                "found_court": c.get("court_name") or "",
                "source": c.get("source") or "",
                "steps": "D:dagalin_address_index" if success else "",
                "manual_review": bool(c.get("needs_manual_review")),
                "error": "" if success else "Суд не найден (dagalin index)",
            }
        )

    out_path = ROOT / "data" / "test_50_nizhny_jurisdiction_results.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    total = len(picks)
    print(f"picked={total} nn={nn_len} obl={obl_len}")
    print(f"success={ok}/{total} ({round(ok * 100 / total, 1)}%)")
    print(f"out={out_path}")


if __name__ == "__main__":
    main()
