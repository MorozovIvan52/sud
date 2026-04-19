# Проверка подключения API

## Где используются API

| API | Переменная окружения | Где используется |
|-----|----------------------|------------------|
| **DaData** | `DADATA_TOKEN`, `DADATA_API_KEY` | parser/dadata_api.py, court_locator (court_matcher, gps_handler), batch_processing (address_normalization), jurisdiction_service (геокодер, нормализатор), court-verification |
| **Yandex Geocoder / Locator** | `YANDEX_GEO_KEY`, `YANDEX_GEOCODER_API_KEY`, `YANDEX_API_KEY`, `YANDEX_LOCATOR_API_KEY` | court_locator/gps_handler.py, court_locator/multi_geocoder.py, jurisdiction_service (geocoding_service), court-verification (yandex_maps.py) |
| **ФССП** | `FSSP_API_KEY` | parser/check_apis.py (проверка) |
| **ГАС Правосудие** | — | parser/sudrf_scraper.py, parser/jurisdiction.py |
| **Redis** | `REDIS_URL`, `REDIS_HOST` | jurisdiction_service (кэш, rate limit) |

## Запуск проверки всех API

```bash
python parser/check_apis.py
```

Вывод: для каждого API — OK или FAIL и краткое сообщение (ключ не задан, ответ получен, таймаут и т.д.).

## Запуск тестов подключения

```bash
pytest tests/test_apis_connectivity.py tests/test_court_locator_api_integration.py tests/test_unified_jurisdiction_smoke.py -v
```

- **test_dadata_connected_and_responds** — DaData suggest/address (skip при отсутствии ключа или таймауте).
- **test_yandex_geocoder_connected_and_responds** — Yandex Geocoder (skip без ключа).
- **test_courts_db_available** — БД судов (courts.sqlite).
- **test_dadata_suggest_returns_suggestions** — формат ответа standardize_address.
- **test_yandex_geocode_returns_coords** — координаты в ответе Yandex.
- **test_process_debtor_returns_result_for_moscow_address** — пайплайн по адресу в Москве (skip без геокодер-ключей).
- **test_process_debtor_returns_result_for_spb_address** — пайплайн по адресу в СПб.

При отсутствии ключей тесты DaData/Yandex помечаются как skipped, а не failed.
