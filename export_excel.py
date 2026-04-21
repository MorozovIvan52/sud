from typing import List, Dict, Any
import pandas as pd

from jurisdiction import determine_jurisdiction, CourtResult
from courts_db import init_db, seed_example_data


def process_cases_to_excel(test_cases: List[Dict[str, Any]], out_path: str):
    init_db()
    seed_example_data()

    rows = []
    for case in test_cases:
        cr: CourtResult = determine_jurisdiction(case)
        rows.append(
            {
                "fio": case.get("fio"),
                "passport": case.get("passport"),
                "address": case.get("address"),
                "debt_amount": case.get("debt_amount"),
                "contract_date": case.get("contract_date"),
                "court_name": cr.court_name,
                "court_address": cr.address,
                "court_index": cr.index,
                "jurisdiction_type": cr.jurisdiction_type,
                "gpk_article": cr.gpk_article,
                "source": cr.source,
            }
        )
    df = pd.DataFrame(rows)
    df.to_excel(out_path, index=False)


if __name__ == "__main__":
    test_cases = [
        {"fio": "Петров П.П.", "passport": "4509 123456", "address": "Москва, ул. Ленина 15", "debt_amount": 15000,
         "contract_date": "2026-02-15"},
        {"fio": "Сидорова А.А.", "passport": "7710 654321", "address": "СПб, пр. Невский 10", "debt_amount": 20000,
         "contract_date": "2026-01-10"},
    ]
    process_cases_to_excel(test_cases, "cases_output.xlsx")
