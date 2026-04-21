import os
import re
import sqlite3
from collections import Counter
from typing import Optional

import pandas as pd


def extract_first_int(s: object) -> Optional[int]:
    if s is None:
        return None
    m = re.findall(r"\d+", str(s))
    if not m:
        return None
    try:
        return int(m[0])
    except Exception:
        return None


def main() -> None:
    db_path = r"parser/court_districts.sqlite"
    out_dir = r"batch_outputs"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "nizhny_magistrates_1_8_grouped.xlsx")

    con = sqlite3.connect(db_path)
    q = """
    SELECT district_number, court_name, boundaries, region
    FROM court_districts
    """
    df = pd.read_sql_query(q, con)
    con.close()

    df["unit_num"] = df["district_number"].apply(extract_first_int)
    df = df.dropna(subset=["unit_num"])
    df["unit_num"] = df["unit_num"].astype(int)

    # Choose display name: most common court_name for a given unit.
    grouped_rows = []
    for unit_num, g in df.groupby("unit_num"):
        names = [str(x) for x in g["court_name"].fillna("").tolist() if str(x).strip()]
        if names:
            name = Counter(names).most_common(1)[0][0]
        else:
            name = ""

        # Keep all geometry descriptions for this unit (as JSON/poly list in TEXT).
        boundaries_list = [str(x) for x in g["boundaries"].fillna("").tolist()]
        boundaries_cell = "\n---\n".join(boundaries_list)

        grouped_rows.append(
            {
                "номер_и_наименование": f"{unit_num} — {name}",
                "описание_границ": boundaries_cell,
            }
        )

    out_df = pd.DataFrame(grouped_rows).sort_values(
        "номер_и_наименование", key=lambda s: s.str.extract(r"(\\d+)").astype(float)[0]
    )
    out_df.to_excel(out_path, index=False)
    print("Saved:", out_path)
    print("Units exported:", len(out_df))


if __name__ == "__main__":
    main()

