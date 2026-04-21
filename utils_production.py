# utils_production.py — утилиты для продакшена: очистка кэша, бэкап.

import sqlite3
from datetime import datetime
from pathlib import Path

_ULTIMATE_CACHE_DB = Path(__file__).resolve().parent / "ultimate_cache.sqlite"


def init_production_db() -> None:
    """Удаление записей кэша старше 30 дней и VACUUM."""
    if not _ULTIMATE_CACHE_DB.exists():
        return
    conn = sqlite3.connect(_ULTIMATE_CACHE_DB)
    conn.execute(
        "DELETE FROM cache WHERE julianday('now') - julianday(cached_at) > 30"
    )
    conn.execute("VACUUM")
    conn.commit()
    conn.close()


def backup_cache() -> str:
    """Копирование кэша в файл с датой в имени. Возвращает путь к бэкапу."""
    from shutil import copyfile
    if not _ULTIMATE_CACHE_DB.exists():
        return ""
    dest = _ULTIMATE_CACHE_DB.parent / f"backup_cache_{datetime.now().strftime('%Y%m%d')}.sqlite"
    copyfile(str(_ULTIMATE_CACHE_DB), str(dest))
    return str(dest)
