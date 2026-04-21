# supreme_recaptcha.py — Supreme Anti-Captcha: ротация решателей, поведенческие эвристики, retry с экспонентой.
# Интеграция с anti_captcha; при наличии playwright — stealth + humanize.

import asyncio
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    requests = None


class CaptchaError(Exception):
    """Ошибка при решении капчи (повтор по smart_retry)."""
    pass


class MaxRetriesExceeded(Exception):
    """Исчерпано число попыток smart_retry."""
    pass


UA_POOL_SUPREME = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
if (window.chrome) window.chrome.runtime = { connect: function() {}, sendMessage: function() {} };
const orig = Error.prototype.toString;
Error.prototype.toString = function() { if (this.message && this.message.indexOf('Invocation') >= 0) return ''; return orig.call(this); };
"""

CANVAS_NOISE_SCRIPT = """
const orig = HTMLCanvasElement.prototype.toDataURL;
HTMLCanvasElement.prototype.toDataURL = function(type) {
    const ctx = this.getContext('2d');
    if (ctx && type === 'image/png') {
        try {
            const imgData = ctx.getImageData(0, 0, Math.min(this.width, 10), Math.min(this.height, 10));
            if (imgData && imgData.data) {
                for (let i = 0; i < imgData.data.length; i += 4) {
                    imgData.data[i] = Math.min(255, imgData.data[i] + (Math.random() * 2 - 1));
                }
                ctx.putImageData(imgData, 0, 0);
            }
        } catch (e) {}
    }
    return orig.apply(this, arguments);
};
"""

# Нормализация Canvas fingerprint через fillText (шум 0.1–0.5px по x)
CANVAS_FILLTEXT_NOISE = """
(function() {
    const origGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type) {
        const ctx = origGetContext.apply(this, arguments);
        if (type === '2d' && ctx) {
            const origFillText = ctx.fillText.bind(ctx);
            ctx.fillText = function(text, x, y, maxWidth) {
                const noise = (Math.random() * 0.5);
                if (arguments.length >= 4) origFillText(text, x + noise, y, maxWidth);
                else origFillText(text, x + noise, y);
            };
        }
        return ctx;
    };
})();
"""


async def smart_retry(
    func: Callable[[], Any],
    max_retries: int = 5,
    base_delay: float = 15.0,
    cap_delay: float = 300.0,
) -> Any:
    """Повтор с экспоненциальной задержкой и jitter. При CaptchaError — ждём и пробуем снова."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            result = await func()
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except CaptchaError as e:
            last_exc = e
            delay = min(cap_delay, (2 ** attempt) * base_delay + random.uniform(0, 10))
            logger.info("Retry %s/%s через %.0f с (CaptchaError)", attempt + 1, max_retries, delay)
            await asyncio.sleep(delay)
        except Exception as e:
            last_exc = e
            raise
    raise MaxRetriesExceeded(f"После {max_retries} попыток") from last_exc


class SupremeRecaptcha:
    """Ротация решателей (2captcha / anti-captcha), паузы, опционально stealth при наличии playwright."""

    SERVICE_2CAPTCHA = "2captcha"
    SERVICE_ANTICAPTCHA = "anticaptcha"
    SERVICE_CAPMONSTER = "capmonster"

    def __init__(
        self,
        api_key_2captcha: str = None,
        api_key_anticaptcha: str = None,
        api_key_capmonster: str = None,
        pageurl: str = "",
    ):
        self.api_keys = {
            self.SERVICE_2CAPTCHA: (api_key_2captcha or os.getenv("TWOCAPTCHA_API_KEY") or os.getenv("CAPTCHA_API_KEY") or "").strip(),
            self.SERVICE_ANTICAPTCHA: (api_key_anticaptcha or os.getenv("ANTICAPTCHA_API_KEY") or "").strip(),
            self.SERVICE_CAPMONSTER: (api_key_capmonster or os.getenv("CAPMONSTER_API_KEY") or "").strip(),
        }
        self.current_url = pageurl
        self.user_agents = list(UA_POOL_SUPREME)
        self._browser = None
        self._page = None
        self._playwright = None

    async def __aenter__(self) -> "SupremeRecaptcha":
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def smart_retry(
        self,
        func: Callable[[], Any],
        max_retries: int = 5,
        base_delay: float = 15.0,
        cap_delay: float = 300.0,
    ) -> Any:
        """Экспоненциальная задержка + jitter (15s, 30s, 60s, 120s, 240s + random 0–10s)."""
        return await smart_retry(func, max_retries=max_retries, base_delay=base_delay, cap_delay=cap_delay)

    def _get_page_url(self, page: Any) -> str:
        if hasattr(page, "url"):
            return getattr(page, "url", "") or self.current_url
        return self.current_url

    async def ml_predict_recaptcha(self, page: Any) -> Optional[str]:
        """Заглушка ML-предсказания (без модели → None → идём в сервис)."""
        return None

    def _submit_2captcha(self, site_key: str, page_url: str) -> Optional[str]:
        if not self.api_keys[self.SERVICE_2CAPTCHA] or not requests:
            return None
        try:
            r = requests.post(
                "https://2captcha.com/in.php",
                data={
                    "key": self.api_keys[self.SERVICE_2CAPTCHA],
                    "method": "userrecaptcha",
                    "googlekey": site_key,
                    "pageurl": page_url,
                },
                timeout=15,
            )
            text = (r.text or "").strip()
            if "OK|" in text:
                return text.split("|", 1)[-1].strip()
            logger.warning("2captcha submit: %s", text)
        except Exception as e:
            logger.debug("2captcha submit: %s", e)
        return None

    def _get_2captcha_result(self, request_id: str, max_wait: int = 120, poll_interval: int = 5) -> Optional[str]:
        if not self.api_keys[self.SERVICE_2CAPTCHA] or not requests:
            return None
        for _ in range(max_wait // poll_interval):
            time.sleep(poll_interval)
            try:
                r = requests.get(
                    "https://2captcha.com/res.php",
                    params={"key": self.api_keys[self.SERVICE_2CAPTCHA], "action": "get", "id": request_id},
                    timeout=10,
                )
                text = (r.text or "").strip()
                if "CAPCHA_NOT_READY" in text:
                    continue
                if "OK|" in text:
                    return text.split("|", 1)[-1].strip()
                logger.warning("2captcha result: %s", text)
                return None
            except Exception as e:
                logger.debug("2captcha poll: %s", e)
        return None

    def _submit_anticaptcha(self, site_key: str, page_url: str) -> Optional[str]:
        if not self.api_keys[self.SERVICE_ANTICAPTCHA] or not requests:
            return None
        try:
            r = requests.post(
                "https://api.anti-captcha.com/createTask",
                json={
                    "clientKey": self.api_keys[self.SERVICE_ANTICAPTCHA],
                    "task": {
                        "type": "RecaptchaV2TaskProxyless",
                        "websiteURL": page_url,
                        "websiteKey": site_key,
                    },
                },
                timeout=15,
            )
            data = r.json() or {}
            if data.get("errorId") == 0 and data.get("taskId"):
                return str(data["taskId"])
            logger.warning("anticaptcha createTask: %s", data)
        except Exception as e:
            logger.debug("anticaptcha: %s", e)
        return None

    def _get_anticaptcha_result(self, task_id: str, max_wait: int = 120, poll_interval: int = 3) -> Optional[str]:
        if not self.api_keys[self.SERVICE_ANTICAPTCHA] or not requests:
            return None
        for _ in range(max_wait // poll_interval):
            time.sleep(poll_interval)
            try:
                r = requests.post(
                    "https://api.anti-captcha.com/getTaskResult",
                    json={"clientKey": self.api_keys[self.SERVICE_ANTICAPTCHA], "taskId": task_id},
                    timeout=10,
                )
                data = r.json() or {}
                if data.get("status") == "ready" and data.get("solution", {}).get("gRecaptchaResponse"):
                    return data["solution"]["gRecaptchaResponse"]
                if data.get("errorId") and data.get("errorId") != 0:
                    return None
            except Exception as e:
                logger.debug("anticaptcha getResult: %s", e)
        return None

    def _solve_via_service(self, site_key: str, page_url: str) -> Optional[str]:
        """Ротация: 2captcha → anticaptcha."""
        page_url = page_url or self.current_url or "https://sudrf.ru"
        services = []
        if self.api_keys[self.SERVICE_2CAPTCHA]:
            rid = self._submit_2captcha(site_key, page_url)
            if rid:
                services.append(("2captcha", lambda: self._get_2captcha_result(rid)))
        if self.api_keys[self.SERVICE_ANTICAPTCHA]:
            task_id = self._submit_anticaptcha(site_key, page_url)
            if task_id:
                services.append(("anticaptcha", lambda: self._get_anticaptcha_result(task_id)))
        random.shuffle(services)
        for name, get_result in services:
            token = get_result()
            if token:
                return token
        return None

    async def solve_recaptcha_v2(self, page: Any, site_key: str, page_url: str = "") -> Optional[str]:
        """ML-заглушка → ротация сервисов. Возвращает токен или raises CaptchaError."""
        page_url = page_url or self._get_page_url(page)
        predicted = await self.ml_predict_recaptcha(page)
        if predicted:
            return predicted
        token = self._solve_via_service(site_key, page_url)
        if not token:
            raise CaptchaError("Не удалось получить токен reCAPTCHA")
        return token

    async def inject_recaptcha_token(self, page: Any, token: str, textarea_selector: str = "textarea[name=g-recaptcha-response]") -> bool:
        try:
            if hasattr(page, "evaluate"):
                await page.evaluate(
                    f"""
                    (token) => {{
                        const el = document.querySelector('{textarea_selector}') || document.querySelector('[name="g-recaptcha-response"]');
                        if (el) {{ el.value = token; el.dispatchEvent(new Event('input', {{ bubbles: true }})); return true; }}
                        return false;
                    }}
                    """,
                    token,
                )
                return True
        except Exception as e:
            logger.debug("inject_recaptcha_token: %s", e)
        return False

    async def twocaptcha_solve(self, page: Any, site_key: str) -> str:
        """Ожидание 15–25 с + запрос токена + инъекция."""
        page_url = self._get_page_url(page)
        token = self._solve_via_service(site_key, page_url)
        if not token:
            raise CaptchaError("Сервис не вернул токен")
        await asyncio.sleep(random.uniform(15, 25))
        await self.inject_recaptcha_token(page, token)
        return token

    async def randomize_canvas(self, page: Any) -> None:
        if not hasattr(page, "evaluate"):
            return
        try:
            await page.evaluate(CANVAS_NOISE_SCRIPT)
            await page.evaluate(CANVAS_FILLTEXT_NOISE)
        except Exception as e:
            logger.debug("randomize_canvas: %s", e)

    async def humanize_behavior(self, page: Any) -> None:
        """Мышь (Bezier-like steps) + человеческий скролл: 3 раза 200–400px, пауза 0.5–1.5 с."""
        if hasattr(page, "mouse"):
            try:
                await page.mouse.move(
                    random.uniform(100, 400),
                    random.uniform(100, 400),
                    steps=random.randint(20, 40),
                )
            except Exception as e:
                logger.debug("humanize mouse: %s", e)
        if hasattr(page, "evaluate"):
            try:
                await asyncio.sleep(random.uniform(0.3, 0.8))
                for _ in range(3):
                    await page.evaluate(f"window.scrollBy(0, {random.randint(200, 400)})")
                    await asyncio.sleep(random.uniform(0.5, 1.5))
            except Exception as e:
                logger.debug("humanize scroll: %s", e)

    async def human_type(self, page: Any, selector: str, text: str, delay_min: int = 50, delay_max: int = 150) -> None:
        """Печать с микро-паузами 50–150 ms на символ (human-like typing)."""
        if not text:
            return
        try:
            if hasattr(page, "locator"):
                loc = page.locator(selector).first
                await loc.click()
            elif hasattr(page, "focus"):
                await page.focus(selector)
            if hasattr(page, "keyboard"):
                for char in text:
                    await page.keyboard.type(char, delay=random.randint(delay_min, delay_max))
            elif hasattr(page, "type"):
                await page.type(selector, text, delay=random.uniform(delay_min / 1000.0, delay_max / 1000.0))
        except Exception as e:
            logger.debug("human_type: %s", e)

    async def boost_trust_score(self, page: Any) -> None:
        """Поведенческий буст для ML (scroll + hover) — перед Turnstile/Captcha."""
        await self.humanize_behavior(page)

    @asynccontextmanager
    async def stealth_browser(self, headless: bool = True):
        """Требует playwright. Использование: async with solver.stealth_browser() as (browser, page):"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError("pip install playwright && playwright install chromium")
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                f"--user-agent={random.choice(self.user_agents)}",
            ],
        )
        context = await browser.new_context(
            user_agent=random.choice(self.user_agents),
            viewport={"width": 1920, "height": 1080},
        )
        await context.add_init_script(STEALTH_SCRIPT)
        page = await context.new_page()
        await self.randomize_canvas(page)
        self._browser = browser
        self._page = page
        self._playwright = playwright
        try:
            yield browser, page
        finally:
            await browser.close()
            self._browser = None
            self._page = None
            await playwright.stop()
            self._playwright = None

    async def _capsolver_turnstile(self, page: Any) -> bool:
        """Заглушка: Capsolver API для Cloudflare Turnstile (при наличии CAPSOLVER_API_KEY)."""
        key = (os.getenv("CAPSOLVER_API_KEY") or "").strip()
        if not key or not requests:
            return False
        # TODO: вызов Capsolver API (get taskId → getResult) и подстановка токена в cf-turnstile-response
        logger.debug("capsolver_turnstile: API не реализован, stub")
        return False

    async def bypass_turnstile(self, page: Any) -> bool:
        """Cloudflare Turnstile: boost trust score + fallback Capsolver. solvePows — вне Playwright."""
        await self.boost_trust_score(page)
        return await self._capsolver_turnstile(page)


async def main():
    async with SupremeRecaptcha(pageurl="https://sudrf.ru") as solver:
        async with solver.stealth_browser(headless=True) as (browser, page):
            await page.goto("https://sudrf.ru")
            # Пример: человеческий ввод в поиск
            # await solver.human_type(page, "#search", "2341844", delay_min=50, delay_max=150)
            # Решение reCAPTCHA (подставьте реальный site_key с страницы)
            # token = await solver.smart_retry(lambda: solver.solve_recaptcha_v2(page, "SITE_KEY"))
            # await solver.inject_recaptcha_token(page, token)
            logger.info("stealth_browser + page ready")
    # Без playwright — только ротация сервисов:
    solver2 = SupremeRecaptcha(pageurl="https://sudrf.ru")
    token = solver2._solve_via_service("SITE_KEY", "https://sudrf.ru")
    logger.info("Token: %s", token[:50] + "..." if token and len(token) > 50 else token)


if __name__ == "__main__":
    asyncio.run(main())
