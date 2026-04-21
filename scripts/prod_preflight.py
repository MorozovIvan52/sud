#!/usr/bin/env python3
"""
Автоматический preflight по разделу 1 чеклиста docs/PROD_READINESS_CHECKLIST_RU.md.

  python scripts/prod_preflight.py
  python scripts/prod_preflight.py --install-deps
  python scripts/prod_preflight.py --full-tests
  python scripts/prod_preflight.py --strict-keys --require-polygons

Код выхода: 0 если нет Fail; 1 если хотя бы один Fail. Предупреждения (WARN) не валят код.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Literal, Tuple

ROOT = Path(__file__).resolve().parent.parent

Outcome = Literal["Pass", "Fail", "Warn"]


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int | None = None) -> Tuple[int, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out.strip()


def _print_line(code: str, outcome: Outcome, detail: str) -> None:
    print(f"[{code}] {outcome:4}  {detail}")


def check_1_1_pip(*, install_deps: bool) -> Outcome:
    pip_ok = True
    if install_deps:
        rc, out = _run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")],
            timeout=600,
        )
        if rc != 0:
            _print_line("1.1", "Fail", f"pip install: exit {rc}\n{out[:800]}")
            return "Fail"
        _print_line("1.1", "Pass", "pip install -r requirements.txt OK")
    else:
        rc, out = _run([sys.executable, "-m", "pip", "check"], timeout=120)
        if rc != 0:
            _print_line("1.1", "Warn", f"pip check exit {rc} (см. --install-deps)\n{out[:400]}")
            pip_ok = False
        else:
            _print_line("1.1", "Pass", "pip check OK (для принудительной установки: --install-deps)")
    try:
        import fastapi  # noqa: F401
        import pytest  # noqa: F401
        import requests  # noqa: F401
    except ImportError as e:
        _print_line("1.1b", "Fail", f"импорт зависимостей: {e}")
        return "Fail"
    _print_line("1.1b", "Pass", "ключевые пакеты импортируются")
    return "Pass" if pip_ok else "Warn"


def check_1_2_bootstrap() -> Outcome:
    rc, out = _run([sys.executable, str(ROOT / "scripts" / "bootstrap_local_databases.py")], timeout=120)
    if rc != 0:
        _print_line("1.2", "Fail", f"bootstrap exit {rc}\n{out[:600]}")
        return "Fail"
    _print_line("1.2", "Pass", "bootstrap_local_databases.py OK")
    return "Pass"


def check_1_3_courts(min_courts: int) -> Outcome:
    _load_env()
    sys.path.insert(0, str(ROOT))
    from court_locator import config

    path = Path(config.COURTS_DB_PATH)
    if not path.is_file():
        _print_line("1.3", "Fail", f"нет файла courts: {path}")
        return "Fail"
    try:
        conn = sqlite3.connect(str(path))
        n = conn.execute("SELECT COUNT(*) FROM courts").fetchone()[0]
        conn.close()
    except Exception as e:
        _print_line("1.3", "Fail", f"SQLite courts: {e}")
        return "Fail"
    if n < min_courts:
        _print_line("1.3", "Fail", f"строк в courts: {n} (нужно >= {min_courts})")
        return "Fail"
    _print_line("1.3", "Pass", f"courts.sqlite: {n} строк ({path})")
    return "Pass"


def check_1_4_polygons(*, require: bool) -> Outcome:
    sys.path.insert(0, str(ROOT))
    from court_locator import config

    path = Path(config.COURT_DISTRICTS_DB_PATH)
    if not path.is_file():
        msg = f"нет court_districts.sqlite: {path}"
        if require:
            _print_line("1.4", "Fail", msg)
            return "Fail"
        _print_line("1.4", "Warn", msg + " (точечный spatial может быть недоступен)")
        return "Warn"
    try:
        conn = sqlite3.connect(str(path))
        n = conn.execute("SELECT COUNT(*) FROM court_districts").fetchone()[0]
        conn.close()
    except Exception as e:
        _print_line("1.4", "Fail", str(e))
        return "Fail"
    if n == 0:
        if require:
            _print_line("1.4", "Fail", "court_districts пуста")
            return "Fail"
        _print_line("1.4", "Warn", "court_districts: 0 строк (импорт полигонов по docs)")
        return "Warn"
    _print_line("1.4", "Pass", f"полигоны: {n} строк ({path})")
    return "Pass"


def check_1_5_keys(*, strict: bool) -> Outcome:
    _load_env()
    y = (os.getenv("YANDEX_GEO_KEY") or os.getenv("YANDEX_GEOCODER_API_KEY") or "").strip()
    d = (os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or "").strip()
    if y or d:
        parts = []
        if y:
            parts.append("Yandex")
        if d:
            parts.append("DaData")
        _print_line("1.5", "Pass", "ключи: " + "+".join(parts))
        return "Pass"
    if strict:
        _print_line("1.5", "Fail", "нет YANDEX_GEO_KEY / DADATA_TOKEN (--strict-keys)")
        return "Fail"
    _print_line("1.5", "Warn", "нет ключей геокодера — режим бесплатных источников/OSM (см. README)")
    return "Warn"


def check_1_6_diagnose() -> Outcome:
    rc, out = _run([sys.executable, str(ROOT / "scripts" / "diagnose_jurisdiction.py")], timeout=180)
    if rc != 0:
        _print_line("1.6", "Fail", f"diagnose_jurisdiction exit {rc}\n{out[-1200:]}")
        return "Fail"
    _print_line("1.6", "Pass", "diagnose_jurisdiction.py OK")
    return "Pass"


def check_pytest(paths: list[str], code: str, timeout: int) -> Outcome:
    cmd = [sys.executable, "-m", "pytest", "-q", *paths]
    rc, out = _run(cmd, timeout=timeout)
    tail = out[-1500:] if len(out) > 1500 else out
    if rc != 0:
        _print_line(code, "Fail", f"pytest exit {rc}\n{tail}")
        return "Fail"
    _print_line(code, "Pass", " ".join(paths))
    return "Pass"


def main() -> int:
    ap = argparse.ArgumentParser(description="Preflight раздела 1 (готовность ядра к прод).")
    ap.add_argument("--install-deps", action="store_true", help="1.1: выполнить pip install -r requirements.txt")
    ap.add_argument("--min-courts", type=int, default=1, help="1.3: минимум строк в courts")
    ap.add_argument("--require-polygons", action="store_true", help="1.4: Fail если нет полигонов")
    ap.add_argument("--strict-keys", action="store_true", help="1.5: Fail если нет Yandex/DaData")
    ap.add_argument("--full-tests", action="store_true", help="1.11: pytest tests/")
    ap.add_argument("--skip-bootstrap", action="store_true", help="не запускать bootstrap (1.2)")
    ap.add_argument("--skip-diagnose", action="store_true", help="не запускать diagnose (1.6)")
    args = ap.parse_args()

    os.chdir(ROOT)
    _load_env()

    print("=== prod_preflight (раздел 1, docs/PROD_READINESS_CHECKLIST_RU.md) ===\n")

    fails = 0

    def run(o: Outcome) -> None:
        nonlocal fails
        if o == "Fail":
            fails += 1

    run(check_1_1_pip(install_deps=args.install_deps))
    if not args.skip_bootstrap:
        run(check_1_2_bootstrap())
    else:
        _print_line("1.2", "Warn", "пропущено (--skip-bootstrap)")

    run(check_1_3_courts(args.min_courts))
    run(check_1_4_polygons(require=args.require_polygons))
    run(check_1_5_keys(strict=args.strict_keys))

    if not args.skip_diagnose:
        run(check_1_6_diagnose())
    else:
        _print_line("1.6", "Warn", "пропущено (--skip-diagnose)")

    run(check_pytest(["tests/test_jurisdiction_readiness_rf.py"], "1.7", timeout=300))
    run(check_pytest(["tests/test_court_locator_api_integration.py"], "1.8", timeout=180))
    run(check_pytest(["tests/test_geocode_yandex_dadata_fallback.py"], "1.9", timeout=120))
    run(
        check_pytest(
            [
                "tests/test_html_jurisdiction_extraction.py",
                "tests/test_jurisdiction_scrape_aggregate.py",
                "tests/test_court_sites_scraper.py",
            ],
            "1.10",
            timeout=180,
        )
    )

    if args.full_tests:
        run(check_pytest(["tests/"], "1.11", timeout=900))
    else:
        _print_line("1.11", "Warn", "пропущено (добавьте --full-tests для pytest tests/)")

    print()
    if fails:
        print(f"Итог: FAIL ({fails} проверок). Код выхода 1.")
        return 1
    print("Итог: OK (нет Fail; предупреждения WARN допустимы). Код выхода 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
