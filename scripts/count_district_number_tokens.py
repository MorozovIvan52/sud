import re
import sqlite3
from collections import Counter

import pandas as pd


def main() -> None:
    con = sqlite3.connect(r"parser/court_districts.sqlite")
    df = pd.read_sql_query("SELECT district_number FROM court_districts", con)
    con.close()

    tokens = []
    for s in df["district_number"].fillna("").astype(str):
        m = re.findall(r"\d+", s)
        tokens.append(m[0] if m else None)

    c = Counter([t for t in tokens if t is not None])
    print("total rows:", len(tokens))
    print("missing token:", sum(1 for t in tokens if t is None))
    print("token distribution:")
    def sort_key(item):
        k, _v = item
        try:
            return int(k)
        except Exception:
            return 10**9

    for k, v in sorted(c.items(), key=sort_key):
        print(" ", k, "=>", v)


if __name__ == "__main__":
    main()

