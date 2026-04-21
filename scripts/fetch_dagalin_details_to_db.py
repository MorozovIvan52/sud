"""
Догрузка детальных данных с карточек dagalin.org в dagalin_mirovye_courts.detail_json
(вышестоящий суд, реквизиты госпошлины, ОСП).

Перед запуском заполните справочник URL:
  python scripts/scrape_dagalin_rf_mirovye_to_db.py

Затем:
  python scripts/fetch_dagalin_details_to_db.py --max 50
  python scripts/fetch_dagalin_details_to_db.py --insecure --host-header dagalin.org

Переменная DAGALIN_FETCH_SKIP=1 отключает сетевые запросы (для CI).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from court_locator.dagalin_page_parse import dagalin_detail_to_json_str, parse_dagalin_detail_html
from court_locator.database import Database
from scrape_dagalin_region import DagalinRegionScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    ap = argparse.ArgumentParser(description="Загрузка detail_json с dagalin.org в БД")
    ap.add_argument("--max", type=int, default=0, help="Максимум URL (0 = все без detail_json)")
    ap.add_argument("--delay", type=float, default=1.0, help="Пауза между запросами, сек")
    ap.add_argument("--insecure", action="store_true", help="verify=False для HTTPS")
    ap.add_argument("--host-header", default=None, help="Заголовок Host при доступе по IP")
    ap.add_argument("--timeout", type=int, default=25, help="Таймаут HTTP")
    ap.add_argument("--dry-run", action="store_true", help="Только лог, без записи в БД")
    args = ap.parse_args()

    if os.environ.get("DAGALIN_FETCH_SKIP", "").strip() in ("1", "true", "yes"):
        logger.info("DAGALIN_FETCH_SKIP: выход без запросов")
        return

    db = Database()
    db.init_schema()
    urls = db.list_dagalin_urls_missing_detail(limit=args.max or 0)
    if not urls:
        logger.info("Нет URL без detail_json (или таблица пуста). Сначала scrape_dagalin_rf_mirovye_to_db.")
        db.close()
        return

    scraper = DagalinRegionScraper(
        insecure=args.insecure,
        timeout=args.timeout,
        host_header=args.host_header,
        delay_sec=max(0.0, args.delay),
    )

    ok = err = 0
    for i, url in enumerate(urls):
        logger.info("[%s/%s] %s", i + 1, len(urls), url)
        html = scraper.fetch(url)
        time.sleep(max(0.0, args.delay))
        if not html:
            err += 1
            continue
        try:
            parsed = parse_dagalin_detail_html(html, url)
            dj = dagalin_detail_to_json_str(parsed)
        except Exception as e:
            logger.warning("Парсинг %s: %s", url, e)
            err += 1
            continue
        if not dj or dj == "{}" or dj == "null":
            err += 1
            continue
        if not args.dry_run:
            db.update_dagalin_detail_json(url, dj)
        ok += 1

    db.close()
    logger.info("Готово: успешно %s, ошибок %s", ok, err)


if __name__ == "__main__":
    main()
