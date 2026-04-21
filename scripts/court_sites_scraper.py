"""
Политный скрапер сайтов судов/участков без геокодирования:
- читает список seed-URL из config/court_sites_seeds.json (или аргумент --seed)
- уважает robots.txt (urllib.robotparser)
- ограничивает частоту запросов по домену (min_delay_sec)
- парсит контактные данные и признаки участков из HTML (bs4 + regex)
- сохраняет результат в batch_outputs/court_sites_scrape_<ts>.json и .csv

Запуск:
  python scripts/court_sites_scraper.py --seeds config/court_sites_seeds.json
  python scripts/court_sites_scraper.py --seed https://example.com/page1 --seed https://example.com/page2

Поля результата:
  name              — найденное имя суда/участка (по заголовкам h1/h2/title)
  address           — строка адреса (эвристика по ключевым словам)
  phone             — первый найденный телефон
  email             — первый найденный email
  schedule          — строка с расписанием (эвристика)
  section_numbers   — список номеров участков, если упомянуты
  boundary_snippet  — фраза с упоминанием границ, если есть
  source_url        — откуда спарсили
  fetched_at        — ISO-время
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


USER_AGENT = "Mozilla/5.0 (compatible; CourtSitesScraper/1.0)"
DEFAULT_TIMEOUT = 7  # жесткий таймаут на ответ
DEFAULT_MIN_DELAY = 2.0  # seconds between requests to same domain


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(\+7|8)[^\d]{0,3}(\d{3})[^\d]{0,3}(\d{3})[^\d]{0,3}(\d{2})[^\d]{0,3}(\d{2})")
SECTION_RE = re.compile(r"(?:участк[а-я]*|миров[а-я\s]+суд[а-я]*).*?(\d{1,3})", re.IGNORECASE)
ADDRESS_HINTS = ("г.", "ул.", "улица", "пр.", "просп", "д.", "дом", "стр", "корп", "пл.", "площадь", "ш.", "шоссе", "пер.")
SCHEDULE_HINTS = ("график", "прием", "приём", "часы", "режим", "время работы")
BOUNDARY_HINT = "границ"


@dataclass
class ScrapeResult:
    name: str
    address: str
    phone: str
    email: str
    schedule: str
    section_numbers: List[str]
    boundary_snippet: str
    source_url: str
    fetched_at: str
    dagalin_detail: Optional[Dict[str, Any]] = None
    jurisdiction_html_report: Optional[Dict[str, Any]] = None


def load_seeds(path: Path) -> List[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


def can_fetch(url: str, rp_cache: dict[str, RobotFileParser]) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = rp_cache.get(robots_url)
    if rp is None:
        rp = RobotFileParser()
        try:
            rp.set_url(robots_url)
            rp.read()
        except Exception:
            # если robots недоступен — разрешаем, чтобы не блокировать
            rp = None
        rp_cache[robots_url] = rp
    if rp is None:
        return True
    return rp.can_fetch(USER_AGENT, url)


def throttle(domain: str, last_time: dict[str, float], min_delay: float = DEFAULT_MIN_DELAY) -> None:
    now = time.time()
    if domain in last_time:
        delta = now - last_time[domain]
        if delta < min_delay:
            time.sleep(min_delay - delta)
    last_time[domain] = time.time()


def fetch(
    url: str,
    last_time: dict[str, float],
    rp_cache: dict[str, RobotFileParser],
    log_level: str = "info",
    insecure_ssl: bool = False,
) -> Optional[str]:
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http"):
        return None
    if not can_fetch(url, rp_cache):
        if log_level == "debug":
            print(f"[skip robots] {url}")
        return None
    throttle(parsed.netloc, last_time)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT, verify=not insecure_ssl)
            if log_level == "debug":
                clen = resp.headers.get("Content-Length")
                print(f"[{resp.status_code}] {url} len={clen or len(resp.content)}")
            if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
                return resp.text
            if resp.status_code in (403, 404):
                return None
        except Exception as e:
            if log_level == "debug":
                print(f"[error attempt {attempt+1}] {url} {e}")
            time.sleep(1 + attempt)
    return None


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_fields(html: str, url: str) -> ScrapeResult:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(" ")
    text = clean_text(text)

    # Name: prefer h1/h2/title
    name = ""
    for tag_name in ("h1", "h2", "title"):
        tag = soup.find(tag_name)
        if tag and clean_text(tag.get_text()):
            name = clean_text(tag.get_text())
            break

    # Email, phone
    email = ""
    m = EMAIL_RE.search(text)
    if m:
        email = m.group(0)
    phone = ""
    m = PHONE_RE.search(text)
    if m:
        digits = "".join(m.groups()[1:])  # skip +7/8
        prefix = "+7" if m.group(1).startswith("+7") else "+7"
        phone = f"{prefix}{digits}"

    # Address: heuristic by lines containing address hints
    address = ""
    candidates: List[str] = []
    lines = [clean_text(x) for x in soup.get_text("\n").split("\n") if clean_text(x)]
    for line in lines:
        low = line.lower()
        if ("адрес" in low or any(h in low for h in ADDRESS_HINTS)) and len(line) > 15:
            candidates.append(line)
    if candidates:
        with_adres = [c for c in candidates if "адрес" in c.lower()]
        if with_adres:
            address = sorted(with_adres, key=len, reverse=True)[0]
        else:
            address = sorted(candidates, key=len, reverse=True)[0]

    # Schedule
    schedule = ""
    sched_lines = [ln for ln in lines if any(h in ln.lower() for h in SCHEDULE_HINTS)]
    if sched_lines:
        schedule = sorted(sched_lines, key=len, reverse=True)[0]

    # Section numbers
    section_numbers = []
    for m in SECTION_RE.finditer(text):
        section_numbers.append(m.group(1))
    section_numbers = sorted(set(section_numbers))

    # Boundary snippet
    boundary_snippet = ""
    if BOUNDARY_HINT in text.lower():
        idx = text.lower().find(BOUNDARY_HINT)
        boundary_snippet = clean_text(text[max(0, idx - 80): idx + 200])

    jur: Optional[Dict[str, Any]] = None
    try:
        _root = Path(__file__).resolve().parent.parent
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        from court_locator.html_jurisdiction_status import analyze_territorial_jurisdiction_html, report_to_dict

        jur = report_to_dict(analyze_territorial_jurisdiction_html(html, url))
    except Exception:
        pass

    return ScrapeResult(
        name=name,
        address=address,
        phone=phone,
        email=email,
        schedule=schedule,
        section_numbers=section_numbers,
        boundary_snippet=boundary_snippet,
        source_url=url,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        jurisdiction_html_report=jur,
    )


def extract_dagalin(html: str, url: str) -> List[ScrapeResult]:
    """
    Специализированный парсер для dagalin.org:
    - detail-страницы (/courts/.../wc/avt1): таблица с адресом/телефоном/email и блок "Территориальная подсудность".
    - список (/courts/niz/wc): извлекаем h2 с названием участка и следующий текст как boundary_snippet (контактов нет).
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = clean_text(soup.get_text(" "))

    # Detail page has table rows with bold labels.
    results: List[ScrapeResult] = []
    is_detail = bool(re.search(r"/courts/.+?/wc/", url))
    if is_detail:
        _root = Path(__file__).resolve().parent.parent
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        from court_locator.dagalin_page_parse import parse_dagalin_detail_html

        parsed = parse_dagalin_detail_html(html, url)
        cc = parsed.get("court_card") or {}
        name = cc.get("name") or ""
        addr = cc.get("address") or ""
        email = cc.get("email") or ""
        phone = cc.get("phone") or ""
        schedule = cc.get("schedule") or ""
        section_numbers = list(cc.get("section_numbers") or [])
        boundary = cc.get("boundary_snippet") or ""

        jur = parsed.get("jurisdiction_html_report")
        results.append(
            ScrapeResult(
                name=name,
                address=addr,
                phone=phone,
                email=email,
                schedule=schedule,
                section_numbers=section_numbers,
                boundary_snippet=boundary,
                source_url=url,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                dagalin_detail=parsed,
                jurisdiction_html_report=jur if isinstance(jur, dict) else None,
            )
        )
        return results

    # List page: multiple h2 entries, use following paragraph as boundary text
    for h in soup.find_all(["h2", "h3"]):
        name = clean_text(h.get_text())
        if not name or "мировой судебный участок" not in name.lower():
            continue
        boundary = ""
        # find next sibling text block
        nxt = h.find_next_sibling()
        while nxt and boundary == "":
            if hasattr(nxt, "get_text"):
                candidate = clean_text(nxt.get_text())
                if candidate:
                    boundary = candidate
                    break
            nxt = nxt.find_next_sibling()
        section_numbers = []
        for m in SECTION_RE.finditer(name):
            section_numbers.append(m.group(1))
        section_numbers = sorted(set(section_numbers))
        jur = None
        try:
            _root = Path(__file__).resolve().parent.parent
            if str(_root) not in sys.path:
                sys.path.insert(0, str(_root))
            from court_locator.html_jurisdiction_status import analyze_territorial_jurisdiction_html, report_to_dict

            jur = report_to_dict(analyze_territorial_jurisdiction_html(html, url))
        except Exception:
            pass
        results.append(
            ScrapeResult(
                name=name,
                address="",
                phone="",
                email="",
                schedule="",
                section_numbers=section_numbers,
                boundary_snippet=boundary,
                source_url=url,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                jurisdiction_html_report=jur,
            )
        )
    return results


def save_results(results: List[ScrapeResult], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    json_path = out_dir / f"court_sites_scrape_{ts}.json"
    csv_path = out_dir / f"court_sites_scrape_{ts}.csv"
    data = [asdict(r) for r in results]
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # CSV
    import csv

    if data:
        csv_rows = []
        for row in data:
            r = dict(row)
            if isinstance(r.get("dagalin_detail"), (dict, list)):
                r["dagalin_detail"] = json.dumps(r["dagalin_detail"], ensure_ascii=False)
            if isinstance(r.get("jurisdiction_html_report"), dict):
                r["jurisdiction_html_report"] = json.dumps(r["jurisdiction_html_report"], ensure_ascii=False)
            csv_rows.append(r)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)
    return json_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Polite scraper for court sites (no geocoder).")
    parser.add_argument("--seeds", type=Path, default=Path("config/court_sites_seeds.json"), help="Path to JSON list of seed URLs.")
    parser.add_argument("--seed", action="append", help="Seed URL (can be repeated).")
    parser.add_argument("--min-delay", type=float, default=DEFAULT_MIN_DELAY, help="Min delay between requests per domain, seconds.")
    parser.add_argument("--max-seeds", type=int, default=10, help="Limit number of seeds to process (for debug).")
    parser.add_argument("--log", choices=["debug", "info", "warn"], default="info", help="Log verbosity.")
    parser.add_argument("--insecure", action="store_true", help="Skip SSL verification (use only if certificates are invalid).")
    args = parser.parse_args()

    seeds: List[str] = []
    seeds += load_seeds(args.seeds)
    if args.seed:
        seeds += args.seed
    seeds = [s.strip() for s in seeds if s and s.strip()]
    seeds = sorted(set(seeds))
    if args.max_seeds and len(seeds) > args.max_seeds:
        seeds = seeds[: args.max_seeds]
    if not seeds:
        print("No seeds provided. Add URLs via --seed or config/court_sites_seeds.json")
        return

    rp_cache: dict[str, RobotFileParser] = {}
    last_time: dict[str, float] = defaultdict(float)
    results: List[ScrapeResult] = []

    for url in seeds:
        html = fetch(url, last_time, rp_cache, log_level=args.log, insecure_ssl=args.insecure)
        if not html:
            continue
        parsed = urlparse(url)
        if "dagalin.org" in parsed.netloc:
            extracted = extract_dagalin(html, url)
            results.extend(extracted)
        else:
            res = extract_fields(html, url)
            results.append(res)

    out = save_results(results, Path("batch_outputs"))
    print(f"Saved {len(results)} items to {out}")


if __name__ == "__main__":
    main()
