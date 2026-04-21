import sqlite3
import pandas as pd


def main() -> None:
    con = sqlite3.connect(r"parser/court_districts.sqlite")
    q = """
    SELECT district_number, court_name
    FROM court_districts
    WHERE region = '18'
    LIMIT 30
    """
    df = pd.read_sql_query(q, con)
    con.close()

    def safe(v: object) -> str:
        s = "" if v is None else str(v)
        return s.encode("unicode_escape").decode("ascii")

    df["district_number_repr"] = df["district_number"].apply(safe)
    df["court_name_repr"] = df["court_name"].apply(safe)
    print(df[["district_number_repr", "court_name_repr"]].to_string(index=False))


if __name__ == "__main__":
    main()

