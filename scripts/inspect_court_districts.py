import sqlite3
import pandas as pd


def main() -> None:
    db_path = r"parser/court_districts.sqlite"
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print("tables:", tables)

    cols = cur.execute("PRAGMA table_info(court_districts)").fetchall()
    print("court_districts columns:", [(c[1], c[2]) for c in cols])

    q = """
    SELECT district_number, region, court_name, boundaries
    FROM court_districts
    WHERE region LIKE '%Нижегород%'
    LIMIT 5
    """
    df = pd.read_sql_query(q, con)
    print(df.to_string(index=False))

    con.close()


if __name__ == "__main__":
    main()

