"""
Единый клиент ФССП (банк данных исполнительных производств).

Ключ берётся из конфига: FSSP_API_KEY в .env / окружении. В код не коммитится.
Таймаут и лимиты — через parser/fssp_config.py (FSSP_TIMEOUT, FSSP_MAX_REQUESTS_PER_MINUTE).
Официальный API ФССП — по договору; коммерческие прокладки (parser-api, apiportal и т.д.) — отдельно.

Используется в: supreme_turbo, supreme_parser, anti_hallucination.
"""
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# База URL и имя переменной ключа (дублируем для независимости от fssp_config при импорте)
FSSP_API_BASE = os.getenv("FSSP_API_BASE", "https://api.fssp.gov.ru")
FSSP_API_KEY_ENV = "FSSP_API_KEY"


def _default_timeout() -> int:
    """Таймаут по умолчанию из конфига (см. fssp_config.FSSPConfig)."""
    try:
        from fssp_config import get_fssp_timeout
        return get_fssp_timeout()
    except ImportError:
        try:
            from parser.fssp_config import get_fssp_timeout
            return get_fssp_timeout()
        except ImportError:
            return int(os.getenv("FSSP_TIMEOUT", "30"))


def get_fssp_api_key() -> Optional[str]:
    """Единая точка: ключ ФССП из окружения (.env). Не коммитить в репозиторий."""
    return (os.getenv(FSSP_API_KEY_ENV) or os.getenv("FSSP_TOKEN") or "").strip() or None


def _headers() -> Dict[str, str]:
    """Заголовки запроса к ФССП; при наличии ключа — Authorization."""
    h = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    key = get_fssp_api_key()
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


async def search_by_ip(
    ip: str,
    session: Any,
    *,
    api_key: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Поиск по номеру исполнительного производства.
    Возвращает dict: ip, status, debtor, amount, court, source (или error).

    :param ip: номер ИП (цифры)
    :param session: aiohttp.ClientSession
    :param api_key: переопределение ключа (иначе из get_fssp_api_key())
    :param timeout: таймаут запроса в секундах (по умолчанию из FSSP_TIMEOUT / fssp_config)
    """
    if timeout is None:
        timeout = _default_timeout()
    ip_clean = (ip or "").strip()
    if not ip_clean:
        return {"ip": "", "status": "ошибка", "amount": 0, "source": "error"}
    import re
    ip_clean = re.sub(r"\D", "", ip_clean)
    if len(ip_clean) < 7 or len(ip_clean) > 15:
        return {"ip": ip, "status": "ошибка", "amount": 0, "source": "error"}

    url = f"{FSSP_API_BASE.rstrip('/')}/ip/{ip_clean}"
    headers = _headers()
    if api_key:
        headers = {**headers, "Authorization": f"Bearer {api_key}"}

    try:
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                text = ""
                try:
                    text = (await resp.text())[:500]
                except Exception:
                    pass
                logger.debug("ФССП ИП %s: HTTP %s %s", ip_clean, resp.status, text)
                return {"ip": ip_clean, "status": "ошибка", "amount": 0, "source": "error"}

            raw = await resp.text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return {"ip": ip_clean, "status": "ошибка", "amount": 0, "source": "error"}

            return {
                "ip": ip_clean,
                "status": data.get("phase", data.get("status", "не_известно")),
                "debtor": data.get("debtor_name", data.get("debtor", "")),
                "amount": float(data.get("sum_execution", data.get("sum", data.get("amount", 0)))),
                "court": data.get("court_name", data.get("court", "")),
                "source": "fssp",
            }
    except Exception as e:
        logger.debug("FSSP search_by_ip: %s", e)
        return {"ip": ip_clean, "status": "ошибка", "amount": 0, "source": "error"}


async def verify_ip_exists(ip: str, session: Any, *, timeout: Optional[int] = None) -> bool:
    """Проверка существования ИП в ФССП (для анти-галлюцинаций). Возвращает True при 200."""
    ip_clean = (ip or "").strip()
    if not ip_clean:
        return True
    import re
    ip_clean = re.sub(r"\D", "", ip_clean)
    if len(ip_clean) < 7 or len(ip_clean) > 15:
        return False
    if timeout is None:
        timeout = _default_timeout()
    url = f"{FSSP_API_BASE.rstrip('/')}/ip/{ip_clean}"
    try:
        async with session.get(url, headers=_headers(), timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return True
