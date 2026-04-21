import os
import sqlite3
import pandas as pd


def main() -> None:
    db_path = r"parser/court_districts.sqlite"
    out_dir = r"batch_outputs"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "nizhny_magistrate_court_districts.xlsx")

    con = sqlite3.connect(db_path)
    q = """
    SELECT district_number, court_name, boundaries
    FROM court_districts
    WHERE region LIKE '%Нижегородская область%'
    """
    df = pd.read_sql_query(q, con)
    con.close()

    if df.empty:
        raise SystemExit("No rows found for region LIKE '%Нижегородская область%'.")

    # Sort numerically when possible (district_number stored as TEXT).
    df["district_num_int"] = pd.to_numeric(df["district_number"], errors="coerce")
    df = df.sort_values(["district_num_int", "district_number"], na_position="last")

    df_out = pd.DataFrame(
        {
            "номер_и_наименование": df["district_number"].astype(str)
            + " — "
            + df["court_name"].fillna("").astype(str),
            "описание_границ": df["boundaries"].fillna("").astype(str),
        }
    )

    df_out.to_excel(out_path, index=False)
    print("Saved:", out_path)
    print("Rows:", len(df_out))


if __name__ == "__main__":
    main()

