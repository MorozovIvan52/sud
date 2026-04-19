# Сервис подсудности: бесплатные источники и запуск

Реализация соответствует техническим требованиям к сервису-конкуренту с опорой **только на бесплатные** источники данных и API.

## 1. Бесплатные источники данных (без коммерческих API)

### 1.1. Локальная БД судов (основа)

- **parser/courts.sqlite** — список мировых судов (регион, район, участок, адрес, индекс, координаты). Заполняется:
  - из открытых данных (CSV по регионам с сайтов судов);
  - из seed-данных для разработки (`courts_db.seed_example_data()`);
  - один раз можно выгрузить список через DaData (бесплатный лимит) и дальше обновлять вручную из открытых источников.
- **parser/court_districts.sqlite** — границы участков (GeoJSON-полигоны). Загружаются из GeoJSON файлов (см. ниже).

Никакой «кражи» коммерческих баз: используем только то, что получено легально (открытые данные, свой парсинг, бесплатные лимиты).

### 1.2. Геокодирование (бесплатно)

- **Nominatim (OpenStreetMap)** — используется автоматически в court_locator при отсутствии ключа Yandex. Бесплатно, с лимитами по количеству запросов в секунду (1 req/s без указания своего User-Agent). Подходит для разработки и небольшой нагрузки.
- **Yandex Geocoder** — опционально (нужен ключ). Улучшает точность по России; при его отсутствии сервис полностью работает на Nominatim.

### 1.3. Откуда брать границы участков (GeoJSON) бесплатно

- **NextGIS Map API** — [api.mapdev.io](https://api.mapdev.io/resource/138) — границы судебных участков (Россошанский судебный район, Воронежская обл., 186 участков). GeoJSON: `GET /api/resource/137/geojson`. TMS для карты: `.../tile?resource=138&nd=204&z={z}&x={x}&y={y}`. Загрузка: `load_nextgis_to_db()` или `POST /api/nextgis-load`. Дополнительно: `fetch_resource_meta()`, `fetch_children()`, `discover_geojson_resources()` — обход ресурсов; `load_nextgis_from_resources()` — загрузка из нескольких ID; `sync_nextgis_to_postgis()` — синхронизация в PostGIS (NGW_POSTGIS_DSN или PG_DSN).
- **Официальные сайты судов** — разделы «Территориальная подсудность», карты участков. Парсинг или ручная выгрузка в GeoJSON.
- **OpenStreetMap** — теги административных границ (admin_level и др.). Экспорт в GeoJSON (например, через Overpass API или готовые датасеты).
- **Humanitarian Data Exchange (HDX)** — [data.humdata.org](https://data.humdata.org) — административные границы РФ в формате GeoJSON.
- **GitHub** — репозитории с GeoJSON по регионам России (например, поиск по "russia geojson").
- **ГАС «Правосудие»** — официальные данные; прямой массовый доступ к границам участков через открытое API ограничен (используется через коммерческих посредников или ручной сбор).

Собранные GeoJSON загружаются в court_districts через `load_geojson_to_db()` или DataUpdater. NextGIS — через `load_nextgis_to_db()`.

### 1.4. Что не подключаем (только бесплатные)

- Коммерческие API подсудности (Подсудность.рф, SmartLegalData, Nodul, Debex и т.п.) в проект **не добавляются**.
- DaData — по желанию можно отключить (не задавать DADATA_TOKEN); поиск пойдёт по району из адреса и по Nominatim/Yandex.

## 2. Запуск REST API

### 2.1. Установка

```bash
pip install -r requirements.txt
# В requirements.txt уже есть fastapi, uvicorn
```

### 2.2. Переменные окружения (.env)

В корне проекта есть файл **`.env.example`** — скопируйте в `.env` и при необходимости отредактируйте.

Минимально для работы **без платных ключей**:

- Не задавать `DADATA_TOKEN` — тогда по адресу используется парсинг района + геокодер (Nominatim при отсутствии Yandex).
- Не задавать `YANDEX_GEO_KEY` — геокодирование только через Nominatim (бесплатно).
- Опционально: `REDIS_URL` — кеш в Redis; без него — in-memory кеш.

Пути к БД по умолчанию: `parser/courts.sqlite`, `parser/court_districts.sqlite`.

### 2.3. Запуск сервера

Из корня проекта:

```bash
python run_court_locator_api.py
```

Или напрямую через uvicorn:

```bash
uvicorn court_locator.api:app --host 0.0.0.0 --port 8000
```

С автоперезагрузкой:

```bash
python -m uvicorn court_locator.api:app --reload --host 0.0.0.0 --port 8000
```

Документация API (OpenAPI): http://localhost:8000/docs

### 2.4. Примеры запросов

**По координатам (WGS84):**

```bash
curl -X POST "http://localhost:8000/api/find-jurisdiction" \
  -H "Content-Type: application/json" \
  -d "{\"lat\": 55.7558, \"lng\": 37.6173}"
```

**По адресу:**

```bash
curl -X POST "http://localhost:8000/api/find-jurisdiction-by-address" \
  -H "Content-Type: application/json" \
  -d "{\"address\": \"г. Москва, ул. Тверская, д. 15\"}"
```

**Экспорт границ (GeoJSON):**

```bash
curl "http://localhost:8000/api/boundaries"
```

**Метрики времени отклика:**

```bash
curl "http://localhost:8000/api/metrics"
```

**Проверка доступности:**

```bash
curl "http://localhost:8000/api/health"
```

## 3. Соответствие техническим требованиям

| Требование | Реализация |
|------------|------------|
| Определение по GPS-координатам, WGS84 | `POST /api/find-jurisdiction` (lat, lng) |
| Определение по текстовому адресу | `POST /api/find-jurisdiction-by-address` (Yandex или Nominatim) |
| Время отклика по координатам < 100 мс | Кеш (Redis/in-memory), метрики в `/api/metrics` |
| Время отклика по адресу < 500 мс | Зависит от геокодера; кеш по адресу снижает повторные запросы |
| Экспорт границ в GeoJSON | `GET /api/boundaries` — FeatureCollection |
| REST API, документация | FastAPI, OpenAPI `/docs` |
| Только бесплатные источники | БД судов + Nominatim; Yandex/DaData опционально |
| Актуальность данных | Загрузка GeoJSON, `scheduled_update()` из своего URL (без коммерческих API) |

## 4. Первоначальная загрузка данных

1. Заполнить **courts** (список судов): CSV с колонками region, district, section_num, court_name, address, postal_index, coordinates — импорт через `parser/import_courts.py` или seed для теста.
2. При наличии GeoJSON с границами участков — загрузить в court_districts:  
   `from court_locator import load_geojson_to_db; load_geojson_to_db("path/to/courts.geojson")`
3. Запустить API и проверить `/api/health` и `/api/find-jurisdiction` на известных координатах.

После этого сервис работает автономно на бесплатных источниках; коммерческие API не подключаются.
