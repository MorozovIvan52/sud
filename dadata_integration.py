"""
Интеграция DaData для поиска суда по адресу (бесплатно 10 000 запросов/день).
Токен: dadata.ru → Бесплатный тариф → задать в DADATA_TOKEN или передать в конструктор.
"""
import os
from typing import Dict, Any, Optional

import requests


class DadataCourtFinder:
    """Поиск суда по адресу через DaData Suggest API."""

    def __init__(self, token: Optional[str] = None):
        self.token = (token or os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or "").strip()
        self.url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/court"
        self.headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def find_court_by_address(self, address: str, region: Optional[str] = None) -> Dict[str, Any]:
        """
        Находит суд по адресу (и опционально региону).
        Возвращает dict с ключами court_name, address, region, type или пустой dict при ошибке/нет токена.
        """
        if not self.token:
            return {}

        query = f"{address}, {region}".strip(", ") if region else address
        payload = {
            "query": query,
            "count": 3,
        }
        if region:
            payload["locations"] = [{"region": region}]

        try:
            response = requests.post(self.url, json=payload, headers=self.headers, timeout=10)
            if response.status_code != 200:
                return {}
            data = response.json()
            suggestions = data.get("suggestions") or []
            if not suggestions:
                return {}
            court = suggestions[0].get("data") or {}
            addr = court.get("address")
            if isinstance(addr, dict):
                address_value = addr.get("value", "")
                postal_code = addr.get("postal_code", "")
            else:
                address_value = court.get("address") or ""
                postal_code = ""
            return {
                "court_name": court.get("name") or suggestions[0].get("value", ""),
                "address": address_value,
                "postal_index": postal_code,
                "region": court.get("region", ""),
                "type": court.get("type", ""),
            }
        except Exception:
            return {}


# Удобная функция без класса (использует DADATA_TOKEN из окружения)
def find_court_by_address(address: str, region: Optional[str] = None) -> Dict[str, Any]:
    """Тонкая обёртка над DadataCourtFinder.find_court_by_address."""
    return DadataCourtFinder().find_court_by_address(address, region)
