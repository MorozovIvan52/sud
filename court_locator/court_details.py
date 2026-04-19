"""
Сбор подробных сведений по найденному суду (46 полей) для записи в Excel.
Поиск по GPS → суд → заполнение полей из БД и parser (реквизиты, КБК, госпошлина).
Поля, которых нет в БД (ОСП, ИФНС, банк и т.д.), остаются пустыми или со ссылкой на реквизиты.
Соответствие заключению (docs/jurisdiction_conclusion.md): ФИАС, геокодирование, ст. 28/30 ГПК, границы, ручная верификация.
"""
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Человекочитаемые метки источников данных (docs/jurisdiction_verification_sources.md)
SOURCE_LABELS: Dict[str, str] = {
    "postgis": "PostGIS (границы участков)",
    "court_districts": "Полигоны участков (court_districts)",
    "coordinates_district": "Обратное геокодирование + район",
    "courts_nearest": "Ближайший суд (courts)",
    "courts_geo": "Ближайший суд (courts_geo)",
    "address_district": "Парсинг адреса (регион, район)",
    "dadata": "DaData API",
    "unified_A_district": "Парсинг адреса (регион, район) [unified]",
    "unified_B_dadata": "DaData API [unified]",
    "unified_C_postgis": "PostGIS [unified]",
}

try:
    from court_locator.gpk_articles import get_gpk_article, GPK_ARTICLE_28
except ImportError:
    GPK_ARTICLE_28 = "ст. 28 ГПК РФ"

    def get_gpk_article(case_type: str = None, is_exclusive: bool = False) -> str:
        return GPK_ARTICLE_28

# Порядок и названия колонок для Excel (подробный список сведений)
COURT_DETAIL_COLUMNS: List[str] = [
    "Нормализованный адрес",
    "Уровень достоверности",
    "Требует проверки",
    "Уровень обработки",
    "Тип производства",
    "Наименование суда",
    "Код суда",
    "Адрес суда",
    "e-mail суда",
    "Телефон суда",
    "Сайт суда",
    "Госпошлина, руб.",
    "ID Отдела судебных приставов (ОСП)",
    "Код ОСП",
    "Наименование ОСП",
    "Адрес ОСП",
    "Телефон ОСП",
    "Эл. адрес ОСП",
    "УФК",
    "ОКТМО",
    "ИНН",
    "КПП",
    "Счет",
    "БИК",
    "КБК",
    "Банк",
    "Код ИФНС",
    "Сайт ИФНС",
    "Телефон ИФНС",
    "Адрес ИФНС",
    "Наименование вышестоящего суда",
    "Код вышестоящего суда",
    "Адрес вышестоящего суда",
    "Email вышестоящего суда",
    "Телефон вышестоящего суда",
    "Сайт вышестоящего суда",
    "УФК вышестоящего суда",
    "ОКТМО вышестоящего суда",
    "ИНН вышестоящего суда",
    "КПП вышестоящего суда",
    "Счет вышестоящего суда",
    "КБК вышестоящего суда",
    "БИК вышестоящего суда",
    "Банк вышестоящего суда",
    "Код ИФНС вышестоящего суда",
    "Сайт ИФНС вышестоящего суда",
    "Телефон ИФНС вышестоящего суда",
    "Адрес ИФНС вышестоящего суда",
    "Источник данных",
]


def _get_region_code_and_urls(region: str, section_num: int) -> Dict[str, str]:
    """Код региона и ссылки на реквизиты/сайт суда (parser)."""
    try:
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        sys.path.insert(0, str(root / "parser"))
        from regions_rf import get_region_code, get_rekvizity_urls
        code = get_region_code(region)
        urls = get_rekvizity_urls(region, section_num or 0)
        return {
            "region_code": code,
            "rekvizity_url": urls.get("rekvizity_url", ""),
            "court_site": urls.get("court_site", ""),
        }
    except Exception:
        return {"region_code": "", "rekvizity_url": "", "court_site": ""}


def _state_duty(debt_amount: Optional[float]) -> str:
    """Госпошлина по сумме иска (parser)."""
    if debt_amount is None or debt_amount <= 0:
        return ""
    try:
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        sys.path.insert(0, str(root / "parser"))
        from super_parser import state_duty_from_debt
        return str(state_duty_from_debt(float(debt_amount)))
    except Exception:
        return ""


def build_court_details(
    court: Dict[str, Any],
    normalized_address: Optional[str] = None,
    debt_amount: Optional[float] = None,
    *,
    confidence: Optional[str] = None,
    needs_manual_review: Optional[bool] = None,
    processing_level: Optional[str] = None,
    case_type: Optional[str] = None,
) -> Dict[str, str]:
    """
    Собирает словарь из 45 полей по найденному суду.
    court — результат locate_court (court_name, address, region, phone, schedule, source, section_num, ...).
    Поля, которых нет в БД (ОСП, ИФНС, банковские реквизиты и т.д.), остаются пустыми.
    """
    region = (court.get("region") or "").strip()
    section_num = court.get("section_num")
    if section_num is not None:
        try:
            section_num = int(section_num)
        except (TypeError, ValueError):
            section_num = 0
    else:
        section_num = 0

    extra = _get_region_code_and_urls(region, section_num)
    region_code = extra.get("region_code", "")
    rekvizity_url = extra.get("rekvizity_url", "")
    court_site = extra.get("court_site", "")

    court_name = court.get("court_name") or ""
    court_address = court.get("address") or ""
    phone = court.get("phone") or ""
    email = court.get("email") or court.get("court_email") or ""
    duty_str = _state_duty(debt_amount)

    # КБК единый для госпошлины по ГПК (мировые суды)
    kbk = "18210803010011050110"

    # Реквизиты из справочника (parser/court_rekvizity, docs/analysis_molotok_junona_requisites.md)
    rekvizity = {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "parser"))
        from court_rekvizity import lookup_rekvizity
        rekvizity = lookup_rekvizity(region, section_num)
    except Exception:
        pass

    def empty_if(s: str, placeholder: str = "") -> str:
        return s if (s and s.strip()) else placeholder

    conf = confidence or court.get("confidence") or ""
    needs_review = needs_manual_review if needs_manual_review is not None else court.get("needs_manual_review", False)
    level = processing_level or court.get("processing_level") or ""
    gpk_article = get_gpk_article(case_type=court.get("case_type") or case_type)

    # Все 45 полей по порядку (включая реквизиты из справочника)
    return {
        "Нормализованный адрес": empty_if(normalized_address or ""),
        "Уровень достоверности": empty_if(conf),
        "Требует проверки": "Да" if needs_review else "",
        "Уровень обработки": empty_if(level),
        "Тип производства": f"Гражданское ({gpk_article})",
        "Наименование суда": empty_if(court_name),
        "Код суда": region_code + (str(section_num) if section_num else ""),
        "Адрес суда": empty_if(court_address),
        "e-mail суда": empty_if(email),
        "Телефон суда": empty_if(phone),
        "Сайт суда": empty_if(court_site),
        "Госпошлина, руб.": empty_if(duty_str),
        "ID Отдела судебных приставов (ОСП)": "",
        "Код ОСП": "",
        "Наименование ОСП": "",
        "Адрес ОСП": "",
        "Телефон ОСП": "",
        "Эл. адрес ОСП": "",
        "УФК": empty_if(rekvizity.get("УФК", "")),
        "ОКТМО": empty_if(rekvizity.get("ОКТМО", "")),
        "ИНН": empty_if(rekvizity.get("ИНН", "")),
        "КПП": empty_if(rekvizity.get("КПП", "")),
        "Счет": empty_if(rekvizity.get("Счет", "")),
        "БИК": empty_if(rekvizity.get("БИК", "")),
        "КБК": empty_if(kbk),
        "Банк": empty_if(rekvizity.get("Банк", "")),
        "Код ИФНС": "",
        "Сайт ИФНС": "",
        "Телефон ИФНС": "",
        "Адрес ИФНС": "",
        "Наименование вышестоящего суда": "",
        "Код вышестоящего суда": "",
        "Адрес вышестоящего суда": "",
        "Email вышестоящего суда": "",
        "Телефон вышестоящего суда": "",
        "Сайт вышестоящего суда": "",
        "УФК вышестоящего суда": "",
        "ОКТМО вышестоящего суда": "",
        "ИНН вышестоящего суда": "",
        "КПП вышестоящего суда": "",
        "Счет вышестоящего суда": "",
        "КБК вышестоящего суда": "",
        "БИК вышестоящего суда": "",
        "Банк вышестоящего суда": "",
        "Код ИФНС вышестоящего суда": "",
        "Сайт ИФНС вышестоящего суда": "",
        "Телефон ИФНС вышестоящего суда": "",
        "Адрес ИФНС вышестоящего суда": "",
        "Источник данных": empty_if(SOURCE_LABELS.get(court.get("source", "") or "", "")),
    }
