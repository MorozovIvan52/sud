"""
Интеграция с DaData API (подсказки адресов, стандартизация).
Регистрация: https://dadata.ru/
"""
import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

DADATA_SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
DADATA_GEOCODE_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/geolocate/address"


class DaDataService:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("DADATA_TOKEN")
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {self.token}" if self.token else "",
        }

    def suggest_address(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        """Подсказки по адресу."""
        if not self.token:
            return []
        try:
            r = requests.post(
                DADATA_SUGGEST_URL,
                headers=self.headers,
                json={"query": query, "count": count},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("suggestions", [])
        except requests.RequestException:
            return []

    def geolocate(self, lat: float, lon: float, radius_m: int = 100) -> List[Dict[str, Any]]:
        """Обратное геокодирование: координаты → адрес."""
        if not self.token:
            return []
        try:
            r = requests.post(
                DADATA_GEOCODE_URL,
                headers=self.headers,
                json={"lat": lat, "lon": lon, "radius_meters": radius_m},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("suggestions", [])
        except requests.RequestException:
            return []

    def standardize_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Стандартизация адреса (первая подсказка)."""
        suggestions = self.suggest_address(address, count=1)
        if not suggestions:
            return None
        return suggestions[0].get("data")
