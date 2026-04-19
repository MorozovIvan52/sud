# Court Verification API

Отдельное приложение для верификации границ судебных участков (синхронный FastAPI + SQLAlchemy + PostGIS).

## Шаг 1. Подготовка окружения

```bash
cd court-verification
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate      # Linux/Mac
pip install -r requirements.txt
```

## Шаг 2. API-ключи

**Яндекс.Карты:** [Кабинет разработчика](https://developer.tech.yandex.ru/) → подключить «JavaScript API и HTTP Геокодер» → скопировать API-ключ.

**DaData:** [dadata.ru](https://dadata.ru/) → личный кабинет → API → скопировать токен.

**PostgreSQL + PostGIS:** установить PostgreSQL с компонентом PostGIS, создать БД и выполнить `CREATE EXTENSION postgis;`

## Шаг 3. Переменные окружения

Создайте `.env` в папке `court-verification` (или в корне parserSupreme):

```env
YANDEX_API_KEY=ваш_ключ_яндекса
DADATA_TOKEN=ваш_токен_dadata
DATABASE_URL=postgresql://postgres:your_password@localhost/court_boundaries
```

Файл `.env` добавлен в `.gitignore`.

## Шаг 4. Запуск

```bash
uvicorn main:app --reload
```

Документация: http://localhost:8000/docs

## Проверка API-ключей

**Яндекс.Карты:**
```bash
curl "https://geocode-maps.yandex.ru/1.x/?apikey=ВАШ_КЛЮЧ&geocode=Москва&format=json"
```

**DaData** (подсказки по адресу):
```bash
curl -X POST "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address" \
  -H "Content-Type: application/json" \
  -H "Authorization: Token ВАШ_ТОКЕН" \
  -d "{\"query\": \"Москва Тверская\"}"
```

## API

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/v1/find-court` | Поиск суда по координатам (тело: `latitude`, `longitude`) |
| POST | `/api/v1/courts/` | Создать суд с геометрией |
| GET | `/api/v1/courts/{court_id}` | Получить суд |
| POST | `/api/v1/location/` | Суд по координатам (ответ с полем `found`) |
| POST | `/api/v1/verification/start` | Запуск верификации суда |
| POST | `/api/v1/verification/validate-geometry` | Проверка геометрии (BoundaryValidator) |

**Пример запроса к `/api/v1/find-court`:**
```json
{"latitude": 55.7558, "longitude": 37.6173}
```

## Структура

- `app/database.py` — движок и сессия БД
- `app/models.py` — Court, VerificationResult, VerificationHistory
- `app/schemas.py` — Pydantic-модели
- `app/crud.py` — get_court_by_location (ST_Within), create_court
- `app/services/boundary_validator.py` — Shapely: validate_geometry, point_within_polygon, calculate_distance
- `app/services/verification_engine.py` — запуск верификации
- `app/api/endpoints.py` — эндпоинты

Таблицы создаются при старте (`Base.metadata.create_all`). Для продакшена используйте миграции.
