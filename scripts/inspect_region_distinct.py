import sqlite3
import pandas as pd


def main() -> None:
    con = sqlite3.connect(r"parser/court_districts.sqlite")
    q = """
    SELECT region, COUNT(*) AS cnt, LENGTH(region) AS len
    FROM court_districts
    GROUP BY region
    ORDER BY cnt DESC, len ASC
    """
    df = pd.read_sql_query(q, con)
    con.close()

    # Print python repr to reveal hidden characters.
    for _, row in df.iterrows():
        region = row["region"]
        print("cnt=", int(row["cnt"]), "len=", int(row["len"]), "region_repr=", repr(region))


if __name__ == "__main__":
    main()

