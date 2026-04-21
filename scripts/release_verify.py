#!/usr/bin/env python3
"""
Единая проверка «ядро готово к выдаче»: закон СПб в БД, тесты подсудности/правил,
затем тот же набор, что docs/PROD_READINESS_CHECKLIST_RU.md (раздел 1).

  python scripts/release_verify.py
  python scripts/release_verify.py --no-preflight     # только СПб + pytest ядра
  python scripts/release_verify.py --full-pytest      # после preflight: pytest tests/

Примеры CI:

  python scripts/release_verify.py && echo OK

Код выхода: 0 только если все обязательные шаги без Fail.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_spb_gaps import law_rule_section_gaps  # noqa: E402


def _safe_console_text(s: str) -> str:
    """Вывод subprocess на консоли Windows/cp1251 без падения на редких символах."""
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    return s.encode(enc, errors="replace").decode(enc)


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int | None = None) -> tuple[int, str]:
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Полная верификация ядра перед релизом.")
    ap.add_argument(
        "--db",
        default=str(ROOT / "parser" / "court_districts.sqlite"),
        help="SQLite с таблицей law_rules",
    )
    ap.add_argument("--region", default="Санкт-Петербург", help="Регион для проверки участков")
    ap.add_argument("--min-section", type=int, default=1)
    ap.add_argument("--max-section", type=int, default=211)
    ap.add_argument("--no-preflight", action="store_true", help="Не запускать scripts/prod_preflight.py")
    ap.add_argument("--full-pytest", action="store_true", help="После остального: pytest tests/")
    args = ap.parse_args()

    os.chdir(ROOT)

    fails = 0

    print("=== release_verify: закон СПб (law_rules), диапазон участков ===\n")
    db_path = Path(args.db)
    try:
        missing = law_rule_section_gaps(db_path, args.region, args.min_section, args.max_section)
    except FileNotFoundError:
        print(f"[SPb-law] Fail  нет файла БД: {db_path}")
        fails += 1
        missing = []

    if not fails:
        if missing:
            print(f"[SPb-law] Fail  пропущены номера участков {args.min_section}..{args.max_section}: {missing[:50]}")
            if len(missing) > 50:
                print(f"           ... всего {len(missing)}")
            fails += 1
        else:
            print(
                f"[SPb-law] Pass  {args.region}: все участки {args.min_section}..{args.max_section} присутствуют в law_rules"
            )

    core_tests = [
        "tests/test_spb_jurisdiction_addresses.py",
        "tests/test_law_rules.py",
        "tests/test_law_document_parser.py",
        "tests/test_jurisdiction_core.py",
    ]
    print("\n=== release_verify: pytest (правила и подсудность) ===\n")
    rc, out = _run(
        [sys.executable, "-m", "pytest", "-q", *core_tests],
        timeout=300,
    )
    if rc != 0:
        print(_safe_console_text(f"[pytest-core] Fail  exit {rc}\n{out[-2000:]}"))
        fails += 1
    else:
        print(f"[pytest-core] Pass  {' '.join(core_tests)}")

    if not args.no_preflight:
        print("\n=== release_verify: prod_preflight (чеклист §1) ===\n")
        rc, out = _run(
            [
                sys.executable,
                str(SCRIPTS / "prod_preflight.py"),
                "--skip-bootstrap",
                "--skip-diagnose",
            ],
            timeout=600,
        )
        if rc != 0:
            print(_safe_console_text(f"[preflight] Fail  exit {rc}\n{out[-2500:]}"))
            fails += 1
        else:
            print(_safe_console_text(out))
            print("[preflight] Pass")
    else:
        print("\n[preflight] Skip  (--no-preflight)\n")

    if args.full_pytest:
        print("\n=== release_verify: полный pytest tests/ ===\n")
        rc, out = _run([sys.executable, "-m", "pytest", "-q", "tests/"], timeout=900)
        if rc != 0:
            print(_safe_console_text(f"[pytest-full] Fail  exit {rc}\n{out[-2500:]}"))
            fails += 1
        else:
            tail = out.splitlines()[-3:] if out else []
            print("[pytest-full] Pass\n" + _safe_console_text("\n".join(tail)))

    print()
    if fails:
        print(f"Итог release_verify: FAIL ({fails} блок(ов)).")
        return 1
    print("Итог release_verify: OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
