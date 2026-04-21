import sqlite3


def inspect_db(path: str) -> None:
    print("\nDB:", path)
    con = sqlite3.connect(path)
    cur = con.cursor()
    tables = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print("tables:", [t[0] for t in tables])
    for (name,) in tables:
        cnt = cur.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(" -", name, "rows:", cnt)
    con.close()


def main() -> None:
    inspect_db(r"parser/courts.sqlite")
    inspect_db(r"parser/court_districts.sqlite")
    inspect_db(r"parser/courts_geo.sqlite")


if __name__ == "__main__":
    main()

