# Интеграция модуля court_locator

Модуль `court_locator` определяет мировой суд по адресу или координатам и использует **все API проекта**.

**Пошаговый запуск только на бесплатных источниках:** см. [court_locator_quickstart.md](court_locator_quickstart.md).  
В корне проекта: `.env.example` (шаблон переменных для бесплатного режима), `run_court_locator_api.py` (запуск API).

## Структура (по плану исследования)

```
court_locator/
├── __init__.py
├── config.py          # YANDEX_GEO_KEY, DADATA_TOKEN, REDIS_URL, пути к БД, COURT_DATA_UPDATE_URL
├── cache.py           # Кеш результатов (Redis при REDIS_URL, иначе in-memory)
├── gps_handler.py     # Yandex Geocoder → (lat, lon); reverse_geocode; fallback Nominatim
├── address_parser.py  # Парсинг адреса (регион, район); при наличии — parser.address_parser
├── court_matcher.py   # Полигоны (shapely, опционально R-tree) → район по координатам → ближайший суд
├── database.py        # court_districts (границы, last_updated) + courts (parser)
├── data_loader.py     # Загрузка GeoJSON в court_districts (load_geojson_to_db)
├── updater.py         # DataUpdater: update_from_api, update_from_geojson_file; scheduled_update
├── utils.py
├── main.py            # CourtLocator
└── test_court_locator.py
```

## Используемые API проекта

| API | Переменная | Назначение |
|-----|------------|------------|
| Yandex Geocoder | `YANDEX_GEO_KEY` / `YANDEX_GEOCODER_API_KEY` | Геокодирование адреса; **для совпадения с Parser по координатам обязателен** (reverse_geocode → район → get_court_by_district; без ключа используется только courts_nearest — возможны расхождения) |
| DaData | `DADATA_TOKEN` | Подсказка суда по адресу (используется после поиска по району из адреса) |
| БД судов | `parser/courts.sqlite` | Поиск по району, ближайший суд по coordinates |
| БД с координатами | `parser/courts_geo.sqlite` | Ближайший суд по (lat, lon) |
| Полигоны участков | `parser/court_districts.sqlite` | Точка в полигоне (shapely) |
| Кеш | `REDIS_URL` (опционально) | При заданном — Redis; иначе in-memory. TTL: `COURT_LOCATOR_CACHE_TTL` (сек, по умолчанию 3600). |

## Использование в коде

```python
from court_locator import CourtLocator

finder = CourtLocator(use_cache=True)  # кеш по умолчанию вкл. (Redis или in-memory)

# По адресу (сначала БД по району из адреса — как Parser, затем DaData, затем геокодер)
court = finder.locate_court(address="г. Москва, ул. Тверская, д. 15")

# По координатам (полигоны → reverse_geocode → БД по району → ближайший суд; для совпадения с Parser нужен YANDEX_GEO_KEY)
court = finder.locate_court(lat=55.7558, lng=37.6173)

if court:
    print(court["court_name"], court["address"], court["source"])
finder.close()
```

## Интеграция в parser (jurisdiction)

Текущая логика подсудности в `parser/jurisdiction.py` уже использует DaData и Yandex Geocoder + БД. При желании можно вызывать `CourtLocator` как ещё один источник (например, если появятся полигоны участков):

```python
# В jurisdiction.py при необходимости:
try:
    from court_locator import CourtLocator
    finder = CourtLocator()
    finder.db.courts_path = Path(__file__).parent / "courts.sqlite"
    court = finder.locate_court(address=address)
    if court and court.get("court_name"):
        return _court_row_to_result(court, "court_locator")
finally:
    finder.close()
```

## Зависимости

В `requirements.txt`: `requests`, `shapely`, `schedule`, `geopy`, `python-dotenv`. Опционально: `rtree` — для R-tree пространственного индекса (ускорение поиска по полигонам при большом числе участков).

## Загрузка данных из GeoJSON

Первоначальная загрузка или обновление из файла:

```python
from court_locator import load_geojson_to_db

# Загрузить участки из GeoJSON (Feature или FeatureCollection)
count = load_geojson_to_db("path/to/court_data.geojson", clear_before=True)
print(f"Загружено записей: {count}")
```

Формат GeoJSON: `properties` — id, district_number, region, address, phone, schedule, judge_name; `geometry` — Polygon с coordinates.

## Обновление данных из API (DataUpdater)

```python
from court_locator.updater import DataUpdater, scheduled_update

updater = DataUpdater()
# Обновление из API (JSON или GeoJSON FeatureCollection)
if updater.update_from_api("https://api.podsubnost.rf/courts"):
    print("Данные обновлены")

# Или по расписанию (задать COURT_DATA_UPDATE_URL и COURT_DATA_UPDATE_URL_FALLBACK в .env)
schedule.every().day.at("03:00").do(scheduled_update)
```

В `.env`: `COURT_DATA_UPDATE_URL`, `COURT_DATA_UPDATE_URL_FALLBACK` (опционально).

## Обновление через CourtLocator

Если данные уже в памяти (список словарей с boundaries):

```python
finder = CourtLocator()
finder.update_court_data(list_of_districts)
finder.close()
```

## Кеширование

По умолчанию `CourtLocator(use_cache=True)` кеширует результаты поиска:

- При заданном **REDIS_URL** в окружении или `.env` — кеш в Redis (ключи `court:lat:lng` и `court:addr:hash`), TTL из `COURT_LOCATOR_CACHE_TTL` (по умолчанию 3600 сек).
- Без Redis — in-memory кеш (до 10000 записей), подходит для одного процесса.

Отключение: `CourtLocator(use_cache=False)`.

## Сравнение с реализацией FastAPI + PostGIS + Redis

Подход «FastAPI + PostgreSQL/PostGIS + Redis + Nominatim» (отдельный микросервис) и наш модуль решают одну задачу разными средствами:

| Аспект | Наш court_locator | Вариант FastAPI + PostGIS + Redis |
|--------|-------------------|-----------------------------------|
| БД | SQLite (courts + court_districts), без сервера | PostgreSQL + PostGIS (ST_Contains, GIST-индекс) |
| Геокодер | Yandex (основной) + Nominatim (резерв) | В примере — только Nominatim |
| Кеш | Опционально Redis или in-memory (встроено в CourtLocator) | Redis для ответов API |
| API | Библиотека (Python), вызов `locate_court()` | REST POST /api/find-jurisdiction |
| Интеграция с Parser | Одна БД courts, один парсер адреса — совпадение суда по району | Отдельный сервис, нужна синхронизация данных |

Наш модуль уже даёт: поиск по району (как Parser), полигоны (Shapely), опциональный R-tree, загрузка GeoJSON, обновление из API, кеширование (Redis или memory). При необходимости REST API можно добавить поверх существующего кода:

```python
# Пример обёртки FastAPI (при необходимости вынести в отдельный сервис)
from fastapi import FastAPI
from court_locator import CourtLocator

app = FastAPI()
locator = CourtLocator(use_cache=True)

@app.post("/api/find-jurisdiction")
def find_jurisdiction(coords: dict):
    court = locator.locate_court(lat=coords.get("lat"), lng=coords.get("lng"))
    if not court:
        return {"success": False, "detail": "Юрисдикция не найдена"}
    return {"success": True, "address": court.get("address"), "jurisdiction": court}
```

Миграция на PostGIS имеет смысл при больших объёмах полигонов и необходимости сложных пространственных запросов; для текущей задачи SQLite + Shapely достаточно.

## Связка с GISmap (`GISmap/`)

В репозитории две «ветки» геоданных:

| Компонент | Назначение | Хранилище полигонов |
|-----------|------------|---------------------|
| **Основной парсер** (`court_locator`, `batch_processing`, `unified_jurisdiction`) | Подсудность, 45 полей, SQLite-полигоны | `parser/court_districts.sqlite` → колонка `boundaries` (GeoJSON), либо PostGIS-таблица `court_districts` (`boundary`) после `migrations/001_postgis_court_districts.sql` / NextGIS sync |
| **GISmap** | Карта, загрузка законов, построение зон, API `match_court` | PostGIS: `world_courts`, `world_courts_zones.geom`, `court_addresses`, `court_boundaries_*` |

**Проблема до интеграции:** схемы разные (`court_districts` vs `world_courts_zones`), один и тот же `PG_DSN` без моста не подхватывал полигоны GISmap.

**Сейчас:** при **`COURTS_SPATIAL_BACKEND=postgis`** (или устаревшем `COURTS_DB_BACKEND=postgis`) модуль `court_locator/postgis_adapter.py` сначала ищет точку в `court_districts`, затем — в `world_courts_zones` + `world_courts` (источник: `postgis_gismap_zones`). Отключить второй шаг: `POSTGIS_SKIP_GISMAP_ZONES=1`.

**Рекомендуемая схема деплоя:** один экземпляр PostgreSQL/PostGIS; либо (а) наполнять `court_districts` из экспорта GISmap/NextGIS, либо (б) держать только схему GISmap и полагаться на fallback в `postgis_adapter`. Для батча без PostGIS по-прежнему используется SQLite + Shapely.

**Дублирование кода/сервисов (навести порядок постепенно):** два FastAPI (корневой `court_locator/api.py` и `GISmap/backend`), два набора геокодеров/лимитов, отдельно `jurisdiction_service` и `court-verification` — имеет смысл выбрать один публичный API и единый слой геокодирования, остальное оставить как библиотеки или внутренние сервисы.

## Тест

Из корня проекта:

```bash
python -m court_locator.test_court_locator
```

Сводный тест (Parser + Court locator + согласованность): `python tests_run.py`

## REST API и только бесплатные источники

REST API сервиса: модуль [court_locator/api.py](../court_locator/api.py). Запуск: `uvicorn court_locator.api:app --host 0.0.0.0 --port 8000`. Эндпоинты: `POST /api/find-jurisdiction` (координаты), `POST /api/find-jurisdiction-by-address` (адрес), `GET /api/boundaries` (GeoJSON границ), `GET /api/metrics` (время отклика).

**Использование только бесплатных источников** (без коммерческих API подсудности): см. [court_locator_free_sources.md](court_locator_free_sources.md) — какие данные откуда брать, как запускать сервис без DaData/Yandex (Nominatim), откуда брать границы в формате GeoJSON.
