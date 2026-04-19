"""
Данные с dagalin.org в ответ поиска суда: в первую очередь живой парсинг карточки,
при недоступности сайта — кэш detail_json в БД.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from court_locator.database import Database
from court_locator.dagalin_live import merge_live_or_cached_dagalin


def enrich_court_with_dagalin(court: Optional[Dict[str, Any]], db: Database) -> None:
    """
    Находит строку dagalin_mirovye_courts по названию/участку, тянет HTML с dagalin.org,
    заполняет court_name, address, phone, email, schedule, superior_court,
    state_fee_requisites, bailiffs. Если HTTP не удался — только блоки из detail_json.
    """
    if not court:
        return
    if court.get("source") == "dagalin_address_match":
        return
    row = db.find_dagalin_row_for_court(
        court.get("court_name") or court.get("name"),
        court.get("section_num"),
    )
    if not row:
        return
    merge_live_or_cached_dagalin(court, row, db)
