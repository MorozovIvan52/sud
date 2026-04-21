import sqlite3
import pandas as pd


def main() -> None:
    con = sqlite3.connect(r"parser/court_districts.sqlite")
    q = """
    SELECT district_number, court_name, phone, email
    FROM court_districts
    WHERE region IS NULL OR region = '' OR region LIKE '%%'
    LIMIT 20
    """
    df = pd.read_sql_query(q, con)
    con.close()
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()

