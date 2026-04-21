import re
import sqlite3
from collections import Counter

import pandas as pd


def main() -> None:
    con = sqlite3.connect(r"parser/court_districts.sqlite")
    q = """
    SELECT region, district_number, court_name
    FROM court_districts
    WHERE region IS NULL OR TRIM(region) = ''
    LIMIT 50
    """
    df = pd.read_sql_query(q, con)
    con.close()

    print("rows(sample):", len(df))
    if df.empty:
        return

    missing = 0
    extracted = []
    for s in df["district_number"].fillna(""):
        m = re.findall(r"\d+", str(s))
        if m:
            extracted.append(m[0])
        else:
            missing += 1

    print("missing digits in sample:", missing)
    c = Counter(extracted)
    print("top extracted nums:", c.most_common(15))

    print("\nSample rows (region/district_number only):")
    show = df.copy()
    show["district_digits_extracted"] = [
        (re.findall(r"\d+", str(x)) or [None])[0] for x in show["district_number"].fillna("")
    ]
    print(show[["region", "district_number", "district_digits_extracted"]].to_string(index=False))


if __name__ == "__main__":
    main()

