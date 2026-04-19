"""
Интеграция с Яндекс.Геокодер (HTTP API).
Кабинет: https://developer.tech.yandex.ru/
"""
import os
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

YANDEX_GEOCODER_URL = "https://geocode-maps.yandex.ru/1.x/"


class YandexMapsService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = (
            api_key
            or os.getenv("YANDEX_API_KEY")
            or os.getenv("YANDEX_GEO_KEY")
            or os.getenv("YANDEX_LOCATOR_API_KEY")
        )
        self.base_url = YANDEX_GEOCODER_URL

    def geocode(self, address: str) -> Dict[str, Any]:
        """Геокодирование адреса. Возвращает ответ API Яндекс.Карт."""
        if not self.api_key:
            return {"error": "YANDEX_API_KEY не задан"}
        params = {
            "apikey": self.api_key,
            "geocode": address,
            "format": "json",
        }
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}

    def geocode_to_coords(self, address: str) -> Optional[tuple]:
        """Возвращает (latitude, longitude) или None."""
        data = self.geocode(address)
        if "error" in data:
            return None
        try:
            geo = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
            if not geo:
                return None
            pos = geo[0].get("GeoObject", {}).get("Point", {}).get("pos", "")
            if not pos:
                return None
            lon, lat = map(float, pos.split())
            return (lat, lon)
        except (KeyError, ValueError, IndexError):
            return None
