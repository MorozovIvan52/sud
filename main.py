import json
from jurisdiction import determine_jurisdiction, CourtResult
from courts_db import init_db, seed_example_data

try:
    from env_config import load_dotenv_if_available
    load_dotenv_if_available()
except ImportError:
    pass


def court_result_to_json(cr: CourtResult) -> dict:
    return {
        "court_name": cr.court_name,
        "address": cr.address,
        "index": cr.index,
        "jurisdiction_type": cr.jurisdiction_type,
        "gpk_article": cr.gpk_article,
    }


def run_example():
    init_db()
    seed_example_data()

    data = {
        "fio": "Иванов Иван Иванович",
        "passport": "4509 123456",
        "issued_by": "ОВД России по району",
        "address": "г. Москва, ул. Ленина, д. 15",
        "debt_amount": 15000,
        "contract_date": "2026-02-15",
    }

    result = determine_jurisdiction(data)
    print(json.dumps(court_result_to_json(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run_example()
