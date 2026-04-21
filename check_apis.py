"""
Проверка всех подключённых API: доступность и корректность ответа.

Запуск из корня проекта или из parser/:
  python parser/check_apis.py
  cd parser && python check_apis.py

Требуется: .env в корне (или переменные окружения). Ключи в вывод не печатаются.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Загрузка .env из корня проекта
def _load_dotenv():
    root = Path(__file__).resolve().parent.parent
    env_file = root / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            pass


def _has(key: str, alt: str | None = None) -> bool:
    v = (os.getenv(key) or (os.getenv(alt) if alt else "") or "").strip()
    return bool(v)


def check_fssp() -> tuple[bool, str]:
    """ФССП: ключ есть и запрос к API возвращает ответ (не исключение)."""
    if not _has("FSSP_API_KEY", "FSSP_TOKEN"):
        return False, "ключ не задан (FSSP_API_KEY / FSSP_TOKEN)"
    base = os.getenv("FSSP_API_BASE", "https://api.fssp.gov.ru").rstrip("/")
    key = os.getenv("FSSP_API_KEY") or os.getenv("FSSP_TOKEN") or ""

    async def _request():
        try:
            import aiohttp
            url = f"{base}/ip/12345678"
            headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=15) as resp:
                    # 200 = ок, 404/400 = ИП не найден (API доступен)
                    if resp.status in (200, 404, 400):
                        body = await resp.text()
                        return True, f"HTTP {resp.status}, ответ получен"
                    return False, f"HTTP {resp.status}"
        except asyncio.TimeoutError:
            return False, "таймаут"
        except Exception as e:
            return False, str(e)[:80]

    try:
        ok, msg = asyncio.run(_request())
        return ok, msg
    except Exception as e:
        return False, str(e)[:80]


def check_yandex_geocoder() -> tuple[bool, str]:
    """Yandex Geocoder: по адресу возвращаются координаты."""
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from court_locator import config as clc

        key = clc.YANDEX_GEO_KEY
        src = f"{clc.YANDEX_GEO_KEY_SOURCE}<-{clc.YANDEX_GEO_KEY_ENV or '-'}"
    except Exception:
        key = ""
        src = "?<-?"
    if not key:
        hint = ""
        if (os.getenv("YANDEX_API_KEY") or "").strip():
            hint = " | подсказка: YANDEX_API_KEY не используется для geocode-maps — см. court_locator.config"
        if (os.getenv("YANDEX_LOCATOR_API_KEY") or os.getenv("YANDEX_LOCATOR_KEY") or "").strip() and not (
            os.getenv("YANDEX_GEO_KEY") or os.getenv("YANDEX_GEOCODER_API_KEY")
        ).strip():
            hint += " | активен только LOCATOR-ключ (см. диагностику после исправления .env)"
        return False, f"ключ не задан для ГеокодераHTTP ({src}){hint}"
    try:
        import requests
        url = "https://geocode-maps.yandex.ru/1.x/"
        params = {"apikey": key, "geocode": "Москва", "format": "json", "results": 1}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        members = data.get("response", {}).get("GeoObjectCollection", {}).get("featureMember", [])
        if not members:
            return False, "пустой ответ (нет featureMember)"
        pos = members[0].get("GeoObject", {}).get("Point", {}).get("pos")
        if not pos:
            return False, "нет координат в ответе"
        lon, lat = map(float, pos.split())
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return True, f"координаты получены (lat={lat:.4f}, lon={lon:.4f}) [источник: {src}]"
        return False, "некорректные координаты"
    except Exception as e:
        return False, str(e)[:80]


def check_gas_sudrf() -> tuple[bool, str]:
    """ГАС Правосудие: доступность сайта и запрос по ФИО без капчи."""
    try:
        import requests
        url = "https://bsr.sudrf.ru/bigs/common.html"
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ParserSudPro-Check)"}, timeout=15)
            r.raise_for_status()
        except requests.RequestException as e:
            return False, f"сайт недоступен: {str(e)[:50]}"
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sudrf_scraper import sudrf_search, CaptchaRequired
        results = sudrf_search("Иванов Иван Иванович", region=None, max_results=3)
        if not isinstance(results, list):
            return False, "ответ не список"
        return True, f"сайт доступен, записей по ФИО: {len(results)}"
    except CaptchaRequired:
        return False, "в ответе капча (ГАС временно недоступна)"
    except Exception as e:
        return False, str(e)[:80]


def check_telegram() -> tuple[bool, str]:
    """Telegram Bot API: getMe возвращает бота."""
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        return False, "ключ не задан (BOT_TOKEN)"
    try:
        import requests
        url = f"https://api.telegram.org/bot{token}/getMe"
        r = requests.get(url, timeout=10)
        data = r.json()
        if not data.get("ok"):
            return False, data.get("description", "getMe failed")[:60]
        username = data.get("result", {}).get("username", "")
        return True, f"бот @{username}"
    except Exception as e:
        return False, str(e)[:80]


def check_redis() -> tuple[bool, str]:
    """Redis: пинг."""
    url = os.getenv("REDIS_URL")
    host = os.getenv("REDIS_HOST")
    if not url and not host:
        return False, "не задан (REDIS_URL / REDIS_HOST)"
    try:
        import redis
        if url:
            client = redis.from_url(url, decode_responses=True)
        else:
            port = int(os.getenv("REDIS_PORT", "6379"))
            client = redis.Redis(host=host, port=port, decode_responses=True)
        client.ping()
        return True, "ping OK"
    except ImportError:
        return False, "модуль redis не установлен"
    except Exception as e:
        return False, str(e)[:80]


def check_gigachat() -> tuple[bool, str]:
    """GigaChat: наличие учётных данных и один короткий запрос."""
    cred = (os.getenv("GIGACHAT_CREDENTIALS") or os.getenv("GIGACHAT_API_KEY") or "").strip()
    if not cred:
        return False, "не задан (GIGACHAT_CREDENTIALS / GIGACHAT_API_KEY)"
    try:
        from gigachat import GigaChat
        from gigachat.models import Chat, Messages, MessagesRole
        chat = Chat(messages=[Messages(role=MessagesRole.USER, content="Скажи одно слово: привет")])
        with GigaChat(credentials=cred, verify_ssl_certs=False) as client:
            resp = client.chat(chat)
        text = (resp.choices[0].message.content or "").strip()
        if text:
            return True, f"ответ получен ({len(text)} симв.)"
        return False, "пустой ответ"
    except ImportError:
        return False, "модуль gigachat не установлен"
    except Exception as e:
        return False, str(e)[:80]


def check_yandex_gpt() -> tuple[bool, str]:
    """Yandex GPT: ключ и folder_id заданы, один короткий completion."""
    key = (os.getenv("YANDEX_GPT_API_KEY") or os.getenv("YANDEX_API_KEY") or "").strip()
    folder = (os.getenv("YANDEX_GPT_CATALOG_ID") or os.getenv("YANDEX_FOLDER_ID") or "").strip()
    if not key:
        return False, "не задан YANDEX_GPT_API_KEY / YANDEX_API_KEY"
    if not folder:
        return False, "не задан YANDEX_GPT_CATALOG_ID / YANDEX_FOLDER_ID"
    try:
        import requests
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {key}", "x-folder-id": folder, "Content-Type": "application/json"}
        body = {
            "modelUri": f"gpt://{folder}/yandexgpt/latest",
            "completionOptions": {"stream": False, "temperature": 0.1, "maxTokens": "50"},
            "messages": [{"role": "user", "text": "Скажи одно слово: привет"}],
        }
        r = requests.post(url, json=body, headers=headers, timeout=30)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {(r.text or '')[:100]}"
        data = r.json()
        result = data.get("result", {}) or data
        alternatives = result.get("alternatives", [])
        if alternatives and isinstance(alternatives[0].get("message"), dict):
            text = alternatives[0]["message"].get("text", "")
        else:
            text = (alternatives[0] if alternatives else {}).get("text", "")
        if (text or "").strip():
            return True, f"ответ получен ({len(str(text))} симв.)"
        return False, "пустой ответ"
    except Exception as e:
        return False, str(e)[:80]


def check_2captcha() -> tuple[bool, str]:
    """2Captcha: getbalance возвращает число."""
    key = (os.getenv("TWOCAPTCHA_API_KEY") or os.getenv("CAPTCHA_API_KEY") or "").strip()
    if not key:
        return False, "не задан (TWOCAPTCHA_API_KEY / CAPTCHA_API_KEY)"
    try:
        import requests
        r = requests.get(
            "https://2captcha.com/res.php",
            params={"key": key, "action": "getbalance", "json": 1},
            timeout=10,
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if data.get("status") == 1:
            return True, f"баланс: {data.get('request', 0)}"
        return False, data.get("request", r.text or "ошибка")[:60]
    except Exception as e:
        return False, str(e)[:80]


def check_dadata() -> tuple[bool, str]:
    """DaData: подсказки по адресу (suggest/address) возвращают ответ."""
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from court_locator import config as clc

        token = clc.DADATA_TOKEN
        src = f"{clc.DADATA_TOKEN_SOURCE}<-{clc.DADATA_TOKEN_ENV or '-'}"
    except Exception:
        token = (os.getenv("DADATA_TOKEN") or os.getenv("DADATA_API_KEY") or "").strip()
        src = "?"
    if not token:
        return False, "ключ не задан (DADATA_TOKEN / DADATA_API_KEY)"
    try:
        import requests
        url = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
        r = requests.post(
            url,
            json={"query": "Москва Тверская", "count": 1},
            headers={"Authorization": f"Token {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        suggestions = data.get("suggestions") or []
        if not suggestions:
            return False, "пустой ответ (нет suggestions)"
        return True, f"ответ получен, подсказок: {len(suggestions)} [источник токена: {src}]"
    except Exception as e:
        return False, str(e)[:80]


def check_courts_db() -> tuple[bool, str]:
    """Локальная БД судов: схема есть, можно запросить суд по району."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from courts_db import init_db
        from courts_sqlite import SqliteCourtsRepository
        init_db()
        repo = SqliteCourtsRepository()
        repo.init_schema()
        court = repo.get_court_by_district("Москва", "Тверской")
        if court:
            return True, f"суд найден: {court.get('court_name', '')[:50]}"
        all_c = repo.get_all_courts()
        return True, f"БД доступна, записей: {len(all_c)}"
    except Exception as e:
        return False, str(e)[:80]


def main():
    _load_dotenv()

    checks = [
        ("DaData (DADATA_TOKEN)", check_dadata),
        ("Yandex Geocoder (YANDEX_GEO_KEY)", check_yandex_geocoder),
        ("ФССП (FSSP_API_KEY)", check_fssp),
        ("ГАС Правосудие (bsr.sudrf.ru)", check_gas_sudrf),
        ("Telegram Bot (BOT_TOKEN)", check_telegram),
        ("Redis", check_redis),
        ("GigaChat", check_gigachat),
        ("Yandex GPT", check_yandex_gpt),
        ("2Captcha", check_2captcha),
        ("БД судов (courts.sqlite)", check_courts_db),
    ]

    print("Проверка API\n" + "=" * 50)
    try:
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from court_locator import config as _clc

        diag = _clc.api_env_diagnostics()
        print(
            "  Диагностика env: yandex_geo="
            f"{diag['yandex_geo_key_source']}<-{diag['yandex_geo_key_env']}; "
            f"dadata_token={diag['dadata_token_source']}<-{diag['dadata_token_env']}; "
            f"dadata_secret={diag['dadata_secret_env'] or '-'}"
        )
        if diag.get("yandex_env_hint"):
            print(f"  [!] {diag['yandex_env_hint']}")
        if diag.get("dadata_env_hint"):
            print(f"  [!] {diag['dadata_env_hint']}")
        print("-" * 50)
    except Exception as e:
        print(f"  (диагностика court_locator недоступна: {e})")
        print("-" * 50)
    ok_count = 0
    for name, fn in checks:
        try:
            ok, msg = fn()
            status = "OK" if ok else "FAIL"
            if ok:
                ok_count += 1
            print(f"  [{status}] {name}: {msg}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
    print("=" * 50)
    print(f"Пройдено: {ok_count}/{len(checks)}")
    return 0 if ok_count == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
