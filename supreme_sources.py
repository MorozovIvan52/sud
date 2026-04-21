# supreme_sources.py — сводка источников судебных данных РФ (все суды в одном месте).

from typing import Dict

ALL_SOURCES = {
    "fssp": "45 МЛН ИП",
    "world_courts": "85k участков",
    "kad_arbitr": "2.1 МЛН дел",
    "gas_pravosudie": "95% дел",
    "sudrf": "2k+ районных судов",
    "efrsb": "1.2 МЛН банкротств",
}

SOURCE_DESCRIPTIONS = {
    "fssp": "Исполнительные производства (ФССП)",
    "world_courts": "Мировые суды (ИП / физлица)",
    "kad_arbitr": "Арбитраж (компании, kad.arbitr.ru)",
    "gas_pravosudie": "ГАС «Правосудие»",
    "sudrf": "Суды общей юрисдикции (sudrf.ru)",
    "efrsb": "ЕФРСБ — банкротства",
}


def get_sources_info() -> Dict[str, str]:
    """Возвращает ALL_SOURCES с описаниями для лендинга/API."""
    return {k: f"{v} — {SOURCE_DESCRIPTIONS.get(k, '')}" for k, v in ALL_SOURCES.items()}
