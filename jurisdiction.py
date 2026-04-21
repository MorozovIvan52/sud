"""
Определение подсудности (docs/jurisdiction_conclusion.md):
  1) Суд по адресу: DaData (если DADATA_TOKEN) или Yandex Geocoder + БД судов (YANDEX_GEO_KEY)
  2) код паспорта + район → репозиторий судов
  3) адрес + район → репозиторий судов
  4) парсинг ГАС по ФИО (sudrf_scraper)
  5) fallback
Применение ст. 28 и ст. 30 ГПК РФ (исключительная подсудность) — court_locator.gpk_articles.
Репозиторий: COURTS_DB_BACKEND=sqlite|postgres.
"""
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

# Для импорта court_locator при запуске из parser/
_jurisdiction_dir = Path(__file__).resolve().parent
if str(_jurisdiction_dir.parent) not in sys.path:
    sys.path.insert(0, str(_jurisdiction_dir.parent))

from passport_parser import parse_passport_code
from address_parser import parse_address
from courts_repo import CourtsRepository
from courts_sqlite import SqliteCourtsRepository
from sudrf_scraper import sudrf_search_as_court_result, CaptchaRequired
from dadata_api import find_court_by_address as dadata_find_court


@dataclass
class CourtResult:
    court_name: str
    address: str
    index: str
    jurisdiction_type: str
    gpk_article: str
    source: str  # "dadata", "address_geo", "passport_code", "address", "fio_sudrf", "fallback_rule"
    court_region: str = ""
    section_num: int = 0


def get_repo() -> CourtsRepository:
    backend = os.getenv("COURTS_DB_BACKEND", "sqlite")
    if backend == "postgres":
        from courts_postgres import PostgresCourtsRepository
        return PostgresCourtsRepository()
    return SqliteCourtsRepository()


def _fallback_court(region: Optional[str]) -> CourtResult:
    court_name = "Районный суд по месту жительства ответчика"
    court_address = "Адрес районного суда необходимо уточнить вручную"
    postal_index = ""
    try:
        from court_locator.gpk_articles import GPK_ARTICLE_28
        gpk = GPK_ARTICLE_28
    except ImportError:
        gpk = "ст. 28 ГПК РФ"
    return CourtResult(
        court_name=court_name,
        address=court_address,
        index=postal_index,
        jurisdiction_type="по месту жительства ответчика",
        gpk_article=gpk,
        source="fallback_rule",
        court_region=region or "",
        section_num=0,
    )


def _court_row_to_result(court: Dict[str, Any], source: str) -> CourtResult:
    section = court.get("section_num")
    if section is None:
        section = 0
    else:
        try:
            section = int(section)
        except (TypeError, ValueError):
            section = 0
    try:
        from court_locator.gpk_articles import get_gpk_article
        gpk = get_gpk_article(case_type=court.get("case_type"), is_exclusive=court.get("is_exclusive_jurisdiction"))
    except ImportError:
        gpk = "ст. 28 ГПК РФ"
    return CourtResult(
        court_name=court.get("court_name") or "",
        address=court.get("address") or "",
        index=court.get("postal_index") or "",
        jurisdiction_type="по месту жительства ответчика",
        gpk_article=gpk,
        source=source,
        court_region=court.get("region") or "",
        section_num=section,
    )


def determine_jurisdiction(data: Dict[str, Any]) -> CourtResult:
    """
    data = {
      'fio': ...,
      'passport': ...,
      'issued_by': ...,
      'address': ...,
      'debt_amount': ...,
      'contract_date': ...
    }
    Порядок:
    1) Суд по адресу: DaData (если задан DADATA_TOKEN) или Yandex Geocoder + БД судов (при YANDEX_GEO_KEY)
    2) код паспорта + район → БД судов
    3) адрес + район → БД судов
    4) парсинг ГАС по ФИО (sudrf_scraper)
    5) fallback
    """
    repo = get_repo()
    repo.init_schema()

    passport = data.get("passport", "")
    address = data.get("address", "")

    passport_info = parse_passport_code(passport)
    addr_info = parse_address(address)

    region_from_passport = passport_info.get("region_name")
    region_from_address = addr_info.get("region")
    region = region_from_address or region_from_passport

    # 1. Суд по адресу: DaData (если есть токен) или Yandex Geocoder + БД судов (обход DaData)
    if address:
        dadata_token = (os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or "").strip()
        if dadata_token:
            court = dadata_find_court(address, region=region, token=dadata_token)
            if court and court.get("court_name"):
                return _court_row_to_result(court, "dadata")
        # Без DaData: адрес → геокод (Yandex) → ближайший суд из БД (courts_geo / courts)
        # Тот же каскад имён, что в court_locator.config (не только YANDEX_GEO_KEY)
        _yandex_geo = (os.getenv("YANDEX_GEO_KEY") or os.getenv("YANDEX_GEOCODER_API_KEY") or "").strip()
        if not _yandex_geo:
            _yandex_geo = (os.getenv("YANDEX_LOCATOR_API_KEY") or os.getenv("YANDEX_LOCATOR_KEY") or "").strip()
        if _yandex_geo:
            try:
                from geo_court_parser import YandexGeoParser
                geo = YandexGeoParser()
                geo_result = geo.super_find_court("", address, None)
                if geo_result:
                    return CourtResult(
                        court_name=geo_result.court_name,
                        address=geo_result.court_address,
                        index=geo_result.court_index or "",
                        jurisdiction_type="по месту жительства ответчика",
                        gpk_article="ст. 28 ГПК РФ",
                        source="address_geo",
                        court_region=geo_result.region or "",
                        section_num=geo_result.section_num,
                    )
            except Exception:
                pass

    # 2. По коду подразделения паспорта + району
    if region_from_passport and addr_info.get("district"):
        court = repo.get_court_by_district(region_from_passport, addr_info["district"])
        if court:
            return _court_row_to_result(court, "passport_code")

    # 3. По адресу регистрации (регион + район из парсера адреса)
    if region_from_address and addr_info.get("district"):
        court = repo.get_court_by_district(region_from_address, addr_info["district"])
        if court:
            return _court_row_to_result(court, "address")

    # 4. Бесплатный парсинг ГАС по ФИО (sudrf_scraper). При капче — не используем ГАС, идём в fallback
    fio = data.get("fio", "").strip()
    if fio:
        try:
            court = sudrf_search_as_court_result(fio, region=region)
        except CaptchaRequired:
            court = None
        if court:
            return CourtResult(
                court_name=court["court_name"],
                address=court["address"],
                index=court.get("postal_index") or "",
                jurisdiction_type="по месту жительства ответчика",
                gpk_article="ст. 28 ГПК РФ",
                source="fio_sudrf",
                court_region=region or "",
                section_num=0,
            )

    # 5. Fallback
    return _fallback_court(region)
