import sqlite3
import pandas as pd


def main() -> None:
    con = sqlite3.connect(r"parser/court_districts.sqlite")
    q = """
    SELECT region, COUNT(*) as cnt
    FROM court_districts
    GROUP BY region
    ORDER BY cnt DESC
    """
    df = pd.read_sql_query(q, con)
    con.close()

    print(df.head(30).to_string(index=False))


if __name__ == "__main__":
    main()

