"""
Импорт контактных данных мировых судей (телефон, email, адрес, судья) в `parser/court_districts.sqlite`.

Ожидаемый вход: папка с файлами (обычно .txt), где встречаются:
  - email вида `msud{N}.<subdomain>@sudrf.ru` (например msud1.nnov@sudrf.ru)
  - телефон (пример: 8(831)299-47-10)
  - адрес (пример: 603950, г. Нижний Новгород, ул. Ватутина, д. 10 А)
  - имя мирового судьи в строке `мировой судья <ФИО>`

Сопоставление по судебному участку: N из `msudN`.
Обновляем все строки `court_districts`, у которых в `district_number` встречается цифра N.

Запуск из корня проекта:
  python -m parser.import_court_contacts_to_court_districts --input-dir ./data/contacts/nnov --region "Нижегородская область"
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from pathlib import Path
from typing import Optional


MSUD_EMAIL_RE = re.compile(r"\bmsud\s*(\d+)\.[^\s@]+@sudrf\.ru\b", re.IGNORECASE)
ANY_SUDRF_EMAIL_RE = re.compile(r"\b[\w\.-]+@sudrf\.ru\b", re.IGNORECASE)
PHONE_RE = re.compile(r"8\s*\(\s*\d{3}\s*\)\s*\d{3}-\d{2}-\d{2}")
ADDRESS_RE = re.compile(r"\b\d{5,6},\s*г\.\s*[^\n,]+,\s*[^;\n]+", re.IGNORECASE)
JUDGE_RE = re.compile(r"мировой\s+судья\s+([А-ЯЁ][^\n]+)", re.IGNORECASE)


def _read_text(path: Path) -> str:
    # Обычно такие страницы в Windows-1251; пробуем utf-8, потом cp1251.
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=enc, errors="strict")
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_section_num_and_email(text: str) -> tuple[Optional[str], Optional[str]]:
    m = MSUD_EMAIL_RE.search(text)
    if m:
        return m.group(1), m.group(0)
    # fallback: искать msudN без доменной части (редко)
    ms = re.search(r"\bmsud\s*(\d+)\b", text, re.IGNORECASE)
    if ms:
        email = None
        all_emails = ANY_SUDRF_EMAIL_RE.findall(text)
        if all_emails:
            # Берём первую sudrf-почту, если конкретная msudN не нашлась
            email = all_emails[0]
        return ms.group(1), email
    return None, None


def _extract_phone(text: str) -> str:
    m = PHONE_RE.search(text)
    return m.group(0).strip() if m else ""


def _extract_address(text: str) -> str:
    m = ADDRESS_RE.search(text)
    return m.group(0).strip() if m else ""


def _extract_judge_name(text: str) -> str:
    m = JUDGE_RE.search(text)
    return m.group(1).strip() if m else ""


def _digit_prefix(s: Optional[str]) -> str:
    if not s:
        return ""
    m = re.search(r"\d+", str(s))
    return m.group(0) if m else ""


def import_contacts(input_dir: Path, region_name: str) -> None:
    project_root = Path(__file__).resolve().parent.parent
    db_path = project_root / "parser" / "court_districts.sqlite"

    if not db_path.exists():
        raise FileNotFoundError(f"Не найден БД: {db_path}")

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Ensure email column exists (на случай, если таблицу создали старым кодом)
    cur.execute("PRAGMA table_info(court_districts)")
    cols = {row[1] for row in cur.fetchall()}
    if "email" not in cols:
        cur.execute("ALTER TABLE court_districts ADD COLUMN email TEXT")
        conn.commit()

    # Снимок всех court_districts, чтобы быстро обновлять по id
    all_rows = cur.execute("SELECT id, district_number, region FROM court_districts").fetchall()

    txt_files = [p for p in sorted(input_dir.glob("*.txt")) if p.is_file()]
    if not txt_files:
        raise FileNotFoundError(f"В папке нет *.txt: {input_dir}")

    updated = 0
    skipped = 0

    for p in txt_files:
        text = _read_text(p)
        section_num, email = _extract_section_num_and_email(text)
        if not section_num:
            skipped += 1
            continue

        phone = _extract_phone(text)
        address = _extract_address(text)
        judge_name = _extract_judge_name(text)

        # Обновляем все строки, где district_number содержит эту цифру
        target_ids = [rid for (rid, dnum, _reg) in all_rows if _digit_prefix(dnum) == section_num]
        if not target_ids:
            skipped += 1
            continue

        court_name = f"Мировой судья судебного участка № {section_num}"

        cur.executemany(
            """
            UPDATE court_districts
            SET
              district_number = ?,
              region = ?,
              court_name = ?,
              address = ?,
              phone = ?,
              email = ?,
              judge_name = ?,
              schedule = COALESCE(schedule, '')
            WHERE id = ?
            """,
            [
                (
                    str(section_num),
                    region_name,
                    court_name,
                    address,
                    phone,
                    email or "",
                    judge_name,
                    rid,
                )
                for rid in target_ids
            ],
        )

        updated += len(target_ids)

    conn.commit()
    conn.close()

    print(f"Import завершён. Обновлено записей: {updated}. Пропущено файлов: {skipped}.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True, help="Папка с файлами контактов (.txt)")
    ap.add_argument("--region", required=True, help="Например: 'Нижегородская область'")
    args = ap.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    import_contacts(input_dir=input_dir, region_name=args.region)


if __name__ == "__main__":
    main()

