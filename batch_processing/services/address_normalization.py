"""
Нормализация адресов: стандартизация сокращений, очистка лишних запятых и пробелов.
Поддержка формата «Шаблон ФССП»: 681035, , Хабаровский край , гор. Комсомольск-на-Амуре...
Опционально: приведение к стандарту ФИАС через DaData (при DADATA_TOKEN).
"""
import logging
import os
import re

logger = logging.getLogger(__name__)

# Стандартизация сокращений (гор.→г., ул→улица и т.д.)
ABBREV_MAP = [
    (r"\bгор\.\s*", "г. "),
    (r"\bгор\s+", "г. "),
    (r"\bг\s+", "г. "),
    (r"\bул\.?\s*", "улица "),
    # «пр-кт» целиком — иначе «пр» съедается правилом для «пр.» и получается «проспект -кт».
    (r"\bпр-кт\.?\s*", "проспект "),
    (r"\bпр\.\s+", "проспект "),
    (r"\bпер\.?\s*", "переулок "),
    (r"\bд\.?\s*", "д. "),
    (r"\bкв\.?\s*", "кв. "),
    (r"\bкорп\.?\s*", "корп. "),
    (r"\bстр\.?\s*", "стр. "),
    (r"\bобл\.?\s*", "область "),
    (r"\bРесп\b", "Республика "),
    (r"\bресп\b", "республика "),
]


def normalize_address(addr: str) -> str:
    """
    Нормализация адреса: очистка, стандартизация сокращений.
    Обрабатывает формат «681035, , Хабаровский край , гор. Комсомольск-на-Амуре, улица Юбилейная , 14, 3, 60».
    """
    if not addr or not isinstance(addr, str):
        return ""
    s = addr.strip()
    # 1. Убрать лишние запятые (,,  ,)
    s = re.sub(r",\s*,+", ",", s)
    s = re.sub(r",\s*,\s*", ", ", s)
    # 2. Нормализовать пробелы вокруг запятых
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = s.strip().strip(",").strip()
    # 3. Применить сокращения
    for pattern, replacement in ABBREV_MAP:
        s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)
    # 4. Убрать точки после однобуквенных сокращений в конце слов
    s = re.sub(r"\b([а-яА-Я])\s*\.\s*", r"\1. ", s)
    return s.strip()


def fix_typos(addr: str) -> str:
    """Исправление типичных опечаток в адресах."""
    if not addr:
        return ""
    s = addr
    # Двойные пробелы
    s = re.sub(r"\s{2,}", " ", s)
    # Запятая перед цифрой дома
    s = re.sub(r",\s*(\d+)\s*,\s*", r", \1, ", s)
    return s.strip()


def normalize_address_fssp(addr: str) -> str:
    """
    Полная нормализация для формата ФССП.
    Комбинирует fix_typos и normalize_address.
    """
    return normalize_address(fix_typos(addr or ""))


def normalize_address_fias(addr: str) -> str:
    """
    Нормализация адреса с приведением к стандарту ФИАС.
    Сначала базовая нормализация (normalize_address_fssp), затем при наличии DADATA_TOKEN —
    стандартизация через DaData suggest/address.
    Возвращает исходный адрес при отсутствии токена или ошибке API.
    """
    base = normalize_address_fssp(addr or "")
    if not base:
        return ""
    token = (os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or "").strip()
    if not token:
        return base
    try:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from court_locator.parser_bridge import dadata_standardize_address

        standardized = dadata_standardize_address(base, token=token)
        return standardized.strip() if standardized else base
    except Exception as e:
        logger.warning("address_normalization: DaData standardize failed: %s", e)
        return base
