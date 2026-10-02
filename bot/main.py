"""Точка входа: запуск бота + HTTP API для Mini App."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from bot.config import OWNER_ID
from bot.db import cleanup_db, init_db
from bot.handlers import setup_routers
from bot.handlers.subscription import SubscriptionMiddleware
from bot.loader import bot, dp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def auto_cleanup_task() -> None:
    """Фоновая задача: очистка БД каждые 7 дней."""
    SEVEN_DAYS = 7 * 24 * 60 * 60
    while True:
        await asyncio.sleep(SEVEN_DAYS)
        try:
            deleted_msgs, deleted_events = cleanup_db()
            await bot.send_message(
                OWNER_ID,
                f"🧹 <b>Автоочистка БД выполнена</b>\n\n"
                f"Удалено записей старше 7 дней:\n"
                f"• Сообщений: <b>{deleted_msgs}</b>\n"
                f"• Событий: <b>{deleted_events}</b>\n\n"
                f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            )
        except Exception as e:
            logging.error(f"Ошибка автоочистки БД: {e}")


async def start_web_api() -> None:
    """HTTP API на :8080 для входа userbot с сайта."""
    try:
        import uvicorn
        from bot.web_api import app as api_app
    except ImportError as e:
        logger.error(f"Web API не запущен (нужны fastapi uvicorn): {e}")
        return
    config = uvicorn.Config(
        api_app,
        host="127.0.0.1",
        port=8080,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    logger.info("Web API: http://127.0.0.1:8080/api/health")
    await server.serve()


async def main() -> None:
    init_db()
    dp.message.middleware(SubscriptionMiddleware())
    setup_routers(dp)
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        from bot.userbot_manager import restore_all_sessions, shutdown_all
        await restore_all_sessions()
    except Exception as e:
        logging.error(f"Userbot restore: {e}")

    asyncio.create_task(auto_cleanup_task())
    asyncio.create_task(start_web_api())
    try:
        await dp.start_polling(bot)
    finally:
        try:
            from bot.userbot_manager import shutdown_all
            await shutdown_all()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
