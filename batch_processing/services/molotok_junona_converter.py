"""
Конвертер результата обработки в формат Молоток Юнона.
См. docs/analysis_molotok_junona_requisites.md.

Вход: результат process_debtor (45 полей court_details).
Выход: колонки для загрузки в Молоток Юнона.
"""
from typing import Any, Dict, List, Optional

# Колонки выходного файла Молоток Юнона (docs/analysis_molotok_junona_requisites.md)
MOLOTOK_JUNONA_COLUMNS: List[str] = [
    "№ Договора",
    "Банк получателя",
    "БИК",
    "ИНН",
    "КПП",
    "№ Счета",
    "Наименование получателя платежа",
    "КБК",
    "ОКТМО",
    "№ казначейского счета",
]

# Маппинг наших полей → Молоток Юнона
DEBTOR_TO_MOLOTOK_MAP: Dict[str, str] = {
    "КБК": "КБК",
    "ИНН": "ИНН",
    "КПП": "КПП",
    "Счет": "№ Счета",
    "БИК": "БИК",
    "УФК": "Банк получателя",
    "ОКТМО": "ОКТМО",
}


def convert_debtor_to_molotok_junona(
    debtor_row: Dict[str, Any],
    *,
    contract_id: Optional[str] = None,
    treasury_account: Optional[str] = None,
) -> Dict[str, str]:
    """
    Преобразует строку результата process_debtor в формат Молоток Юнона.

    :param debtor_row: результат build_court_details (45 полей)
    :param contract_id: № Договора (если не передан — берётся из id/Номер договора входного файла)
    :param treasury_account: № казначейского счета (из справочника по региону, если есть)
    :return: словарь с колонками MOLOTOK_JUNONA_COLUMNS
    """
    out: Dict[str, str] = {col: "" for col in MOLOTOK_JUNONA_COLUMNS}

    # № Договора — из входных данных или сгенерированный
    out["№ Договора"] = str(contract_id or debtor_row.get("id") or debtor_row.get("contract_number") or "").strip()

    # Реквизиты из court_details (сейчас большинство пустые — нужен справочник)
    out["Банк получателя"] = (debtor_row.get("УФК") or "").strip()
    out["БИК"] = (debtor_row.get("БИК") or "").strip()
    out["ИНН"] = (debtor_row.get("ИНН") or "").strip()
    out["КПП"] = (debtor_row.get("КПП") or "").strip()
    out["№ Счета"] = (debtor_row.get("Счет") or "").strip()
    out["Наименование получателя платежа"] = "Казначейство России (ФНС России)"
    out["КБК"] = (debtor_row.get("КБК") or "18210803010011050110").strip()
    out["ОКТМО"] = (debtor_row.get("ОКТМО") or "").strip()
    out["№ казначейского счета"] = str(treasury_account or "").strip()

    return out


def convert_batch_to_molotok_junona(
    debtor_rows: List[Dict[str, Any]],
    *,
    id_key: str = "id",
    contract_number_key: str = "contract_number",
) -> List[Dict[str, str]]:
    """
    Пакетное преобразование списка результатов в формат Молоток Юнона.
    """
    result: List[Dict[str, str]] = []
    for row in debtor_rows:
        contract_id = row.get(id_key) or row.get(contract_number_key)
        result.append(convert_debtor_to_molotok_junona(row, contract_id=contract_id))
    return result
