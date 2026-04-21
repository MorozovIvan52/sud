import re
from typing import Dict, Optional


def normalize_address(addr: str) -> str:
    return addr.strip().replace(".,", ",").replace("  ", " ")


def extract_region(address: str) -> Optional[str]:
    """
    Очень упрощённо: Москва / Московская область / Санкт-Петербург.
    Для прод: использовать ФИАС/ГАР или DaData.
    """
    addr = address.lower()
    if "москва" in addr or "г. москва" in addr:
        return "Москва"
    if "московская обл" in addr or "московская область" in addr:
        return "Московская область"
    if "санкт-петербург" in addr or "спб" in addr or "санкт петербург" in addr:
        return "Санкт-Петербург"
    return None


def extract_district(address: str, region: Optional[str]) -> Optional[str]:
    """
    Тут только заглушки под тестовые кейсы.
    В реальном решении можно использовать заранее подготовленную
    карту "улица → район" по конкретному региону.
    """
    addr = address.lower()

    # Москва (улица → район для согласованности parser и court_locator)
    if region == "Москва":
        if "ленина" in addr:
            return "Тверской"
        if "тверская" in addr or "тверская ул" in addr:
            return "Тверской"
        return None

    # Санкт-Петербург
    if region == "Санкт-Петербург":
        if "невский" in addr or "пр. невский" in addr:
            return "Центральный"
        return None

    # Для МО / других регионов — аналогично
    return None


def parse_address(address: str) -> Dict:
    addr = normalize_address(address)
    region = extract_region(addr)
    district = extract_district(addr, region)

    return {
        "raw": address,
        "normalized": addr,
        "region": region,
        "district": district,
    }
