"""Заглушки источников данных для верификации."""
from typing import Dict, Any, Optional


class DataSources:
    @staticmethod
    def fetch_official(court_id: int) -> Dict[str, Any]:
        return {"source": "official", "available": False}

    @staticmethod
    def fetch_regional(region_code: str) -> Optional[Dict[str, Any]]:
        return None

    @staticmethod
    def fetch_commercial(court_data: Dict[str, Any]) -> Dict[str, Any]:
        return {}
