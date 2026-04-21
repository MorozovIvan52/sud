from __future__ import annotations

"""
Скрапинг dagalin.org по странице списка (например, https://dagalin.org/courts/niz/wc):
- проверка доступности сайта (HEAD);
- сессия requests с User-Agent и таймаутами;
- ссылки со страницы списка: Drupal teasers — article[about^="/courts/.../wc/..."],
  запасной вариант — все <a href> с /courts/.../wc/;
- для каждой карточки сохраняем краткий текст подсудности из списка (jurisdiction_teaser);
- детальные страницы — extract_dagalin из court_sites_scraper (boundary_snippet и контакты);
- задержка между запросами;
- JSON/CSV в batch_outputs/dagalin_scrape_<ts>.{json,csv}

Запуск:
  python scripts/scrape_dagalin_region.py --list https://dagalin.org/courts/niz/wc --max 200 --insecure
  python scripts/scrape_dagalin_region.py --list https://77.223.102.186/courts/niz/wc --host-header dagalin.org --insecure
"""

import argparse
import csv
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from court_sites_scraper import extract_dagalin, clean_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Путь к карточке участка: /courts/<region>/wc/<slug>, не сама страница списка .../wc
WC_DETAIL_PATH_RE = re.compile(r"/courts/[^/]+/wc/[^/]+/?$", re.IGNORECASE)


class DagalinRegionScraper:
    """Парсер списка и карточек dagalin.org (территориальная подсудность и контакты)."""

    def __init__(
        self,
        insecure: bool = False,
        timeout: int = 10,
        host_header: str | None = None,
        delay_sec: float = 1.0,
    ):
        self.insecure = insecure
        self.timeout = timeout
        self.host_header = host_header
        self.delay_sec = delay_sec
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (compatible; CourtSitesScraper/1.0)"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5",
            }
        )

    def _request_headers(self) -> dict:
        h = dict(self.session.headers)
        if self.host_header:
            h["Host"] = self.host_header
        return h

    def check_site_accessibility(self, base_url: str) -> bool:
        """Проверяет доступность хоста перед парсингом."""
        try:
            resp = self.session.head(
                base_url.rstrip("/") + "/",
                timeout=min(5, self.timeout),
                verify=not self.insecure,
                headers=self._request_headers(),
                allow_redirects=True,
            )
            if resp.status_code == 200:
                return True
            logger.warning("HEAD %s вернул статус %s", base_url, resp.status_code)
            return False
        except Exception as e:
            logger.error("Сайт недоступен (%s): %s", base_url, e)
            return False

    def fetch(self, url: str) -> str | None:
        try:
            resp = self.session.get(
                url,
                timeout=self.timeout,
                verify=not self.insecure,
                headers=self._request_headers(),
            )
            resp.raise_for_status()
            ct = resp.headers.get("Content-Type", "")
            if "text/html" not in ct:
                logger.warning("Не HTML для %s: %s", url, ct)
                return None
            return resp.text
        except Exception as e:
            logger.error("Ошибка загрузки %s: %s", url, e)
            return None

    @staticmethod
    def parse_list_page(
        html: str, list_url: str
    ) -> Tuple[List[str], Dict[str, str], Dict[str, str]]:
        """
        Возвращает:
        - упорядоченные URL карточек;
        - map url -> краткая подсудность (тизер) со страницы списка;
        - map url -> полное название участка (заголовок тизера).
        """
        soup = BeautifulSoup(html, "html.parser")
        base = list_url
        links_ordered: List[str] = []
        seen: set[str] = set()
        teaser_by_url: Dict[str, str] = {}
        name_by_url: Dict[str, str] = {}

        for art in soup.find_all("article", attrs={"about": True}):
            about = (art.get("about") or "").strip()
            if not about or not WC_DETAIL_PATH_RE.search(about.split("?")[0].rstrip("/")):
                continue
            abs_url = urljoin(base, about).split("#")[0].rstrip("/")
            if abs_url in seen:
                continue
            seen.add(abs_url)
            links_ordered.append(abs_url)
            body = art.select_one(".field--name-body") or art.find(
                "div",
                class_=lambda c: isinstance(c, str) and "field--name-body" in c,
            )
            teaser_by_url[abs_url] = clean_text(body.get_text()) if body else ""
            title_el = art.select_one("h2.node__title a") or art.select_one("h2.node__title") or art.find("h2")
            name_by_url[abs_url] = clean_text(title_el.get_text()) if title_el else ""

        if not links_ordered:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not re.search(r"/courts/.+?/wc/.+?", href):
                    continue
                abs_url = urljoin(base, href).split("#")[0].rstrip("/")
                if not WC_DETAIL_PATH_RE.search(urlparse(abs_url).path):
                    continue
                if abs_url not in seen:
                    seen.add(abs_url)
                    links_ordered.append(abs_url)

        return links_ordered, teaser_by_url, name_by_url


def save_results(results: List[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    json_path = out_dir / f"dagalin_scrape_{ts}.json"
    csv_path = out_dir / f"dagalin_scrape_{ts}.csv"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if results:
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)
    return json_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Скрапинг списка мировых судов dagalin.org")
    ap.add_argument(
        "--list",
        required=True,
        help="URL страницы списка (например, https://dagalin.org/courts/niz/wc)",
    )
    ap.add_argument("--max", type=int, default=0, help="Ограничение числа ссылок (0 = все)")
    ap.add_argument("--insecure", action="store_true", help="verify=False для HTTPS")
    ap.add_argument(
        "--host-header",
        default=None,
        help="Принудительный заголовок Host (доступ по IP с нужным vhost)",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Пауза между запросами карточек, сек (по умолчанию 1.0)",
    )
    ap.add_argument(
        "--skip-check",
        action="store_true",
        help="Не выполнять HEAD-проверку доступности сайта",
    )
    ap.add_argument("--timeout", type=int, default=10, help="Таймаут HTTP, сек")
    args = ap.parse_args()

    parsed = urlparse(args.list)
    if not parsed.scheme or not parsed.netloc:
        logger.error("Некорректный URL списка: %s", args.list)
        sys.exit(1)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    scraper = DagalinRegionScraper(
        insecure=args.insecure,
        timeout=args.timeout,
        host_header=args.host_header,
        delay_sec=args.delay,
    )

    if not args.skip_check and not scraper.check_site_accessibility(base_url):
        logger.error("Сайт недоступен. Проверьте сеть, DNS/hosts или используйте --skip-check.")
        sys.exit(1)

    logger.info("Загрузка списка: %s", args.list)
    html = scraper.fetch(args.list)
    if not html:
        logger.error("Не удалось загрузить страницу списка")
        sys.exit(1)

    links, teaser_by_url, name_by_url = DagalinRegionScraper.parse_list_page(html, args.list)
    if args.max and len(links) > args.max:
        links = links[: args.max]

    logger.info("Найдено ссылок на карточки: %s", len(links))

    results: List[dict] = []
    for i, url in enumerate(links):
        logger.info("[%s/%s] %s", i + 1, len(links), url)
        page = scraper.fetch(url)
        if not page:
            continue
        teaser = teaser_by_url.get(url, "")
        list_title = name_by_url.get(url, "")
        for r in extract_dagalin(page, url):
            row = r.__dict__ if hasattr(r, "__dict__") else dict(r)
            row = dict(row)
            if list_title:
                row["name"] = list_title
            row["jurisdiction_teaser"] = teaser
            row["detailed_jurisdiction"] = row.get("boundary_snippet") or ""
            results.append(row)
        if scraper.delay_sec > 0 and i < len(links) - 1:
            time.sleep(scraper.delay_sec)

    out = save_results(results, Path("batch_outputs"))
    logger.info("Сохранено записей: %s -> %s", len(results), out)


if __name__ == "__main__":
    main()
