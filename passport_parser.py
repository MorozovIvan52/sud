from typing import Dict

# Очень грубая карта: для реальной работы расширить по официальному справочнику
PASSPORT_CODE_REGION_MAP = {
    "770": "Москва",
    "771": "Московская область",
    "450": "Москва",       # старые коды
    "451": "Москва",
    "504": "Санкт-Петербург",
    "780": "Санкт-Петербург",
}


def parse_passport_code(code: str) -> Dict:
    """
    code: '4509 123456' или '4509123456' или '770-123'.
    Возвращает dict с region_code и region_name.
    """
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) < 3:
        return {"region_code": None, "region_name": None}

    prefix3 = digits[:3]
    region_name = PASSPORT_CODE_REGION_MAP.get(prefix3)
    return {"region_code": prefix3, "region_name": region_name}
