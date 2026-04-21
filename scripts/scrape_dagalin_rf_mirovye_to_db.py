from __future__ import annotations

"""
Загрузка в БД всех мировых судебных участков РФ с dagalin.org (название + территориальная подсудность).

1. Страница https://dagalin.org/courts — собираем ссылки вида /courts/<код>/wc (списки по субъекту).
2. Для каждого списка — парсинг тизеров (без запросов к карточкам): название участка и текст подсудности.
3. Запись в SQLite таблицу dagalin_mirovye_courts (court_locator / court_districts.sqlite).

Примеры:
  python scripts/scrape_dagalin_rf_mirovye_to_db.py --clear
  python scripts/scrape_dagalin_rf_mirovye_to_db.py --max-regions 3 --dry-run
  python scripts/scrape_dagalin_rf_mirovye_to_db.py --insecure --host-header dagalin.org

Догрузка реквизитов (вышестоящий суд, госпошлина, ОСП) с карточек:
  python scripts/fetch_dagalin_details_to_db.py --max 100
"""

import argparse
import csv
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from court_locator.database import Database
from scrape_dagalin_region import DagalinRegionScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def discover_region_wc_list_urls(html: str, page_url: str) -> List[str]:
    """Ссылки на страницы списков мировых судов по субъектам: /courts/<code>/wc."""
    soup = BeautifulSoup(html, "html.parser")
    base = page_url
    seen: set[str] = set()
    out: List[str] = []
    for a in soup.find_all("a", href=True):
        full = urljoin(base, a["href"])
        p = urlparse(full)
        parts = [x for x in p.path.split("/") if x]
        if len(parts) != 3 or parts[0] != "courts" or parts[2] != "wc":
            continue
        norm = f"{p.scheme}://{p.netloc}/courts/{parts[1]}/wc".rstrip("/")
        if norm not in seen:
            seen.add(norm)
            out.append(norm)
    return sorted(out)


def region_code_from_detail_url(detail_url: str) -> str:
    parts = [x for x in urlparse(detail_url).path.split("/") if x]
    if len(parts) >= 3 and parts[0] == "courts":
        return parts[1]
    return ""


def fallback_name(detail_url: str) -> str:
    slug = [x for x in urlparse(detail_url).path.split("/") if x]
    if slug:
        return f"Мировой судебный участок ({slug[-1]})"
    return "Мировой судебный участок"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Скрапинг всех мировых участков РФ с dagalin.org → таблица dagalin_mirovye_courts"
    )
    ap.add_argument(
        "--base-url",
        default="https://dagalin.org",
        help="Корень сайта (по умолчанию https://dagalin.org)",
    )
    ap.add_argument("--insecure", action="store_true", help="verify=False для HTTPS")
    ap.add_argument("--host-header", default=None, help="Заголовок Host при доступе по IP")
    ap.add_argument("--delay", type=float, default=0.8, help="Пауза между HTTP-запросами, сек")
    ap.add_argument("--timeout", type=int, default=25, help="Таймаут запроса, сек")
    ap.add_argument("--max-regions", type=int, default=0, help="Ограничить число субъектов (0 = все)")
    ap.add_argument("--clear", action="store_true", help="Очистить таблицу перед загрузкой")
    ap.add_argument("--dry-run", action="store_true", help="Не писать в БД, только лог и счётчик")
    ap.add_argument(
        "--csv-out",
        default=None,
        help="Опционально сохранить копию в CSV (utf-8-sig), например batch_outputs/dagalin_mirovye_rf.csv",
    )
    ap.add_argument("--skip-check", action="store_true", help="Пропустить HEAD-проверку сайта")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    index_url = f"{base}/courts"
    parsed = urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        logger.error("Некорректный --base-url: %s", args.base_url)
        sys.exit(1)

    scraper = DagalinRegionScraper(
        insecure=args.insecure,
        timeout=args.timeout,
        host_header=args.host_header,
        delay_sec=args.delay,
    )

    if not args.skip_check and not scraper.check_site_accessibility(base):
        logger.error("Сайт недоступен. Проверьте сеть или укажите --skip-check.")
        sys.exit(1)

    logger.info("Загрузка оглавления: %s", index_url)
    index_html = scraper.fetch(index_url)
    if not index_html:
        logger.error("Не удалось загрузить %s", index_url)
        sys.exit(1)

    region_urls = discover_region_wc_list_urls(index_html, index_url)
    if args.max_regions and len(region_urls) > args.max_regions:
        region_urls = region_urls[: args.max_regions]
    logger.info("Найдено списков мировых судов по субъектам: %s", len(region_urls))

    all_rows: List[Dict[str, Any]] = []
    for ri, list_url in enumerate(region_urls):
        logger.info("Регион [%s/%s]: %s", ri + 1, len(region_urls), list_url)
        html = scraper.fetch(list_url)
        time.sleep(max(0.0, args.delay))
        if not html:
            logger.warning("Пропуск (нет HTML): %s", list_url)
            continue
        links, teaser_by_url, name_by_url = DagalinRegionScraper.parse_list_page(html, list_url)
        rc = region_code_from_detail_url(links[0]) if links else ""
        if not rc:
            p = urlparse(list_url)
            seg = [x for x in p.path.split("/") if x]
            if len(seg) >= 2:
                rc = seg[1]
        for u in links:
            name = (name_by_url.get(u) or "").strip() or fallback_name(u)
            jur = (teaser_by_url.get(u) or "").strip()
            all_rows.append(
                {
                    "source_url": u,
                    "region_code": region_code_from_detail_url(u) or rc,
                    "court_name": name,
                    "jurisdiction_text": jur,
                }
            )

    logger.info("Всего участков собрано: %s", len(all_rows))

    if args.csv_out:
        csv_path = Path(args.csv_out)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["court_name", "jurisdiction_text", "source_url", "region_code"],
            )
            w.writeheader()
            for r in all_rows:
                w.writerow(
                    {
                        "court_name": r["court_name"],
                        "jurisdiction_text": r["jurisdiction_text"],
                        "source_url": r["source_url"],
                        "region_code": r["region_code"],
                    }
                )
        logger.info("CSV: %s", csv_path.resolve())

    if args.dry_run:
        return

    db = Database()
    db.init_schema()
    if args.clear:
        db.clear_dagalin_mirovye_courts()
    db.upsert_dagalin_mirovye_courts(all_rows)
    db.close()
    logger.info("Записано в dagalin_mirovye_courts: %s строк", len(all_rows))


if __name__ == "__main__":
    main()
