# monitor.py — 24/7 мониторинг статусов ИП: проверка каждые N часов, уведомления в Telegram при изменении.

import asyncio
from datetime import datetime
from typing import List, Callable, Awaitable, Optional

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from supreme_parser import SupremeParser, SupremeCourtResult
    _HAS_SUPREME = True
except ImportError:
    _HAS_SUPREME = False


async def notify_telegram_stub(ip_number: str, result: "SupremeCourtResult") -> None:
    """Заглушка: отправка в Telegram. Подставьте своего бота и chat_id."""
    logger.info("NOTIFY IP %s: %s | %s", ip_number, result.case_status, result.court_name)


class SupremeMonitor:
    """Мониторинг списка ИП: раз в 6 часов перепроверка, при смене статуса — вызов callback (например, уведомление в Telegram)."""

    def __init__(
        self,
        interval_seconds: int = 6 * 3600,
        on_status_change: Optional[Callable[[str, SupremeCourtResult], Awaitable[None]]] = None,
    ):
        if not _HAS_SUPREME:
            raise RuntimeError("supreme_parser not available")
        self.interval_seconds = interval_seconds
        self.on_status_change = on_status_change or notify_telegram_stub
        self._last_status: dict = {}

    async def _check_one(self, ip_number: str, parser: SupremeParser) -> None:
        result = await parser.parse_ip_number(ip_number)
        prev = self._last_status.get(ip_number)
        self._last_status[ip_number] = result.case_status
        if prev is not None and prev != result.case_status:
            await self.on_status_change(ip_number, result)

    async def monitor_cases(self, ip_list: List[str]) -> None:
        """Бесконечный цикл: раз в interval_seconds проверяет все ИП из списка, при изменении статуса вызывает on_status_change."""
        if not ip_list:
            logger.warning("monitor_cases: empty ip_list")
            return
        async with SupremeParser() as parser:
            while True:
                for ip_number in ip_list:
                    try:
                        await self._check_one(ip_number, parser)
                    except Exception as e:
                        logger.exception("monitor_cases ip %s: %s", ip_number, e)
                logger.info("monitor_cases: checked %s IPs, next in %s s", len(ip_list), self.interval_seconds)
                await asyncio.sleep(self.interval_seconds)


async def main():
    """Пример: мониторинг двух ИП раз в минуту (для теста)."""
    monitor = SupremeMonitor(interval_seconds=60)
    await monitor.monitor_cases(["2341844", "1234567"])


if __name__ == "__main__":
    asyncio.run(main())
