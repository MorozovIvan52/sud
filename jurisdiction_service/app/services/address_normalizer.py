"""
Нормализация адресов: очистка, стандартизация сокращений.
Интеграция с ФИАС (опционально через DaData).
См. habr.com/ru/articles/672186/
"""
import hashlib
import re
from typing import Optional

from app.core.exceptions import ValidationError


# Стандартизация сокращений: "ул." -> "улица", "гор." -> "г." и т.д.
ABBREV_MAP: list[tuple[str, str]] = [
    (r"\bгор\.\s*", "г. "),
    (r"\bгор\s+", "г. "),
    (r"\bг\s+", "г. "),
    (r"\bул\.?\s*", "улица "),
    (r"\bпр\.?\s*", "проспект "),
    (r"\bпер\.?\s*", "переулок "),
    (r"\bд\.?\s*", "д. "),
    (r"\bкв\.?\s*", "кв. "),
    (r"\bкорп\.?\s*", "корп. "),
    (r"\bстр\.?\s*", "стр. "),
    (r"\bобл\.?\s*", "область "),
    (r"\bРесп\.?\s*", "Республика "),
    (r"\bресп\.?\s*", "республика "),
]


class AddressNormalizer:
    """Нормализация и валидация адресов."""

    def normalize(self, address: str) -> str:
        """
        Очистка и стандартизация адреса.
        Убирает лишние запятые, пробелы, приводит сокращения к стандарту.
        """
        if not address or not isinstance(address, str):
            raise ValidationError("Адрес не указан", field="address")

        s = address.strip()
        if len(s) < 5:
            raise ValidationError("Адрес слишком короткий", field="address")

        # Убрать лишние запятые
        s = re.sub(r",\s*,+", ",", s)
        s = re.sub(r"\s*,\s*", ", ", s)
        s = re.sub(r"\s{2,}", " ", s)
        s = s.strip().strip(",").strip()

        # Применить сокращения
        for pattern, replacement in ABBREV_MAP:
            s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)

        return s.strip()

    def normalize_with_fias(self, address: str, dadata_token: Optional[str] = None) -> str:
        """
        Нормализация с опциональной проверкой через DaData (ФИАС).
        При отсутствии токена — только базовая нормализация.
        """
        normalized = self.normalize(address)
        if not dadata_token:
            return normalized

        try:
            import httpx
            resp = httpx.post(
                "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address",
                json={"query": normalized, "count": 1},
                headers={"Authorization": f"Token {dadata_token}", "Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                suggestions = data.get("suggestions") or []
                if suggestions:
                    return (suggestions[0].get("data", {}).get("value") or suggestions[0].get("value", normalized)).strip()
        except Exception:
            pass
        return normalized

    @staticmethod
    def hash_address(address: str) -> str:
        """Хеш адреса для кэширования."""
        return hashlib.sha256(address.strip().lower().encode("utf-8")).hexdigest()
