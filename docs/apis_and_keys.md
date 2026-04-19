# API и ключи проекта ПарсерСуд Pro

Список внешних API и переменных окружения. Где брать ключи и что нужно для полного запуска поиска.

**Определение подсудности по адресу (заключение):** [jurisdiction_conclusion.md](jurisdiction_conclusion.md)

**Реестр документации → код:** [docs_implementation_registry.md](docs_implementation_registry.md)

### Поля ответа API `find_court` (`UnifiedJurisdictionCore`)

Помимо `success`, `court`, `unified_address`, `resolution_steps` в словаре `FindCourtResponse.to_dict()` для **текстового адреса** (когда сработало взвешенное голосование источников) добавляются:

| Поле | Описание |
|------|-----------|
| `confidence_score` | Уверенность по сумме весов победившего ключа (ограничение сверху 2.0, одна цифра после запятой); пороги настраиваются через `JURISDICTION_MIN_CONFIDENCE_SUM`, `JURISDICTION_DISAGREEMENT_CONFIDENCE`. |
| `resolution_reason` | Текстовая причина выбора (например, «попадание в полигон + совпадение улицы», «совпадение улицы и диапазона домов»). |
| `needs_manual_review` | `true`, если по правилам голосования или геометрии нужна ручная проверка. |
| `source_votes` | Массив голосов источников: `source`, `court_key`, `weight`, опционально `court_id` — для отладки и мониторинга. |
| `selected_court_id` | Номер участка из meta голоса победителя, если удалось вывести из `section_num`. |

Идентификатор суда в основном теле ответа по-прежнему в `court` (в т.ч. `section_num`, `court_name`). Пороги и имена источников полигона: `JURISDICTION_POLYGON_SOURCE_NAMES` (по умолчанию `polygon,postgis`).

---

## 1. Обязательные для «поиска по ИП и подсудности»

| API / сервис | Переменные окружения | Где взять ключ | Используется в коде |
|--------------|----------------------|----------------|---------------------|
| **DaData** (суды по адресу) | `DADATA_TOKEN`, для Profile API также `DADATA_SECRET` | [dadata.ru](https://dadata.ru) → Регистрация → API → Token + Secret. Бесплатный тариф: 10k запросов/день | `dadata_api.py`, `dadata_integration.py`, `jurisdiction.py`, `ultimate_parser.py`, `bot.py` |

**В этом проекте оба ключа DaData уже прописаны в `.env`** (DADATA_TOKEN и DADATA_SECRET) — подсказки судов и Profile API (баланс, статистика) готовы к работе.

**DaData Profile API** (баланс и лимиты): `GET https://dadata.ru/api/v2/profile/balance`, `/api/v2/stat/daily`, `/api/v2/version`. Заголовки: `Authorization: Token <DADATA_TOKEN>`, `X-Secret: <DADATA_SECRET>`. В коде: `dadata_api.get_balance()`, `get_daily_stats()`, `get_versions()`. Скрипт «всё полезное из DaData»: `parser/dadata_fetch_all.py` (баланс, статистика, версии; опция `--dump-courts` — выгрузка мировых судов в CSV). Спецификация: `docs/dadata_profile_api.yml`.
| **БД судов** (локальная) | `COURTS_DB_BACKEND=sqlite` (по умолчанию) или `postgres` | Не нужен ключ для SQLite. Файл БД создаётся автоматически. Заполнение: CSV через `import_courts.py` или выгрузка из DaData — `parser/dump_magistrates_to_csv.py` (см. docs/court_sources_db.md) | `jurisdiction.py`, `courts_sqlite.py`, `courts_postgres.py`, `import_courts.py` |
| **ГАС Правосудие** (поиск по ФИО) | Не требуется | Парсинг HTML по bsr.sudrf.ru. Без ключа; при капче — см. раздел «Капча» | `sudrf_scraper.py`, `anti_block.py`, `jurisdiction.py` |

**Минимум для старта:** DaData уже подключена — **используем наши ключи из `.env`** (DADATA_TOKEN, DADATA_SECRET). **БД судов уже заполнена** (выгрузка из DaData по **всем 85 субъектам РФ** выполнена: в `parser/courts.sqlite` загружено **1640** мировых судов из `parser/data/magistrates_dadata.csv`). Этого достаточно для проверки подсудности по адресу и паспорту. Чтобы обновить или расширить список: [docs/howto_fill_courts_db.md](howto_fill_courts_db.md). Кратко: (1) **через наши ключи DaData** — `cd parser`, `python dump_magistrates_to_csv.py` (или `python dadata_fetch_all.py --dump-courts`), затем `python -c "from import_courts import import_courts_from_csv; from pathlib import Path; import_courts_from_csv(Path('data/magistrates_dadata.csv'))"`; (2) **свой CSV** — формат и порталы в howto; (3) **тест** — `courts_db.init_db()` + `seed_example_data()`.

### Обход или замена DaData

DaData в проекте используется для: (1) **подсказки суда по адресу** (`find_court_by_address` в `jurisdiction.py`, `ultimate_parser.py`); (2) **Profile API** — баланс и статистика (`dadata_fetch_all.py`); (3) **выгрузка списка мировых судов** по регионам (`dump_magistrates_to_csv.py`) для заполнения БД.

**Варианты без DaData:**

| Вариант | Описание |
|--------|----------|
| **Своя цепочка «адрес → суд»** | Геокодер **Yandex** (`YANDEX_GEO_KEY`) + локальная БД судов с координатами (`courts_geo.sqlite`) или по региону из геокодера → поиск в `courts.sqlite`. Реализовано в `geo_court_parser.py` (YandexGeoParser). В `jurisdiction.py` при отсутствии `DADATA_TOKEN` можно использовать этот путь (адрес → геокод → ближайший суд или регион → суд из БД). |
| **Только БД судов + паспорт/адрес** | Не использовать «суд по адресу» через API. Подсудность: код подразделения паспорта + район из парсера адреса → `get_court_by_district()` в БД; при необходимости — парсинг ГАС по ФИО; иначе fallback. Для этого достаточно заполненной БД судов и **не нужен ни DaData, ни Yandex Geocoder**. |
| **Заполнение БД судов без DaData** | Список мировых судов для БД: (1) **открытые данные** — CSV по регионам (см. [howto_fill_courts_db.md](howto_fill_courts_db.md), способ 2); (2) **seed** — тестовые 2 суда для разработки; (3) один раз выгрузить из DaData и дальше обновлять из открытых источников. |
| **Другие провайдеры** | Прямых аналогов «подсказки суда по адресу» с публичным API в РФ мало. Можно использовать любой геокодер (Yandex, 2GIS, Google) для получения региона/координат по адресу и затем выбирать суд из своей БД по региону или по ближайшей точке. |

**Итог:** DaData можно не использовать: задать только `YANDEX_GEO_KEY` и заполненную БД судов (в т.ч. `courts_geo.sqlite` для геопоиска) — в коде при отсутствии DaData будет использоваться геопарсер + БД. Либо вообще убрать шаг «суд по адресу» и опираться на паспорт, парсер адреса и ГАС по ФИО.

---

## 2. ФССП (исполнительные производства)

| API / сервис | Переменные окружения | Где взять ключ | Используется в коде |
|--------------|----------------------|----------------|---------------------|
| **ФССП (официальный)** | `FSSP_API_KEY` (или `FSSP_TOKEN`); опционально `FSSP_API_BASE`, `FSSP_TIMEOUT`, `FSSP_MAX_REQUESTS_PER_MINUTE` | Официальный API ФССП (банк данных исполнительных производств). Доступ — по договору с ФССП; ключ хранится во внешней конфигурации (.env/секреты), в код не коммитится. Публичного REST с key= без договора нет; коммерческие прокладки — [parser-api](https://www.parser-api.com/fssprus-ru), apiportal и др. [newtechaudit: API и ФССП](https://newtechaudit.ru/api-i-fssp-kak-eto-rabotaet/) | Клиент API: `parser/fssp_client.py` (`search_by_ip`, `verify_ip_exists`). Конфиг: `parser/fssp_config.py` (`FSSPConfig`). Веб-парсинг: `parser/fssp_web_parser.py` (`FSSPWebParser`). Вызывают: `supreme_turbo.py`, `supreme_parser.py`, `anti_hallucination.py` |

**Важно.** В проекте используются URL вида `https://api.fssp.gov.ru/ip/{ip}` и `https://api.fssp.gov.ru/executions/{ip}` — это, с высокой вероятностью, демо‑эндпоинты или внутренний/нестабильный API, не предназначенный для открытого массового использования. Для легального и устойчивого доступа к данным ФССП необходимо отдельно согласовать подключение к их сервисам (ГИС ГМП, СМЭВ и др.) через официальный сайт `fssp.gov.ru` или уполномоченных операторов. После получения доступа параметры авторизации (ключ/токен) должны храниться во внешней конфигурации (например, `FSSP_API_KEY` или `FSSP_TOKEN` в `.env`/секретах) и подставляться в заголовки или параметры запросов во всех модулях, работающих с ФССП (`supreme_turbo.py`, `supreme_parser.py`, `anti_hallucination.py`), без жёсткого вшивания в код. [habr](https://habr.com/ru/articles/648321/)

**Парсинг открытых данных ФССП** (альтернатива API — веб-интерфейс fssp.gov.ru/iss/ip/): инструкция и реализация в коде — [fssp_parsing_open_data.md](fssp_parsing_open_data.md), класс `FSSPWebParser` в `parser/fssp_web_parser.py`. **Настройка и легальный доступ** (конфиг в коде: `parser/fssp_config.py`, СМЭВ, ГИС ГМП, тестирование) — [fssp_legal_integration.md](fssp_legal_integration.md). Интеграция с ГИС ГМП: подключение через СМЭВ или готовые API; требуется электронная подпись, учётные данные и защищённый канал связи.

---

## 3. Капча (ГАС Правосудие, суды)

| API / сервис | Переменные окружения | Где взять ключ | Используется в коде |
|--------------|----------------------|----------------|---------------------|
| **2Captcha** | `TWOCAPTCHA_API_KEY` или `CAPTCHA_API_KEY` | [2captcha.com](https://2captcha.com) — пополнение баланса, затем API key в личном кабинете | `anti_captcha.py`, `supreme_recaptcha.py` |
| **Anti-Captcha** | `ANTICAPTCHA_API_KEY` | [anti-captcha.com](https://anti-captcha.com) — регистрация, API key | `supreme_recaptcha.py` |
| **CapMonster** | `CAPMONSTER_API_KEY` | [capmonster.cloud](https://capmonster.cloud) | `supreme_recaptcha.py` |
| **Capsolver** (Turnstile) | `CAPSOLVER_API_KEY` | [capsolver.com](https://capsolver.com) — для Cloudflare Turnstile (если суды перейдут на него) | `supreme_recaptcha.py` (заглушка) |

Если капча на bsr.sudrf.ru мешает — задать один из ключей выше и использовать поток решения капчи в `supreme_recaptcha.py` / `anti_captcha.py`.

---

## 4. Арбитраж и банкротства

| API / сервис | Переменные окружения | Где взять ключ | Используется в коде |
|--------------|----------------------|----------------|---------------------|
| **КАД Арбитраж** (kad.arbitr.ru) | `KAD_ARBITR_USER_AGENT`, `KAD_ARBITR_PROXY`, `KAD_ARBITR_DELAY_MIN`, `KAD_ARBITR_DELAY_MAX` | Парсинг сайта, ключ API не нужен. User-Agent и прокси — по желанию, чтобы снизить блокировки | `kad_arbitr_parser.py`, `kad_arbitr_compliance.py` |
| **ЕФРСБ** (bankrot.fedresurs.ru) | Не требуется | Парсинг сайта; в проекте модуль-заглушка `efrsb_parser.py` | Планируется/заглушка |

---

## 4.5. NextGIS Map API (границы судебных участков)

| API / сервис | Переменные окружения | Где взять | Используется в коде |
|--------------|----------------------|-----------|---------------------|
| **NextGIS Map** (api.mapdev.io) | `NEXTGIS_BASE_URL`, `NEXTGIS_BOUNDARIES_RESOURCE_ID`, `NEXTGIS_EXTRA_RESOURCE_IDS`, `NEXTGIS_MAP_TMS_URL`, `NGW_POSTGIS_DSN` | Бесплатно, без ключа. [api.mapdev.io/resource/138](https://api.mapdev.io/resource/138) — границы судебных участков (Россошанский район, Воронежская обл.) | `court_locator/nextgis_source.py`, `updater.update_from_nextgis`, `GET /api/nextgis-map`, `POST /api/nextgis-load`, `GET /api/nextgis-resources`, `POST /api/nextgis-sync-postgis` |

GeoJSON: `https://api.mapdev.io/api/resource/137/geojson`. TMS для отображения на карте: `.../tile?resource=138&nd=204&z={z}&x={x}&y={y}`. Прямое подключение к PostGIS: `NGW_POSTGIS_DSN` или `PG_DSN` — `sync_nextgis_to_postgis()` загружает GeoJSON в таблицу court_districts.

---

## 5. Геокодирование

| API / сервис | Переменные окружения | Где взять ключ | Используется в коде |
|--------------|----------------------|----------------|---------------------|
| **Yandex Geocoder (HTTP `geocode-maps.yandex.ru`)** | Приоритет: **`YANDEX_GEO_KEY`** → **`YANDEX_GEOCODER_API_KEY`** → **`YANDEX_LOCATOR_API_KEY`** → **`YANDEX_LOCATOR_KEY`** | [developer.tech.yandex.ru](https://developer.tech.yandex.ru) — ключ Геокодера; «Локатор» — запасной вариант в том же контуре | `court_locator/config.py`, `generate_courts_geo.py`, `geo_court_parser.py`, `jurisdiction.py` |

**Диагностика:** `court_locator.config.api_env_diagnostics()` и блок «Диагностика env» в выводе `python parser/check_apis.py` показывают, какой класс ключа активен: **`GEOCODER`** (первые два имени) или **`LOCATOR`**, плюс **точное имя переменной** (`YANDEX_GEO_KEY_ENV`). Это не секрет, только метка для отладки.

**Отключение внешнего геокода (регресс-тесты, ускорение):** `SKIP_EXTERNAL_GEO=1` (или `true` / `yes` / `on`) — в `unified_jurisdiction.core` шаг **C** не вызывает геокодер (Nominatim, Yandex и т.д.); в цепочке шагов появится `C:skipped_external_geo`. Поиск по **Dagalin** (шаг D) и **DaData** (шаг B) при этом **не отключаются**. Скрипт сравнения: `scripts/compare_full_vs_dagalin_50.py`.

**Взвешенное согласование источников (модуль `unified_jurisdiction.voting`):** задаётся порог суммы весов `JURISDICTION_MIN_CONFIDENCE_SUM` (по умолчанию `1.5`), нижняя граница при полном расхождении — `JURISDICTION_DISAGREEMENT_CONFIDENCE` (по умолчанию `0.3`). Имена источников полигона для логики конфликтов: `JURISDICTION_POLYGON_SOURCE_NAMES` (по умолчанию `polygon,postgis`). Тесты контракта: `tests/test_jurisdiction_voting_spec.py`.

### 5.1. Частые путаницы с именами переменных

| Задумывали | Реальность в коде |
|------------|-------------------|
| Один ключ `YANDEX_API_KEY` на все сервисы Яндекса | Для **геокодера маршрута HTTP** он **не читается** в `court_locator`: нужен один из имён из таблицы выше. `YANDEX_API_KEY` используется в **YandexGPT** и в отдельных модулях (`court-verification`), но не как единый ключ геокодера в `court_locator`. |
| Только `DADATA_SECRET_KEY` в .env | Раньше читался только `DADATA_SECRET`. Сейчас поддерживается и **`DADATA_SECRET_KEY`** (`court_locator/config.py`, `dadata_api.py`). |
| Токен только в `DADATA_API_KEY` | Допустимо: подставляется в тот же `DADATA_TOKEN` с меткой источника **`API_KEY`** в диагностике. |

---

## 6. Telegram и мониторинг

| API / сервис | Переменные окружения | Где взять ключ | Используется в коде |
|--------------|----------------------|----------------|---------------------|
| **Telegram Bot** | `BOT_TOKEN`, `ADMIN_ID` (или `MONITOR_CHAT_ID`) | [t.me/BotFather](https://t.me/BotFather) — создать бота, получить токен. ADMIN_ID — свой Telegram user id (например через @userinfobot) | `bot.py`, `supreme_case_monitor.py`, `supreme_monitor.py` |

---

## 7. Кэш и инфраструктура

| API / сервис | Переменные окружения | Где взять ключ | Используется в коде |
|--------------|----------------------|----------------|---------------------|
| **Redis** | `REDIS_HOST`, `REDIS_PORT` или `REDIS_URL` | Локальный Redis или облачный (Redis Cloud, ElastiCache). По умолчанию localhost:6379 | `supreme_turbo.py`, `rate_limit.py`, `supreme_monitor.py` |
| **PostgreSQL** (БД судов) | `COURTS_DB_BACKEND=postgres`, `PG_DSN` | Своя СУБД или облако (например Supabase). DSN: `dbname=courts user=... password=... host=... port=5432` | `courts_postgres.py` |

---

## 8. LLM (разбор документов / подсказки)

Оба провайдера используются для разбора судебных документов: **сначала запрос к одному, при ошибке или отсутствии ключа — ко второму**. Если оба недоступны, срабатывает regex-fallback.

| API / сервис | Переменные окружения | Где взять ключ | Используется в коде |
|--------------|----------------------|----------------|---------------------|
| **GigaChat** | `GIGACHAT_CREDENTIALS` или `GIGACHAT_API_KEY` | [developers.sber.ru](https://developers.sber.ru) — GigaChat API, получить учётные данные | `llm_court_parser.py`, `bot.py` |
| **Yandex GPT (YandexGPT)** | `YANDEX_GPT_API_KEY`, `YANDEX_GPT_CATALOG_ID` (folder id в Yandex Cloud) | [Yandex Cloud](https://cloud.yandex.ru) — создать каталог, включить YandexGPT API, создать API-ключ в IAM. Catalog ID = идентификатор каталога | `llm_court_parser.py` |

Порядок вызова в `SupremeLLMParser`: 1) GigaChat (если заданы учётные данные); при исключении или пустом ответе → 2) Yandex GPT (если заданы `YANDEX_GPT_API_KEY` и `YANDEX_GPT_CATALOG_ID`); при ошибке → 3) regex-fallback по тексту документа.

---

## 9. Опциональные (AIS, CRM, API сервера)

| API / сервис | Переменные окружения | Где взять ключ | Используется в коде |
|--------------|----------------------|----------------|---------------------|
| **AIS (корабли)** | `AIS_VESSELFINDER_KEY`, `AIS_FLEETMON_KEY`, `AIS_AISHUB_KEY`, `AIS_GORADAR_KEY`, `AIS_SHIPATLAS_KEY`, `AIS_*_URL` | Соответствующие сервисы (VesselFinder, FleetMon, AISHub и т.д.) — бесплатные лимиты или платные ключи | `ais_tracker.py` |
| **CRM (1C / Bitrix24)** | Передаётся в конструктор: `api_url`, `api_key` | Настройки вашей CRM | `supreme_crm.py` |
| **CORS / API сервера** | `CORS_ORIGINS`, `API_HOST`, `API_PORT`, `API_RELOAD` | Для FastAPI: настройка хоста и порта | `supreme_secure_api.py` |

---

## 10. Пример .env (шаблон)

Создайте файл `.env` в корне проекта (не коммитить в git):

```env
# Подсудность и адреса (Profile API — баланс/статистика — требует и Secret)
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
```

Загрузка: в коде используется `os.getenv(...)`. Чтобы подхватить `.env`, при запуске приложения можно вызвать `python-dotenv`: `load_dotenv()` в `main.py` или в точке входа бота/API.

---

# Мега-подсказка: чего не хватает, чтобы проект «точно начал искать»

1. **DaData**  
   Без `DADATA_TOKEN` поиск суда по адресу не работает (остаётся только БД по паспорту и ГАС по ФИО). Зарегистрироваться на dadata.ru и прописать токен в `.env`.

2. **БД судов**  
   Репозиторий судов должен быть заполнен: либо импорт из CSV/Excel (`import_courts.py`), либо генерация из открытых данных (`generate_courts_db.py`). Иначе поиск по региону/району паспорта ничего не вернёт.

3. **ФССП**  
   В коде уже есть единый клиент `parser/fssp_client.py` и переменная **`FSSP_API_KEY`** (ключ в .env, не коммитится). Все запросы к ФССП идут через него. Для реальных данных по ИП — оформить доступ на [fssp.gov.ru](https://fssp.gov.ru) (ГИС ГМП, СМЭВ и т.д.) и прописать выданный ключ в `.env`.

4. **Капча на ГАС**  
   Если bsr.sudrf.ru показывает капчу — без сервиса решения капчи (2Captcha/Anti-Captcha и т.д.) парсинг по ФИО будет падать. Задать один из ключей из раздела «Капча» и использовать логику в `supreme_recaptcha.py`.

5. **Таймауты и ретраи**  
   Уже есть в коде (SafeAiohttpSession, fetch_with_retries в kad_arbitr, anti_block). При нестабильном интернете можно увеличить таймауты в `supreme_turbo.py` (SafeAiohttpSession) и паузы между запросами к ГАС/ФССП.

6. **Проверка цепочки**  
   Запустить определение подсудности на одном тесте: адрес + паспорт + ФИО. Убедиться, что вызываются DaData → репозиторий судов → sudrf_scraper (по ФИО) и что в логах нет постоянных ошибок от ФССП/ГАС. См. `test_podsudnost.py`, `jurisdiction.determine_jurisdiction`.

7. **ЕФРСБ и КАД Арбитраж**  
   Для банкротств — дореализовать `efrsb_parser.py` (сейчас заглушка). КАД Арбитраж уже парсится без ключа; при блокировках — настроить прокси и задержки через переменные из раздела «Арбитраж».

Итого: для «поиска по ИП и подсудности» достаточно **DADATA_TOKEN** + **заполненная БД судов** + при необходимости **ключ капчи**. Для полных данных по ИП из ФССП нужен **официальный доступ к данным ФССП** и доработка кода под выданный ключ/формат API.

---

# Что ещё не хватает в программе (помимо API ключей)

Ниже — список того, что нужно для полной реализации и стабильной работы, **без учёта самих ключей**.

## 1. Данные и конфигурация

| Что | Где | Что сделать |
|-----|-----|-------------|
| **БД судов заполнена** | `courts.sqlite` создаётся пустой; поиск по региону/району паспорта ищет в ней | Запустить `generate_courts_db.py` или подготовить CSV и `import_courts.py` (файл `parser/data/magistrates.csv` с колонками region, district, section_num, court_name, address, postal_index, coordinates). Без данных поиск по паспорту/адресу вернёт только DaData или ГАС по ФИО. |
| **Индексы БД** | `courts_db.init_db()` не создаёт индексы; репозиторий судов — `SqliteCourtsRepository.init_schema()` | При первом запуске вызывать `SqliteCourtsRepository().init_schema()` (или добавить индексы в `courts_db.init_db()`), чтобы поиск по region/district был быстрым. |
| **Файл .env** | Ключи читаются из `os.getenv` | Создать `.env` по шаблону из раздела 10 и в точке входа вызвать `load_dotenv()` (см. конец файла). |
| **Прокси (опционально)** | `anti_block.py`, `proxy_rotator.py` | При блокировках ГАС/КАД — положить `parser/data/proxies.json` (по образцу `proxies.example.json`) или задать пул прокси в коде. |

## 2. Заглушки и незавершённый код

| Модуль / место | Что не хватает |
|----------------|----------------|
| **ФССП** | Реализовано: единый клиент `parser/fssp_client.py`, ключ `FSSP_API_KEY` в .env. Запросы из supreme_turbo, supreme_parser, anti_hallucination переведены на fssp_client. Для доступа к данным — договор с ФССП и ключ в конфиге. |
| **ЕФРСБ** | Модуля `efrsb_parser.py` в репозитории нет (только упоминание в `supreme_sources` и в `docs/sources_parsing.md`). Нужен отдельный модуль: парсинг bankrot.fedresurs.ru по ИНН/ФИО/номеру дела, вывод в таблицу/Excel. |
| **sudrf_api.py** | Строка «TODO: разобрать resp по реальному JSON/HTML» — ответ ГАС после POST не парсится в структурированный список; при капче возвращается пустой список. Нужно: разбор HTML (BeautifulSoup) по аналогии с `sudrf_scraper.py` или поддержка реального формата ответа. |
| **supreme_crm.py** | `sync_to_bitrix24` и `sync_to_amocrm` — заглушки (логируют и возвращают `synced: False`). Нужна реализация под REST API Битрикс24 и AmoCRM. |
| **supreme_recaptcha.py** | Capsolver для Cloudflare Turnstile не реализован (stub). Нужен вызов Capsolver API (createTask → getResult) и подстановка токена в форму. |
| **address_parser.py** | Указано «заглушки под тестовые кейсы» — для продакшена нужны правила разбора адресов по регионам/улицам или вызов DaData/другого сервиса нормализации. |
| **monitor.py** | `notify_telegram_stub` — заглушка уведомлений; для реальных алертов подставить отправку в Telegram (например через aiogram/BOT_TOKEN). |

## 3. Зависимости (опциональные, но расширяют функциональность)

| Пакет | Назначение | Где используется |
|-------|------------|-------------------|
| **gigachat** | GigaChat LLM | `llm_court_parser.py`, `anti_hallucination.py` — разбор судебных документов. В `requirements.txt` закомментирован. |
| **pydantic>=2** | Валидация моделей | LLM-парсер, экспорт. Закомментирован в requirements. |
| **pdf2image, pytesseract, Pillow** | OCR из PDF | `ocr_llm_pipeline.py`, `supreme_parser.py` — если нужен разбор сканов/PDF. |
| **playwright** | Браузер для капчи/стелс-запросов | `supreme_recaptcha.py` (опционально). |
| **loguru** | Удобное логирование | По проекту как fallback к logging. |

Установить по мере необходимости: `pip install gigachat pydantic pdf2image pytesseract Pillow` и т.д.

## 4. Инфраструктура и запуск

| Что | Комментарий |
|-----|-------------|
| **Redis** | Для кэша ИП (`supreme_turbo`), rate limit (`rate_limit.py`), мониторинга (`supreme_monitor`). Без Redis кэш L2 отключится, лимиты — через память или отключены. |
| **PostgreSQL** | Только если `COURTS_DB_BACKEND=postgres` и нужна общая БД судов. Иначе достаточно SQLite. |
| **Точка входа** | Бот: запуск `bot.py`. API: `uvicorn supreme_secure_api:app` или `dashboard:app`. Подсудность из консоли: `main.py`. Нужно один раз вызвать `load_dotenv()` в выбранной точке входа. |
| **Скрипт профилирования** | В предыдущих обсуждениях упоминался `profile_supreme.py` (cProfile для `batch_30k_excel`, `super_determine_jurisdiction`). В репозитории его нет — при необходимости добавить отдельный скрипт, который оборачивает эти вызовы в `cProfile.run()` или аналог. |

## 5. Тесты и проверка

| Что | Где / как |
|-----|-----------|
| **Проверка подсудности** | `test_podsudnost.py`, вызов `jurisdiction.determine_jurisdiction()` с тестовыми данными (адрес, паспорт, ФИО). |
| **Проверка цепочки** | Убедиться, что по очереди вызываются DaData → репозиторий судов → sudrf по ФИО и что в логах нет массовых ошибок ФССП/ГАС. |

---

**Загрузка .env:** в коде — `parser/env_config.py`: `load_dotenv_if_available()`, шаблон .env — `get_env_template()`, проверка «чего не хватает» — `what_is_missing_for_search()`. Запуск: `python env_config.py check` (подсказка), `python env_config.py write` (создать .env.example). В точке входа можно вызвать `from env_config import load_dotenv_if_available; load_dotenv_if_available()`.
