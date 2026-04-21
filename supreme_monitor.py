"""
Мониторинг атак: проверка счётчиков в Redis и отправка алертов в Telegram.
Запуск: задать REDIS_URL, BOT_TOKEN, ADMIN_ID и запустить скрипт или как фоновую задачу в боте.
"""
import asyncio
import logging
import os
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ADMIN_ID = os.getenv("ADMIN_ID")  # Telegram user ID админа для алертов
RATE_LIMIT_ALERT_THRESHOLD = int(os.getenv("RATE_LIMIT_ALERT_THRESHOLD", "1000"))
SQLI_ALERT_THRESHOLD = int(os.getenv("SQLI_ALERT_THRESHOLD", "10"))
CHECK_INTERVAL_SEC = int(os.getenv("MONITOR_INTERVAL_SEC", "60"))


def get_redis():
    try:
        import redis
        url = os.getenv("REDIS_URL") or os.getenv("REDIS_HOST")
        if not url:
            return None
        if url.startswith("redis://") or url.startswith("rediss://"):
            return redis.from_url(url, decode_responses=True)
        return redis.Redis(host=url, port=int(os.getenv("REDIS_PORT", 6379)), decode_responses=True)
    except Exception:
        return None


async def send_telegram_alert(text: str) -> bool:
    """Отправляет сообщение в Telegram админу."""
    token = os.getenv("BOT_TOKEN")
    if not token or not ADMIN_ID:
        return False
    try:
        from aiogram import Bot
        from aiogram.enums import ParseMode
        bot = Bot(token=token)
        await bot.send_message(
            chat_id=int(ADMIN_ID),
            text=text,
            parse_mode=ParseMode.HTML,
        )
        await bot.session.close()
        return True
    except Exception as e:
        logger.warning("Telegram alert failed: %s", e)
        return False


async def attack_monitor():
    """Цикл проверки счётчиков атак и отправки алертов."""
    redis_client = get_redis()
    if not redis_client:
        logger.info("Redis not configured — attack monitor disabled.")
        return

    if not ADMIN_ID or not os.getenv("BOT_TOKEN"):
        logger.info("ADMIN_ID or BOT_TOKEN not set — alerts disabled.")
        return

    while True:
        try:
            rate_hits = redis_client.get("rate_limit_hits")
            sqli = redis_client.get("suspicious_queries")

            rate_val = int(rate_hits) if rate_hits else 0
            sqli_val = int(sqli) if sqli else 0

            if rate_val >= RATE_LIMIT_ALERT_THRESHOLD:
                await send_telegram_alert(
                    "🚨 <b>DDoS / перегрузка</b>\n\n"
                    f"Срабатываний rate limit за последний час: <code>{rate_val}</code>\n\n"
                    "Рекомендуется: проверить логи, при необходимости включить CloudFlare / Fail2Ban."
                )
                redis_client.set("rate_limit_hits", "0", ex=3600)

            if sqli_val >= SQLI_ALERT_THRESHOLD:
                await send_telegram_alert(
                    "🛡️ <b>Подозрение на SQLi / инъекции</b>\n\n"
                    f"Подозрительных запросов: <code>{sqli_val}</code>\n\n"
                    "Проверьте логи и при необходимости ужесточите валидацию."
                )
                redis_client.set("suspicious_queries", "0", ex=3600)

        except Exception as e:
            logger.exception("Attack monitor error: %s", e)

        await asyncio.sleep(CHECK_INTERVAL_SEC)


async def main():
    await attack_monitor()


if __name__ == "__main__":
    asyncio.run(main())
