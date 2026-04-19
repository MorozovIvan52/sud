#!/usr/bin/env python3
"""
Запуск REST API сервиса подсудности (court_locator).
Режим только бесплатные источники: не задавайте DADATA_TOKEN и YANDEX_GEO_KEY в .env.
Подробнее: docs/court_locator_free_sources.md
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main():
    try:
        import uvicorn
    except ImportError:
        print("Установите: pip install uvicorn fastapi")
        sys.exit(1)
    from court_locator.api import app
    if app is None:
        print("Установите: pip install fastapi uvicorn")
        sys.exit(1)
    print("Сервис подсудности. Excel пакетом: POST /api/v1/batch-process (format=xlsx) — см. START_EXCEL.md")
    print("API docs: http://0.0.0.0:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
