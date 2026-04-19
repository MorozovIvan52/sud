"""
Настройки модуля court_locator: ключи API и пути к БД из текущего проекта.
Все переменные читаются из окружения или .env (см. docs/apis_and_keys.md).
"""
import os
from pathlib import Path

# Корень проекта (родитель папки court_locator)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARSER_DIR = PROJECT_ROOT / "parser"

# БД судов проекта: parser/courts.sqlite и parser/courts_geo.sqlite
COURTS_DB_PATH = os.getenv("COURTS_DB_PATH") or str(PARSER_DIR / "courts.sqlite")
COURTS_GEO_DB_PATH = os.getenv("COURTS_GEO_DB_PATH") or str(PARSER_DIR / "courts_geo.sqlite")
# БД полигонов участков (если есть границы) — рядом с courts или отдельный файл
COURT_DISTRICTS_DB_PATH = os.getenv("COURT_DISTRICTS_DB_PATH") or str(PARSER_DIR / "court_districts.sqlite")

# Yandex Geocoder (приоритетный геокодер).
# Для совпадения результата с Parser при поиске по координатам нужен YANDEX_GEO_KEY:
# обратное геокодирование (reverse_geocode) даёт регион/район → get_court_by_district → тот же суд.
# Без ключа используется только courts_nearest (ближайший по расстоянию) — возможны расхождения.
#
# Диагностика: YANDEX_GEO_KEY_SOURCE ∈ {GEOCODER, LOCATOR, NONE} — откуда взят ключ;
# YANDEX_GEO_KEY_ENV — имя переменной окружения, которая реально заполнила ключ.


def _resolve_yandex_geocoder_key() -> tuple[str, str, str]:
    """(ключ, GEOCODER|LOCATOR|NONE, имя_переменной_источника)."""
    for env_name in ("YANDEX_GEO_KEY", "YANDEX_GEOCODER_API_KEY"):
        v = (os.getenv(env_name) or "").strip()
        if v:
            return v, "GEOCODER", env_name
    for env_name in ("YANDEX_LOCATOR_API_KEY", "YANDEX_LOCATOR_KEY"):
        v = (os.getenv(env_name) or "").strip()
        if v:
            return v, "LOCATOR", env_name
    return "", "NONE", ""


YANDEX_GEO_KEY, YANDEX_GEO_KEY_SOURCE, YANDEX_GEO_KEY_ENV = _resolve_yandex_geocoder_key()

# DaData — подсказки суда по адресу (опционально)
DADATA_TOKEN = (os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or "").strip()
DADATA_TOKEN_ENV = (
    "DADATA_TOKEN"
    if (os.getenv("DADATA_TOKEN") or "").strip()
    else ("DADATA_API_KEY" if (os.getenv("DADATA_API_KEY") or "").strip() else "")
)
DADATA_TOKEN_SOURCE = "TOKEN" if DADATA_TOKEN_ENV == "DADATA_TOKEN" else ("API_KEY" if DADATA_TOKEN_ENV == "DADATA_API_KEY" else "NONE")

# Secret: в .env иногда пишут DADATA_SECRET_KEY — поддерживаем и его
DADATA_SECRET = (os.getenv("DADATA_SECRET") or os.getenv("DADATA_SECRET_KEY") or "").strip()
DADATA_SECRET_ENV = (
    "DADATA_SECRET"
    if (os.getenv("DADATA_SECRET") or "").strip()
    else ("DADATA_SECRET_KEY" if (os.getenv("DADATA_SECRET_KEY") or "").strip() else "")
)

# Таймауты и лимиты
GEOCODE_TIMEOUT = int(os.getenv("COURT_LOCATOR_GEO_TIMEOUT", "10"))
# SKIP_EXTERNAL_GEO=1|true|yes|on — не вызывать внешний геокод в шаге C unified_jurisdiction (см. core._step_c_spatial).
NEAREST_RADIUS_KM = float(os.getenv("COURT_LOCATOR_RADIUS_KM", "5.0"))

# Кеширование (опционально): при заданном REDIS_URL — Redis, иначе in-memory
REDIS_URL = os.getenv("REDIS_URL", "").strip()
COURT_LOCATOR_CACHE_TTL = int(os.getenv("COURT_LOCATOR_CACHE_TTL", "3600"))

# Обновление данных (updater)
COURT_DATA_UPDATE_URL = os.getenv("COURT_DATA_UPDATE_URL", "").strip()
COURT_DATA_UPDATE_URL_FALLBACK = os.getenv("COURT_DATA_UPDATE_URL_FALLBACK", "").strip()
UPDATE_SCHEDULE = os.getenv("UPDATE_SCHEDULE", "0 3 * * *")  # cron-подобно: каждый день в 3:00

# NextGIS Map API (api.mapdev.io) — границы судебных участков
# Ресурс 137: GeoJSON; ресурс 138: TMS для отображения на карте
NEXTGIS_BASE_URL = os.getenv("NEXTGIS_BASE_URL", "https://api.mapdev.io").strip()
NEXTGIS_BOUNDARIES_RESOURCE_ID = int(os.getenv("NEXTGIS_BOUNDARIES_RESOURCE_ID", "137"))
NEXTGIS_EXTRA_RESOURCE_IDS = [
    int(x.strip()) for x in (os.getenv("NEXTGIS_EXTRA_RESOURCE_IDS") or "").split(",") if x.strip()
]
NEXTGIS_MAP_TMS_URL = os.getenv(
    "NEXTGIS_MAP_TMS_URL",
    "https://api.mapdev.io/api/component/render/tile?resource=138&nd=204&z={z}&x={x}&y={y}",
).strip()

# PostGIS: прямое подключение (если есть свой экземпляр с данными NextGIS)
# При заданном NGW_POSTGIS_DSN — sync_nextgis_to_postgis() загружает GeoJSON в PostGIS
NGW_POSTGIS_DSN = os.getenv("NGW_POSTGIS_DSN", "").strip()


def use_postgis_for_spatial_search() -> bool:
    """
    Использовать PostGIS для поиска по полигонам (court_districts / world_courts_zones).

    Явно: COURTS_SPATIAL_BACKEND=postgis|sqlite|0|1 (рекомендуется, не путается с БД списка судов).

    Устаревшее: COURTS_DB_BACKEND=postgis — то же самое для пространственного слоя
    (репозиторий судов parser при этом остаётся sqlite, если не задан postgres).
    """
    v = (os.getenv("COURTS_SPATIAL_BACKEND") or "").strip().lower()
    if v in ("postgis", "1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off", "sqlite", "none"):
        return False
    return (os.getenv("COURTS_DB_BACKEND") or "").strip().lower() == "postgis"


def api_env_diagnostics() -> dict[str, str]:
    """
    Сводка для отладки: класс ключа Яндекса (GEOCODER/LOCATOR/NONE), имя переменной и подсказки по частым ошибкам .env.
    Не содержит самих секретов.
    """
    out: dict[str, str] = {
        "yandex_geo_key_source": YANDEX_GEO_KEY_SOURCE,
        "yandex_geo_key_env": YANDEX_GEO_KEY_ENV or "-",
        "dadata_token_source": DADATA_TOKEN_SOURCE,
        "dadata_token_env": DADATA_TOKEN_ENV or "-",
        "dadata_secret_env": DADATA_SECRET_ENV or "-",
    }
    if YANDEX_GEO_KEY_SOURCE == "NONE" and (os.getenv("YANDEX_API_KEY") or "").strip():
        out["yandex_env_hint"] = (
            "Задан YANDEX_API_KEY, но HTTP API Геокодера (geocode-maps.yandex.ru) читает только "
            "YANDEX_GEO_KEY / YANDEX_GEOCODER_API_KEY / YANDEX_LOCATOR_API_KEY."
        )
    else:
        out["yandex_env_hint"] = ""
    if DADATA_TOKEN and not DADATA_SECRET:
        out["dadata_env_hint"] = (
            "Секрет DaData не задан — suggest/court обычно работает; Profile API (баланс) нуждается в DADATA_SECRET или DADATA_SECRET_KEY."
        )
    else:
        out["dadata_env_hint"] = ""
    return out
