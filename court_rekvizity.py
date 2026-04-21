"""
Схема справочника реквизитов судов для заполнения court_details.
См. docs/analysis_molotok_junona_requisites.md.

Структура: код суда (region + section_num) → БИК, ИНН, КПП, Счет, ОКТМО, УФК, казначейский счёт, Банк.

Загрузка: CSV с колонками region, section_num, bik, inn, kpp, account, oktmo, ufk, treasury_account, bank.
"""
from pathlib import Path
from typing import Dict, Optional

# Маппинг ключей справочника → поля court_details
REKVIZITY_TO_COURT_DETAILS: Dict[str, str] = {
    "bik": "БИК",
    "inn": "ИНН",
    "kpp": "КПП",
    "account": "Счет",
    "oktmo": "ОКТМО",
    "ufk": "УФК",
    "treasury_account": "№ казначейского счета",
    "bank": "Банк",
}

_REKVIZITY_STORE: Dict[str, Dict[str, str]] = {}


def make_court_key(region: str, section_num: int = 0) -> str:
    """Ключ для поиска в справочнике: region + section_num."""
    r = (region or "").strip()
    s = int(section_num) if section_num is not None else 0
    return f"{r}|{s}"


def lookup_rekvizity(region: str, section_num: int = 0) -> Dict[str, str]:
    """
    Поиск реквизитов по региону и номеру участка.
    Возвращает словарь с полями court_details (БИК, ИНН, КПП, Счет, ОКТМО, УФК и т.д.).
    """
    key = make_court_key(region, section_num)
    row = _REKVIZITY_STORE.get(key)
    if not row:
        return {}
    return {REKVIZITY_TO_COURT_DETAILS[k]: v for k, v in row.items() if k in REKVIZITY_TO_COURT_DETAILS and v}


def load_rekvizity_from_csv(path: Path, *, delimiter: str = ";") -> int:
    """
    Загружает справочник из CSV.
    Колонки: region, section_num, bik, inn, kpp, account, oktmo, ufk, treasury_account, bank.
    """
    import csv
    path = Path(path)
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            region = (row.get("region") or row.get("Регион") or "").strip()
            if not region:
                continue
            try:
                section = int(row.get("section_num") or row.get("Участок") or 0)
            except (ValueError, TypeError):
                section = 0
            key = make_court_key(region, section)
            _REKVIZITY_STORE[key] = {
                "bik": (row.get("bik") or row.get("БИК") or "").strip(),
                "inn": (row.get("inn") or row.get("ИНН") or "").strip(),
                "kpp": (row.get("kpp") or row.get("КПП") or "").strip(),
                "account": (row.get("account") or row.get("Счет") or "").strip(),
                "oktmo": (row.get("oktmo") or row.get("ОКТМО") or "").strip(),
                "ufk": (row.get("ufk") or row.get("УФК") or "").strip(),
                "treasury_account": (row.get("treasury_account") or row.get("Казначейский счёт") or "").strip(),
                "bank": (row.get("bank") or row.get("Банк") or "").strip(),
            }
            count += 1
    return count
