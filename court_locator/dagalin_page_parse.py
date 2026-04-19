"""
Парсинг карточки мирового суда на dagalin.org (детальная страница /courts/.../wc/...):
суд, вышестоящий суд, реквизиты госпошлины, отдел судебных приставов.

Используется скрапером и скриптом загрузки detail_json в dagalin_mirovye_courts.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from bs4 import BeautifulSoup


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _iter_table_rows(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        key = _clean(cells[0].get_text())
        val = _clean(cells[1].get_text())
        if key and val:
            pairs.append((key, val))
    return pairs


def _classify_label(key_lower: str) -> str:
    """Возвращает категорию строки: court | superior | fssp | requisites | ignore."""
    if any(
        x in key_lower
        for x in (
            "инн",
            "кпп",
            "октмо",
            "бик",
            "уфк",
            "кбк",
            "р/с",
            "р/c",
            "рс ",
            "расчётный",
            "расчетный",
            "получатель платежа",
            "получатель",
            "госпошлин",
            "реквизит для оплаты",
            "реквизиты для оплаты",
            "банк получателя",
        )
    ):
        if "вышестоящ" in key_lower or "вышест" in key_lower:
            return "superior_req"
        if "пристав" in key_lower or "осп" in key_lower or "фссп" in key_lower:
            return "fssp_req"
        return "requisites"

    if any(
        x in key_lower
        for x in (
            "вышестоящ",
            "районный суд",
            "городской суд",
            "наименование суда вышестоящ",
            "адрес вышестоящ",
            "телефон вышестоящ",
            "e-mail вышестоящ",
            "email вышестоящ",
            "сайт вышестоящ",
        )
    ):
        return "superior"

    if any(
        x in key_lower
        for x in (
            "отдел судебных пристав",
            "отдела судебных пристав",
            "фссп",
            "приставов по",
        )
    ) or key_lower.startswith("осп ") or key_lower.startswith("осп,"):
        if "инн" in key_lower or "кпп" in key_lower or "бик" in key_lower:
            return "fssp_req"
        return "fssp"

    return "court"


def _fill_superior(bucket: Dict[str, str], key_lower: str, val: str) -> None:
    if "наименование" in key_lower or (
        "вышестоящ" in key_lower and "суд" in key_lower and "адрес" not in key_lower
    ):
        bucket["name"] = val
    elif "адрес" in key_lower:
        bucket["address"] = val
    elif "телефон" in key_lower or key_lower.startswith("тел."):
        bucket["phone"] = val
    elif "e-mail" in key_lower or "email" in key_lower or "эл." in key_lower:
        bucket["email"] = val
    elif "сайт" in key_lower:
        bucket["website"] = val
    else:
        prev = bucket.get("notes") or ""
        bucket["notes"] = (prev + "; " if prev else "") + f"{key_lower}: {val}"


def _fill_fssp(bucket: Dict[str, str], key_lower: str, val: str) -> None:
    if "наименование" in key_lower or ("отдел" in key_lower and "пристав" in key_lower):
        bucket["name"] = val
    elif "адрес" in key_lower:
        bucket["address"] = val
    elif "телефон" in key_lower or key_lower.startswith("тел."):
        bucket["phone"] = val
    elif "e-mail" in key_lower or "email" in key_lower or "эл." in key_lower:
        bucket["email"] = val
    else:
        prev = bucket.get("notes") or ""
        bucket["notes"] = (prev + "; " if prev else "") + f"{key_lower}: {val}"


def _norm_req_key(key_lower: str) -> str:
    k = key_lower.replace("ё", "е")
    if "инн" in k:
        return "inn"
    if "кпп" in k:
        return "kpp"
    if "октмо" in k:
        return "oktmo"
    if "бик" in k:
        return "bik"
    if "кбк" in k:
        return "kbk"
    if "уфк" in k:
        return "ufk_name"
    if "р/с" in k or "р/c" in k or "расчет" in k or "расчёт" in k:
        return "bank_account"
    if "банк" in k and "получ" not in k:
        return "bank_name"
    if "получатель" in k:
        return "recipient"
    if "госпошлин" in k:
        return "state_fee_note"
    return "extra_" + re.sub(r"\W+", "_", k[:40]).strip("_")


def parse_dagalin_detail_html(html: str, url: str) -> Dict[str, Any]:
    """
    Разбор HTML карточки участка dagalin.
    Возвращает структуру для JSON в dagalin_mirovye_courts.detail_json и для скрапера.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    pairs = _iter_table_rows(soup)
    full_text = _clean(soup.get_text(" "))

    court: Dict[str, str] = {}
    superior: Dict[str, str] = {}
    fssp: Dict[str, str] = {}
    requisites: Dict[str, str] = {}

    court_labels = {
        "адрес": "address",
        "e-mail": "email",
        "e-mail:": "email",
        "телефон": "phone",
        "телефон судебного участка": "phone",
        "телефон для справок": "phone",
        "режим работы": "schedule",
    }

    for key, val in pairs:
        kl = key.lower().strip().strip(":")
        cat = _classify_label(kl)
        if cat == "requisites" or cat == "superior_req":
            if cat == "superior_req":
                _fill_superior(superior, kl, val)
            else:
                nk = _norm_req_key(kl)
                if nk.startswith("extra_") and nk in requisites:
                    requisites[nk] = requisites[nk] + "; " + val
                else:
                    requisites[nk] = val
        elif cat == "fssp_req":
            nk = _norm_req_key(kl)
            requisites["fssp_" + nk] = val
        elif cat == "superior":
            _fill_superior(superior, kl, val)
        elif cat == "fssp":
            _fill_fssp(fssp, kl, val)
        else:
            if kl in court_labels:
                court[court_labels[kl]] = val
            elif kl == "телефон:" and "phone" not in court:
                court["phone"] = val

    name = ""
    h1 = soup.find("h1")
    if h1:
        name = _clean(h1.get_text())
    if not name:
        t = soup.find("title")
        if t:
            name = _clean(t.get_text())

    boundary = ""
    best_len = 0
    for cell in soup.find_all(["td", "th", "p", "div"]):
        ctext = _clean(cell.get_text())
        low = ctext.lower()
        if "территориальн" in low and "подсудн" in low:
            if len(ctext) > best_len:
                boundary = ctext
                best_len = len(ctext)
    if not boundary and "территориальн" in full_text.lower():
        boundary = full_text

    section_numbers: List[str] = []
    for m in re.finditer(
        r"(?:участк[а-я]*|миров[а-я\s]+суд[а-я]*).*?(\d{1,3})", (name or full_text), re.IGNORECASE
    ):
        section_numbers.append(m.group(1))
    section_numbers = sorted(set(section_numbers))

    # Убрать пустые блоки
    def strip_empty(d: Dict[str, str]) -> Dict[str, str]:
        return {k: v for k, v in d.items() if v and str(v).strip()}

    superior_c = strip_empty(superior)
    fssp_c = strip_empty(fssp)
    req_c = strip_empty(requisites)

    try:
        from court_locator.html_jurisdiction_status import analyze_territorial_jurisdiction_html, report_to_dict

        jur_rep = report_to_dict(analyze_territorial_jurisdiction_html(html, url))
    except Exception:
        jur_rep = {"status": "error", "reasons": ["jurisdiction_html_report: вспомогательный разбор не выполнен"]}

    return {
        "source_url": url,
        "court_card": {
            "name": name,
            "address": court.get("address", ""),
            "phone": court.get("phone", ""),
            "email": court.get("email", ""),
            "schedule": court.get("schedule", ""),
            "section_numbers": section_numbers,
            "boundary_snippet": boundary,
        },
        "jurisdiction_html_report": jur_rep,
        "superior_court": superior_c or None,
        "bailiffs": fssp_c or None,
        "state_fee_requisites": req_c or None,
    }


def dagalin_detail_to_json_str(parsed: Dict[str, Any]) -> str:
    """Компактная JSON-строка для SQLite (только непустые блоки обогащения)."""
    payload: Dict[str, Any] = {}
    for k in ("superior_court", "state_fee_requisites", "bailiffs"):
        v = parsed.get(k)
        if isinstance(v, dict) and v:
            payload[k] = v
    if not payload:
        return ""
    return json.dumps(payload, ensure_ascii=False)
