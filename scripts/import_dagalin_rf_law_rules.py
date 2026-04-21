from __future__ import annotations

"""
Скрапинг всех мировых судебных участков РФ с dagalin.org (тизеры списков по субъектам)
и загрузка правил в law_rules (очистка только строк dagalin% при --clear-dagalin).

  python scripts/import_dagalin_rf_law_rules.py
  python scripts/import_dagalin_rf_law_rules.py --max-regions 5 --dry-run
  python scripts/import_dagalin_rf_law_rules.py --json-out batch_outputs/dagalin_rf_full.json --no-import
  python scripts/import_dagalin_rf_law_rules.py --insecure --host-header dagalin.org --skip-check
"""

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

from court_locator.database import Database
from import_dagalin_json_to_law_rules import items_to_deduped_law_rules
from scrape_dagalin_region import DagalinRegionScraper
from scrape_dagalin_rf_mirovye_to_db import (
    discover_region_wc_list_urls,
    fallback_name,
    region_code_from_detail_url,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_region_code_to_name(index_html: str, page_url: str) -> Dict[str, str]:
    """Ссылка /courts/<code> → название субъекта с оглавления dagalin."""
    soup = BeautifulSoup(index_html, "html.parser")
    base = page_url
    m: Dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        full = urljoin(base, a["href"])
        p = urlparse(full)
        parts = [x for x in p.path.split("/") if x]
        if len(parts) != 2 or parts[0] != "courts":
            continue
        code = parts[1]
        if not re.match(r"^[a-z0-9]{2,8}$", code, re.I):
            continue
        label = re.sub(r"\s+", " ", (a.get_text() or "").strip())
        if len(label) < 3:
            continue
        old = m.get(code, "")
        if len(label) > len(old):
            m[code] = label
    return m


def scrape_all_items(
    scraper: DagalinRegionScraper,
    index_url: str,
    delay: float,
    max_regions: int,
) -> List[Dict[str, Any]]:
    index_html = scraper.fetch(index_url)
    if not index_html:
        raise RuntimeError(f"Не удалось загрузить {index_url}")
    code_map = build_region_code_to_name(index_html, index_url)
    logger.info("Субъектов в оглавлении (кодов): %s", len(code_map))

    region_urls = discover_region_wc_list_urls(index_html, index_url)
    if max_regions and len(region_urls) > max_regions:
        region_urls = region_urls[:max_regions]
    logger.info("Списков мировых судов к обходу: %s", len(region_urls))

    items: List[Dict[str, Any]] = []
    for ri, list_url in enumerate(region_urls):
        logger.info("Регион [%s/%s]: %s", ri + 1, len(region_urls), list_url)
        html = scraper.fetch(list_url)
        time.sleep(max(0.0, delay))
        if not html:
            logger.warning("Пропуск: %s", list_url)
            continue
        links, teaser_by_url, name_by_url = DagalinRegionScraper.parse_list_page(html, list_url)
        p = urlparse(list_url)
        seg = [x for x in p.path.split("/") if x]
        list_code = seg[1] if len(seg) >= 2 else ""
        region_name = code_map.get(list_code, "").strip() or f"Субъект РФ ({list_code})"

        for u in links:
            name = (name_by_url.get(u) or "").strip() or fallback_name(u)
            jur = (teaser_by_url.get(u) or "").strip()
            rc = region_code_from_detail_url(u) or list_code
            items.append(
                {
                    "name": name,
                    "court_name": name,
                    "jurisdiction_teaser": jur,
                    "boundary_snippet": "",
                    "source_url": u,
                    "region_name": region_name,
                    "region_code": rc,
                }
            )
    return items


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Все мировые суды РФ с dagalin.org → law_rules"
    )
    ap.add_argument("--base-url", default="https://dagalin.org", help="Корень сайта")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--host-header", default=None)
    ap.add_argument("--delay", type=float, default=0.7)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--max-regions", type=int, default=0, help="0 = все субъекты")
    ap.add_argument("--skip-check", action="store_true")
    ap.add_argument(
        "--json-out",
        default=str(ROOT / "batch_outputs" / "dagalin_rf_mirovye_items.json"),
        help="Сохранить сырой список карточек для повторного импорта",
    )
    ap.add_argument(
        "--no-import",
        action="store_true",
        help="Только скрапинг и JSON, без записи в БД",
    )
    ap.add_argument(
        "--clear-dagalin",
        action="store_true",
        help="Перед вставкой удалить law_rules с law_reference LIKE 'dagalin%%'",
    )
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    index_url = f"{base}/courts"
    parsed = urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        logger.error("Некорректный --base-url")
        sys.exit(1)

    scraper = DagalinRegionScraper(
        insecure=args.insecure,
        timeout=args.timeout,
        host_header=args.host_header,
        delay_sec=args.delay,
    )
    if not args.skip_check and not scraper.check_site_accessibility(base):
        logger.error("Сайт недоступен. Используйте --skip-check при необходимости.")
        sys.exit(1)

    items = scrape_all_items(
        scraper, index_url, delay=args.delay, max_regions=args.max_regions
    )
    logger.info("Собрано карточек участков: %s", len(items))

    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("JSON: %s", json_path.resolve())

    if args.no_import:
        return

    deduped = items_to_deduped_law_rules(items)
    logger.info("Уникальных правил после разбора: %s", len(deduped))

    db = Database()
    db.init_schema()
    if args.clear_dagalin:
        conn = db._get_districts_conn()
        conn.execute("DELETE FROM law_rules WHERE law_reference LIKE 'dagalin%'")
        conn.commit()
    db.update_law_rules(deduped, clear_before=False)
    db.close()
    logger.info("Записано правил в law_rules: %s", len(deduped))


if __name__ == "__main__":
    main()
