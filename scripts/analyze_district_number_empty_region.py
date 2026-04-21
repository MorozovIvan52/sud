import re
import sqlite3
from collections import Counter

import pandas as pd


def main() -> None:
    con = sqlite3.connect(r"parser/court_districts.sqlite")
    q = """
    SELECT district_number
    FROM court_districts
    WHERE region IS NULL OR region = ''
    """
    df = pd.read_sql_query(q, con)
    con.close()

    extracted = []
    missing = 0
    for s in df["district_number"].fillna(""):
        m = re.findall(r"\d+", str(s))
        if m:
            extracted.append(m[0])
        else:
            extracted.append(None)
            missing += 1

    print("rows:", len(df))
    print("missing digits:", missing)
    c = Counter([x for x in extracted if x is not None])
    print("unique extracted:", len(c))
    print("top:", c.most_common(15))


if __name__ == "__main__":
    main()

