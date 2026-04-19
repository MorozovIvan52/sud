#!/usr/bin/env python3
"""
Публичный сайт «ПарсерПРО» для клиентов (лендинг + определение подсудности + заявка).
По умолчанию: http://127.0.0.1:8020

Сайт открывается только пока это окно запущено. Закрыли терминал — страница станет недоступна.

Переменные окружения:
  PARSERPRO_PORT — порт (по умолчанию 8020), если порт занят
  PARSERPRO_CORS_ORIGINS — через запятую, если фронт на другом домене
"""
import os
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
    try:
        from parserpro_site.app import app
    except Exception as e:
        print("Ошибка при загрузке приложения:", e, file=sys.stderr)
        print("Запускайте из папки проекта parserSupreme или проверьте зависимости.", file=sys.stderr)
        sys.exit(1)

    port = int(os.environ.get("PARSERPRO_PORT", "8020"))
    print("ПарсерПРО — клиентский сайт", flush=True)
    print(f"  URL: http://127.0.0.1:{port}/", flush=True)
    print("  Не закрывайте это окно, пока пользуетесь сайтом.", flush=True)
    if port != 8020:
        print("  (используется PARSERPRO_PORT)", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
