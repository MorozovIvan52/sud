# supreme_case_monitor.py — мониторинг изменений статусов ИП 24/7 + ИИ-советник действий.

import asyncio
import os
from typing import Any, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

AI_ACTIONS = {
    "исполнено": "✅ Дело закрыто — снимаем с контроля",
    "исполнен": "✅ Дело закрыто — снимаем с контроля",
    "арест_имущества": "🔥 АВТО-ЗВОНОК: имущество на аукционе!",
    "арест": "🔥 Проверить арест имущества",
    "розыск": "🚨 СРОЧНО: должник скрылся",
    "приостановлено": "⏸️ Ждём разблокировки счетов",
    "приостановлен": "⏸️ Ждём разблокировки счетов",
    "возврат": "💰 АВТО-ПЕРЕДАН в МФО",
    "активно": "📋 На контроле, ждём исполнения",
    "ошибка": "⚠️ Требуется ручная проверка",
}


def ai_recommend_action(status: str, result: Optional[Dict[str, Any]] = None) -> str:
    """ИИ-советник: по статусу дела возвращает рекомендацию действия."""
    if not status:
        return AI_ACTIONS.get("ошибка", "⚠️ Требуется ручная проверка")
    s = str(status).strip().lower()
    for key, action in AI_ACTIONS.items():
        if key in s or s in key:
            return action
    return AI_ACTIONS.get("активно", "📋 На контроле")


async def send_telegram_alert(ip: str, old_status: str, new_status: str, recommendation: str) -> bool:
    """Отправка алерта в Telegram о смене статуса ИП."""
    token = os.getenv("BOT_TOKEN")
    admin_id = os.getenv("ADMIN_ID") or os.getenv("MONITOR_CHAT_ID")
    if not token or not admin_id:
        logger.debug("BOT_TOKEN or ADMIN_ID not set — skip telegram alert")
        return False
    try:
        from aiogram import Bot
        from aiogram.enums import ParseMode
        text = (
            f"🔄 <b>Изменился статус ИП</b>\n\n"
            f"№ ИП: <code>{ip}</code>\n"
            f"Было: {old_status}\n"
            f"Стало: {new_status}\n\n"
            f"💡 {recommendation}"
        )
        bot = Bot(token=token)
        await bot.send_message(chat_id=int(admin_id), text=text, parse_mode=ParseMode.HTML)
        await bot.session.close()
        return True
    except Exception as e:
        logger.warning("Telegram alert: %s", e)
        return False


class SupremeCaseMonitor:
    """24/7 отслеживание изменений статусов ИП: кэш + парсер каждые 6 ч + алерты."""

    def __init__(self, check_interval_hours: float = 6.0):
        self.check_interval_seconds = check_interval_hours * 3600
        self._cache: Dict[str, str] = {}
        self._parser = None
        self._turbo = None

    async def _get_parser(self):
        if self._parser is None:
            from supreme_parser import SupremeParser
            self._parser = SupremeParser()
            await self._parser.__aenter__()
        return self._parser

    async def _get_turbo(self):
        if self._turbo is None:
            try:
                from supreme_turbo import SupremeTurbo
                self._turbo = SupremeTurbo()
                await self._turbo.__aenter__()
            except ImportError:
                pass
            except Exception as e:
                logger.debug("SupremeTurbo __aenter__: %s", e)
                self._turbo = None
        return self._turbo

    async def get_current_status(self, ip: str) -> Optional[Dict[str, Any]]:
        """Текущий статус ИП (через turbo cache или парсер)."""
        turbo = await self._get_turbo()
        if turbo:
            return await turbo.search_ip_turbo(ip)
        parser = await self._get_parser()
        result = await parser.parse_ip_number(ip)
        return result.to_dict()

    async def track_case_changes(
        self,
        ip_list: List[str],
        on_change: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Проверяет список ИП, сравнивает с кэшем, при изменении статуса вызывает on_change и отправляет алерт.
        Возвращает список изменений.
        """
        changes = []
        for ip in ip_list:
            ip = str(ip).strip()
            if not ip:
                continue
            try:
                new_result = await self.get_current_status(ip)
                if not new_result:
                    continue
                new_status = new_result.get("case_status") or new_result.get("status") or ""
                old_status = self._cache.get(ip, "")
                self._cache[ip] = new_status
                if old_status and old_status.strip() != new_status.strip():
                    recommendation = ai_recommend_action(new_status, new_result)
                    new_result["ai_recommendation"] = recommendation
                    change = {
                        "ip": ip,
                        "old_status": old_status,
                        "new_status": new_status,
                        "new_result": new_result,
                        "action": recommendation,
                    }
                    changes.append(change)
                    await send_telegram_alert(ip, old_status, new_status, recommendation)
                    if on_change:
                        if asyncio.iscoroutinefunction(on_change):
                            await on_change(change)
                        else:
                            on_change(change)
            except Exception as e:
                logger.debug("track_case_changes %s: %s", ip, e)
        return changes

    async def run_forever(self, ip_list: List[str], on_change: Optional[Any] = None) -> None:
        """Бесконечный цикл: каждые check_interval_seconds проверяет ip_list и шлёт алерты."""
        logger.info("SupremeCaseMonitor started: %s ИП, интервал %.1f ч", len(ip_list), self.check_interval_seconds / 3600)
        while True:
            try:
                changes = await self.track_case_changes(ip_list, on_change=on_change)
                if changes:
                    logger.info("Изменений: %s", len(changes))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("run_forever: %s", e)
            await asyncio.sleep(self.check_interval_seconds)

    async def close(self) -> None:
        if self._turbo:
            await self._turbo.close()
            self._turbo = None
        if self._parser:
            await self._parser.__aexit__(None, None, None)
            self._parser = None
