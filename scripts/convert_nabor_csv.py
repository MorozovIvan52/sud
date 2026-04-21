"""
Конвертация Nabor-dannykh-13.04.2023.csv (cp1251, ; разделитель) в utf-8 с нормальными заголовками.
Выход: batch_outputs/nabor_normalized.csv и .json

Колонки на выходе:
  section_num, court_name, judge_name, phone, email, site_url, address, work_schedule
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

INPUT_PATH = Path(r"C:\Users\1\Downloads\Nabor-dannykh-13.04.2023.csv")
OUT_DIR = Path("batch_outputs")

def normalize_row_list(row: list[str]) -> dict[str, str]:
    # Ожидаемые позиции:
    # 0: № п/п
    # 1: Административный участок мирового судьи (наименование)
    # 2: Адрес суда
    # 3: ФИО судьи
    # 4: Код телефона (831)
    # 5: Телефон
    # 6: Email
    # 7: Сайт
    # 8: График
    def g(idx: int) -> str:
        if idx >= len(row):
            return ""
        v = (row[idx] or "").strip()
        if v.startswith("'") and v.endswith("'"):
            v = v[1:-1]
        return v.strip()

    phone_full = ""
    code = g(4)
    num = g(5)
    if code or num:
        phone_full = f"+7 {code} {num}".strip()

    return {
        "section_num": g(0),
        "court_name": g(1),
        "judge_name": g(3),
        "phone": phone_full,
        "email": g(6),
        "site_url": g(7),
        "address": g(2),
        "work_schedule": g(8),
    }


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True, parents=True)
    out_csv = OUT_DIR / "nabor_normalized.csv"
    out_json = OUT_DIR / "nabor_normalized.json"

    rows = []
    with INPUT_PATH.open("r", encoding="cp1251") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader, None)
        for r in reader:
            if not any(r):
                continue
            rows.append(normalize_row_list(r))

    # write utf-8 csv
    if rows:
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    # write json
    out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Written {len(rows)} rows to {out_csv} and {out_json}")


if __name__ == "__main__":
    main()

