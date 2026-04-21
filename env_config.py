"""
Переменные окружения и шаблон .env из документации.

Соответствует docs/apis_and_keys.md: список API, имена переменных, шаблон .env,
подсказка «чего не хватает для поиска».
"""

import os
from typing import List, Tuple

# --- Имена переменных из docs/apis_and_keys.md (разделы 1–10) ---

# Обязательные для подсудности
DADATA_TOKEN = "DADATA_TOKEN"
DADATA_SECRET = "DADATA_SECRET"
COURTS_DB_BACKEND = "COURTS_DB_BACKEND"

# ФССП
FSSP_API_KEY = "FSSP_API_KEY"
FSSP_TOKEN = "FSSP_TOKEN"
FSSP_API_BASE = "FSSP_API_BASE"
FSSP_TIMEOUT = "FSSP_TIMEOUT"
FSSP_MAX_REQUESTS_PER_MINUTE = "FSSP_MAX_REQUESTS_PER_MINUTE"

# Капча
TWOCAPTCHA_API_KEY = "TWOCAPTCHA_API_KEY"
CAPTCHA_API_KEY = "CAPTCHA_API_KEY"
ANTICAPTCHA_API_KEY = "ANTICAPTCHA_API_KEY"
CAPMONSTER_API_KEY = "CAPMONSTER_API_KEY"
CAPSOLVER_API_KEY = "CAPSOLVER_API_KEY"

# Арбитраж
KAD_ARBITR_USER_AGENT = "KAD_ARBITR_USER_AGENT"
KAD_ARBITR_PROXY = "KAD_ARBITR_PROXY"
KAD_ARBITR_DELAY_MIN = "KAD_ARBITR_DELAY_MIN"
KAD_ARBITR_DELAY_MAX = "KAD_ARBITR_DELAY_MAX"

# Геокодирование
YANDEX_GEO_KEY = "YANDEX_GEO_KEY"

# Telegram
BOT_TOKEN = "BOT_TOKEN"
ADMIN_ID = "ADMIN_ID"
MONITOR_CHAT_ID = "MONITOR_CHAT_ID"

# Кэш и инфраструктура
REDIS_HOST = "REDIS_HOST"
REDIS_PORT = "REDIS_PORT"
REDIS_URL = "REDIS_URL"
PG_DSN = "PG_DSN"

# LLM
GIGACHAT_CREDENTIALS = "GIGACHAT_CREDENTIALS"
GIGACHAT_API_KEY = "GIGACHAT_API_KEY"
YANDEX_GPT_API_KEY = "YANDEX_GPT_API_KEY"
YANDEX_GPT_CATALOG_ID = "YANDEX_GPT_CATALOG_ID"

# Опциональные
AIS_VESSELFINDER_KEY = "AIS_VESSELFINDER_KEY"
CORS_ORIGINS = "CORS_ORIGINS"
API_HOST = "API_HOST"
API_PORT = "API_PORT"
API_RELOAD = "API_RELOAD"


def get_env_template() -> str:
    """Шаблон .env из docs/apis_and_keys.md (раздел 10)."""
    return """# Подсудность и адреса (Profile API — баланс/статистика — требует и Secret)
DADATA_TOKEN=ваш_токен_dadata
DADATA_SECRET=ваш_секретный_ключ_dadata

# БД судов (оставьте по умолчанию или postgres)
COURTS_DB_BACKEND=sqlite

# ФССП — единый клиент parser/fssp_client.py (ключ в заголовок не коммитить)
# FSSP_API_KEY=
# FSSP_API_BASE=https://api.fssp.gov.ru

# Капча (если нужна для ГАС)
# TWOCAPTCHA_API_KEY=
# ANTICAPTCHA_API_KEY=

# Геокодирование
# YANDEX_GEO_KEY=

# Telegram бот
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_ID=ваш_telegram_id

# Кэш
REDIS_HOST=localhost
REDIS_PORT=6379

# PostgreSQL (если COURTS_DB_BACKEND=postgres)
# PG_DSN=dbname=courts user=postgres password=... host=localhost port=5432

# LLM (оба опциональны; если один не работает, используется второй)
# GIGACHAT_CREDENTIALS=
# YANDEX_GPT_API_KEY=
# YANDEX_GPT_CATALOG_ID=
"""


def load_dotenv_if_available() -> None:
    """Вызвать load_dotenv() если установлен python-dotenv. Из docs/apis_and_keys.md."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def what_is_missing_for_search() -> List[Tuple[str, str]]:
    """
    Мега-подсказка из docs/apis_and_keys.md: чего не хватает, чтобы проект «начал искать».
    Возвращает список (название, рекомендация).
    """
    missing = []
    if not (os.getenv(DADATA_TOKEN) or os.getenv("DADATA_API_KEY")):
        missing.append((
            "DaData",
            "Без DADATA_TOKEN/DADATA_API_KEY не будет подсказки суда через DaData; остаются БД по району, Yandex Geocoder (YANDEX_GEO_KEY) и unified_jurisdiction.",
        ))
    # БД судов — проверяем наличие courts.sqlite и что в нём есть записи
    try:
        try:
            from courts_db import DB_PATH
        except ImportError:
            from parser.courts_db import DB_PATH
        if not DB_PATH.exists():
            missing.append((
                "БД судов",
                "Файл БД не создан. Запустить run_fill_courts_db.py --method seed или dadata (docs/howto_fill_courts_db.md).",
            ))
        else:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            try:
                cur = conn.execute("SELECT COUNT(*) FROM courts")
                count = cur.fetchone()[0]
                if count == 0:
                    missing.append((
                        "БД судов",
                        "Репозиторий судов пуст. Запустить run_fill_courts_db.py (docs/howto_fill_courts_db.md).",
                    ))
            except sqlite3.OperationalError:
                missing.append((
                    "БД судов",
                    "Таблица courts не создана. Запустить run_fill_courts_db.py --method seed.",
                ))
            finally:
                conn.close()
    except Exception:
        missing.append((
            "БД судов",
            "Заполнить courts.sqlite: run_fill_courts_db.py (docs/howto_fill_courts_db.md).",
        ))
    if not (os.getenv(FSSP_API_KEY) or os.getenv(FSSP_TOKEN)):
        missing.append((
            "ФССП",
            "Для реальных данных по ИП — оформить доступ на fssp.gov.ru и прописать FSSP_API_KEY в .env. Парсинг веб-интерфейса: run_fssp_web_search.py.",
        ))
    return missing


def print_env_template() -> None:
    """Вывести шаблон .env в консоль (для создания файла вручную)."""
    print(get_env_template())


def write_env_template(path: str = ".env.example") -> None:
    """Записать шаблон .env в файл (например .env.example). Не перезаписывает существующий .env."""
    from pathlib import Path
    p = Path(path)
    if p.exists() and p.name == ".env":
        return  # не перезаписывать реальный .env
    p.write_text(get_env_template(), encoding="utf-8")


if __name__ == "__main__":
    import sys
    load_dotenv_if_available()
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        missing = what_is_missing_for_search()
        if not missing:
            print("Для поиска/подсудности достаточно: DaData и БД судов заполнены.")
        else:
            print("Мега-подсказка (docs/apis_and_keys.md): чего не хватает:")
            for name, msg in missing:
                print(f"  • {name}: {msg}")
    elif len(sys.argv) > 1 and sys.argv[1] == "write":
        write_env_template(sys.argv[2] if len(sys.argv) > 2 else ".env.example")
        print("Шаблон записан в .env.example")
    else:
        print("Использование: python env_config.py [check|write [path]]")
        print("  check — что не хватает для поиска; write — записать шаблон .env в .env.example")
        print("Шаблон .env (фрагмент):")
        print(get_env_template()[:600] + "...")
