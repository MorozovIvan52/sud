"""
Шаблон JSON для автозаполнения искового заявления
(взыскание задолженности по договору микрозайма).
Данные можно передать в docxtpl/jinja2 для генерации DOCX/RTF.
"""
from typing import Dict, Any
from jurisdiction import CourtResult


def build_claim_json(
    court: CourtResult,
    input_data: Dict[str, Any],
    plaintiff_data: Dict[str, Any],
    calc: Dict[str, Any],
) -> Dict[str, Any]:
    """
    input_data: те же данные, что подаются в determine_jurisdiction.
    plaintiff_data: реквизиты МФО (истец).
    calc: готовый расчёт (principal_debt, interest, penalty, state_duty, price).
    """
    fio = input_data.get("fio", "")
    passport = input_data.get("passport", "")
    issued_by = input_data.get("issued_by", "")
    address = input_data.get("address", "")
    contract_date = input_data.get("contract_date", "")
    debt_amount = input_data.get("debt_amount", 0)

    passport_digits = "".join(ch for ch in str(passport) if ch.isdigit())
    series = passport_digits[:4] if len(passport_digits) >= 4 else ""
    number = passport_digits[4:10] if len(passport_digits) >= 10 else ""

    claim_json = {
        "court": {
            "name": court.court_name,
            "address": court.address,
            "index": court.index,
            "jurisdiction_type": court.jurisdiction_type,
            "gpk_article": court.gpk_article,
        },
        "plaintiff": plaintiff_data,
        "defendant": {
            "fio": fio,
            "birth_date": input_data.get("birth_date", ""),
            "passport_series": series,
            "passport_number": number,
            "passport_issued_by": issued_by,
            "passport_issue_date": input_data.get("passport_issue_date", ""),
            "address_registration": address,
            "address_residence": input_data.get("address_residence", address),
        },
        "claim": {
            "claim_type": "взыскание задолженности по договору микрозайма",
            "price": calc.get("price", debt_amount),
            "principal_debt": calc.get("principal_debt", debt_amount),
            "interest": calc.get("interest", 0),
            "penalty": calc.get("penalty", 0),
            "state_duty": calc.get("state_duty", 0),
        },
        "contract": {
            "number": input_data.get("contract_number", ""),
            "date": contract_date,
            "amount": debt_amount,
            "term_to": input_data.get("contract_term_to", ""),
            "interest_rate": input_data.get("interest_rate", 0),
            "payment_schedule": input_data.get("payment_schedule", ""),
            "way_of_conclusion": input_data.get("way_of_conclusion", "дистанционно"),
        },
        "facts": {
            "pretrial_order": {
                "is_required": input_data.get("pretrial_required", False),
                "demand_sent": input_data.get("demand_sent", True),
                "demand_date": input_data.get("demand_date", ""),
                "demand_delivery_proof": input_data.get(
                    "demand_delivery_proof", ""
                ),
            },
            "default_date": input_data.get("default_date", ""),
            "calculation_period_from": input_data.get("calc_from", ""),
            "calculation_period_to": input_data.get("calc_to", ""),
        },
        "attachments": [
            "Копия договора микрозайма",
            "Расчёт задолженности",
            "Копия требования (претензии) о погашении задолженности",
            "Доказательства направления требования ответчику",
            "Квитанция об оплате государственной пошлины",
            "Доверенность представителя",
            "Копия искового заявления для ответчика",
        ],
    }

    return claim_json
