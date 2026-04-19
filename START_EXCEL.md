# Excel → мировой суд: быстрый старт

**Полное руководство для новичка** (как устроена программа, что вводить, что получать, типичные сбои): [docs/USER_GUIDE_BEGINNER_RU.md](docs/USER_GUIDE_BEGINNER_RU.md).

## 0. Первый запуск после клонирования репозитория

Файлы `*.sqlite` **не в git** (см. `.gitignore`). Создайте пустые базы со схемой:

```bash
python scripts/bootstrap_local_databases.py
```

Для быстрой проверки с 2 демо-судами (Москва/СПб): добавьте `--seed`.  
Полный список судов — импорт CSV по [docs/howto_fill_courts_db.md](docs/howto_fill_courts_db.md) или `cd parser && python import_courts.py`.

## 1. Установка (один раз)

```bash
cd путь/к/parserSupreme
pip install -r requirements.txt
python -m spacy download ru_core_news_sm
```

## 2. Ключи API

1. Скопируйте `env.quickstart.example` в файл `.env` в **корне** проекта.
2. Вставьте ключи:
   - **YANDEX_GEO_KEY** — [API Геокодера](https://developer.tech.yandex.ru/) (геокодирование адреса).
   - **DADATA_TOKEN** — [DaData](https://dadata.ru/) (подсказка суда по адресу, ФИАС; **обратное геокодирование и прямой геокод при 403 у Яндекса**).

Без ключей сервис попытается работать на бесплатных источниках (Nominatim, локальная БД) — точность ниже. Рекомендуется задать оба: при ошибке **403** HTTP Геокодера Яндекса цепочка автоматически переходит на DaData.

## 3. Файл Excel

Обязательная колонка: **Адрес** (или `address`, или «Адрес регистрации»).  
Желательно: **ФИО**. Опционально: **Сумма** (для госпошлины), **Широта** / **Долгота**.

Создать пример:

```bash
python run_excel_jurisdiction.py --template шаблон.xlsx
```

## 4. Запуск

```bash
python run_excel_jurisdiction.py ваш_файл.xlsx
```

Результат: рядом с исходником появится `ваш_файл_подсудность.xlsx` (все поля + лист **Сводка** с судом).

Свой путь к результату:

```bash
python run_excel_jurisdiction.py ваш_файл.xlsx -o результат.xlsx
```

## 5. Через веб-API (Swagger)

```bash
python run_court_locator_api.py
```

Откройте http://127.0.0.1:8000/docs → **POST /api/v1/batch-process** → загрузите файл, параметр `format=xlsx` — скачается готовый Excel.

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `COURTS_DB_BACKEND=sqlite` (по умолчанию) | Список судов из `parser/courts.sqlite` |
| `COURTS_DB_BACKEND=postgres` | Список судов из PostgreSQL (см. документацию parser) |
| **`COURTS_SPATIAL_BACKEND=postgis`** + **`PG_DSN`** | Полигоны в PostGIS (`court_districts` / GISmap `world_courts_zones`) — **рекомендуемая** переменная |
| `COURTS_DB_BACKEND=postgis` | Устаревший синоним включения PostGIS для полигонов (совместимость) |

При `postgis` список судов остаётся в SQLite, пока вы явно не включили `COURTS_DB_BACKEND=postgres` для parser.

## Точность

Подсудность зависит от полноты **адреса**, **ключей API** и наличия **полигонов** участков в `parser/court_districts.sqlite` или PostGIS. Для максимальной точности по координатам добавьте колонки широты и долготы (WGS84).
