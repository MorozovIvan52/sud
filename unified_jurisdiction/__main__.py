"""
Диагностика: ключи геокодера, пробный запрос по адресу, resolution_steps.

  python -m unified_jurisdiction
  python -m unified_jurisdiction "г. Москва, ул. Тверская, д. 7"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    p = argparse.ArgumentParser(description="Проверка unified_jurisdiction: ключи и resolution_steps")
    p.add_argument("address", nargs="?", default="г. Москва, ул. Тверская, д. 1")
    p.add_argument("--strict", action="store_true", help="strict_verify (геокод + полигон)")
    p.add_argument("--no-dadata-first", action="store_true", help="старый порядок A→B→C")
    args = p.parse_args()

    try:
        from court_locator import config as cl_config
    except Exception as e:
        print("court_locator:", e)
        return 1

    print(
        "Yandex Geocoder HTTP:",
        f"{cl_config.YANDEX_GEO_KEY_SOURCE}<-{cl_config.YANDEX_GEO_KEY_ENV or '-'}",
        "(ключ задан)" if (cl_config.YANDEX_GEO_KEY or "").strip() else "(ключ не задан)",
    )
    for line, val in cl_config.api_env_diagnostics().items():
        if val and line.endswith("_hint"):
            print(f"  [{line}] {val}")
    print(
        "DaData token:",
        f"{cl_config.DADATA_TOKEN_SOURCE}<-{cl_config.DADATA_TOKEN_ENV or '-'}",
        "+ secret" if (cl_config.DADATA_SECRET or "").strip() else "без secret",
    )
    print("UNIFIED_PREFER_DADATA_COURT env:", repr(__import__("os").getenv("UNIFIED_PREFER_DADATA_COURT")))
    print()

    from unified_jurisdiction import UnifiedJurisdictionClient, FindCourtRequest

    client = UnifiedJurisdictionClient(use_cache=False)
    try:
        req = FindCourtRequest(
            address=args.address,
            strict_verify=args.strict,
            prefer_dadata_court=not args.no_dadata_first,
        )
        res = client.find_court(req)
        out = {
            "success": res.success,
            "resolution_steps": res.resolution_steps,
            "error": res.error,
            "court_name": (res.court or {}).get("court_name"),
            "source": (res.court or {}).get("source"),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if res.success else 2
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
