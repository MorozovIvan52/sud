import re
import sqlite3
import pandas as pd


def main() -> None:
    con = sqlite3.connect(r"parser/court_districts.sqlite")
    q = """
    SELECT district_number
    FROM court_districts
    WHERE region = '18'
    """
    df = pd.read_sql_query(q, con)
    con.close()

    texts = df["district_number"].fillna("").astype(str).tolist()
    joined = "\n".join(texts)

    # Check presence of some typical 2-digit numbers.
    targets = [str(x) for x in range(10, 21)]
    present = {t: (t in joined) for t in targets}
    print("2-digit presence (10..20):", present)

    # Also count extracted integer tokens.
    tokens = []
    for s in texts:
        tokens += re.findall(r"\d+", s)
    print("extracted tokens unique:", sorted(set(tokens), key=lambda x: int(x)))


if __name__ == "__main__":
    main()

