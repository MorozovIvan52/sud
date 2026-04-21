#!/usr/bin/env python3
"""
Сравнение: только Dagalin-индекс vs полный UnifiedJurisdictionCore.find_court
на тех же 50 адресах (Нижний Новгород + Нижегородская обл.).

Примеры:
  python scripts/compare_full_vs_dagalin_50.py --skip-external-geo
  python scripts/compare_full_vs_dagalin_50.py --out data/regression_full_vs_dagalin.csv
  python scripts/compare_full_vs_dagalin_50.py --prefer-no-dadata
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))
sys.stdout.reconfigure(encoding="utf-8")

# Загрузка .env (ключи DaData и т.д.)
_env = ROOT / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(_env)
    except ImportError:
        pass


def _norm_court(name: str) -> str:
    return " ".join((name or "").lower().replace("ё", "е").split())


def main() -> None:
    ap = argparse.ArgumentParser(
        description="50 адресов НН/область: Dagalin-only vs полный find_court"
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "regression_full_vs_dagalin.csv",
        help="CSV с результатами (по умолчанию data/regression_full_vs_dagalin.csv)",
    )
    ap.add_argument(
        "--skip-external-geo",
        action="store_true",
        help="Установить SKIP_EXTERNAL_GEO=1 (не вызывать геокод в шаге C)",
    )
    ap.add_argument(
        "--prefer-no-dadata",
        action="store_true",
        help="FindCourtRequest(prefer_dadata_court=False) — меньше расхождений с приоритетом Dagalin",
    )
    args = ap.parse_args()

    if args.skip_external_geo:
        os.environ["SKIP_EXTERNAL_GEO"] = "1"

    from court_locator.dagalin_address_search import find_court_by_dagalin_address_index
    from court_locator.database import Database
    from nizhny_regression_addresses import build_fifty_sample_addresses
    from unified_jurisdiction.core import UnifiedJurisdictionCore
    from unified_jurisdiction.models import FindCourtRequest
    from unified_jurisdiction.normalizer import normalize_to_unified

    picks, nn_len, _obl_len = build_fifty_sample_addresses(ROOT)
    db = Database()
    core = UnifiedJurisdictionCore(use_cache=False)

    rows: list[dict[str, object]] = []
    for i, r in enumerate(picks, 1):
        addr = r["address"]
        unified = normalize_to_unified(addr)
        cd = find_court_by_dagalin_address_index(db, unified) or {}
        dagalin_name = (cd.get("court_name") or "").strip()
        dagalin_ok = bool(dagalin_name)

        req = FindCourtRequest(
            address=addr,
            strict_verify=False,
            prefer_dadata_court=not args.prefer_no_dadata,
        )
        res = core.find_court(req)
        fc = res.court or {}
        full_name = (fc.get("court_name") or "").strip()
        full_ok = bool(res.success and full_name)

        name_match = False
        if dagalin_ok and full_ok:
            name_match = _norm_court(dagalin_name) == _norm_court(full_name)

        rows.append(
            {
                "idx": i,
                "group": "NN" if i <= nn_len else "NIZ_OBL",
                "input_address": addr,
                "expected_hint": r.get("name") or "",
                "dagalin_court": dagalin_name,
                "dagalin_ok": dagalin_ok,
                "full_court": full_name,
                "full_success": full_ok,
                "full_source": fc.get("source") or "",
                "resolution_steps": "|".join(res.resolution_steps or []),
                "name_match": name_match,
                "needs_manual_review": bool(res.needs_manual_review),
                "error": res.error or "",
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    total = len(rows)
    ok_full = sum(1 for x in rows if x["full_success"])
    ok_match = sum(1 for x in rows if x["name_match"])
    print(f"picked={total} nn={nn_len} obl={total - nn_len}")
    print(f"full_success={ok_full}/{total} ({round(100 * ok_full / total, 1)}%)")
    print(f"name_match(dagalin vs full)={ok_match}/{total} ({round(100 * ok_match / total, 1)}%)")
    print(f"out={args.out}")
    if args.skip_external_geo:
        print("SKIP_EXTERNAL_GEO=1 (шаг C без геокода)")


if __name__ == "__main__":
    main()
