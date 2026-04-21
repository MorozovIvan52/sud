import re
import sqlite3
from collections import Counter

import pandas as pd


def analyze(region_value: str) -> None:
    con = sqlite3.connect(r"parser/court_districts.sqlite")
    q = """
    SELECT district_number
    FROM court_districts
    WHERE region = ?
    """
    df = pd.read_sql_query(q, con, params=[region_value])
    con.close()

    extracted = []
    missing = 0
    for s in df["district_number"].fillna(""):
        m = re.findall(r"\d+", str(s))
        if m:
            extracted.append(m[0])
        else:
            missing += 1

    c = Counter(extracted)
    # Безопасный вывод: в консоли может быть CP1251/не все символы печатаются.
    safe_region = region_value.encode("unicode_escape").decode("ascii")
    print(
        "region:",
        safe_region,
        "rows:",
        len(df),
        "missing digits:",
        missing,
        "unique:",
        len(c),
    )
    print("top:", c.most_common(15))


def main() -> None:
    con = sqlite3.connect(r"parser/court_districts.sqlite")
    regions = [r for (r,) in con.execute("SELECT DISTINCT region FROM court_districts").fetchall()]
    con.close()

    for region_value in regions:
        analyze(region_value)


if __name__ == "__main__":
    main()

