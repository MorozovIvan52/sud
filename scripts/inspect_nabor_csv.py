from __future__ import annotations

import pandas as pd
from pathlib import Path
import csv

path = Path(r"C:\Users\1\Downloads\Nabor-dannykh-13.04.2023.csv")

for enc in ("utf-8", "cp1251", "latin-1"):
    try:
        df = pd.read_csv(path, sep=";", encoding=enc)
        print("encoding:", enc)
        print("columns repr:", [repr(c) for c in df.columns])
        print(df.head(3).to_dict(orient="records"))
        break
    except Exception as e:
        print(enc, "fail", e)

print("\nFirst row via csv.DictReader (cp1251):")
with path.open("r", encoding="cp1251") as f:
    reader = csv.DictReader(f, delimiter=";")
    first = next(reader)
    print({k: repr(v) for k, v in first.items()})

