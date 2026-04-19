"""Коды ошибок и рекомендации для листа «Ошибки»."""
from typing import Dict

ERROR_ADDRESS_NOT_FOUND = "ERROR_ADDRESS_NOT_FOUND"
ERROR_AMBIGUOUS = "ERROR_AMBIGUOUS"
ERROR_LOW_PRECISION = "ERROR_LOW_PRECISION"
ERROR_COURT_NOT_FOUND = "ERROR_COURT_NOT_FOUND"
ERROR_EMPTY_ROW = "ERROR_EMPTY_ROW"
ERROR_NO_ADDRESS = "ERROR_NO_ADDRESS"
ERROR_INVALID_COORDS = "ERROR_INVALID_COORDS"

ERROR_LABELS: Dict[str, str] = {
    ERROR_ADDRESS_NOT_FOUND: "Адрес не найден",
    ERROR_AMBIGUOUS: "Неоднозначный адрес",
    ERROR_LOW_PRECISION: "Низкая точность геокодирования",
    ERROR_COURT_NOT_FOUND: "Суд не найден",
    ERROR_EMPTY_ROW: "Пустая строка",
    ERROR_NO_ADDRESS: "Адрес не указан",
    ERROR_INVALID_COORDS: "Некорректные координаты",
}

RECOMMENDATIONS: Dict[str, str] = {
    ERROR_ADDRESS_NOT_FOUND: "Проверьте адрес, добавьте город и номер дома. Используйте формат: индекс, регион, город, улица, дом, квартира.",
    ERROR_AMBIGUOUS: "Уточните адрес: укажите регион или полный адрес.",
    ERROR_LOW_PRECISION: "Адрес определён приблизительно. Уточните номер дома и квартиры.",
    ERROR_COURT_NOT_FOUND: "Точка не попадает в границы судебных участков. Проверьте координаты или адрес.",
    ERROR_EMPTY_ROW: "Заполните обязательные поля: адрес или ФИО.",
    ERROR_NO_ADDRESS: "Укажите адрес регистрации.",
    ERROR_INVALID_COORDS: "Широта: -90..90, долгота: -180..180. Проверьте формат координат.",
}


def get_error_code(msg: str) -> str:
    """Извлекает код ошибки из сообщения или возвращает ERROR_COURT_NOT_FOUND по умолчанию."""
    m = (msg or "").lower()
    if "адрес не найден" in m or "address_not_found" in m:
        return ERROR_ADDRESS_NOT_FOUND
    if "неоднозначн" in m or "ambiguous" in m:
        return ERROR_AMBIGUOUS
    if "низкая точность" in m or "low_precision" in m:
        return ERROR_LOW_PRECISION
    if "суд не найден" in m or "границы" in m:
        return ERROR_COURT_NOT_FOUND
    if "пустая строка" in m:
        return ERROR_EMPTY_ROW
    if "адрес не указан" in m:
        return ERROR_NO_ADDRESS
    if "координат" in m or "широт" in m or "долгот" in m:
        return ERROR_INVALID_COORDS
    return ERROR_COURT_NOT_FOUND


def get_recommendation(error_code: str) -> str:
    return RECOMMENDATIONS.get(error_code, "Обратитесь к документации или уточните данные вручную.")
