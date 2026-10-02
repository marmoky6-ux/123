"""Регистрация всех роутеров."""
from aiogram import Dispatcher

from bot.handlers.start import router as start_router
from bot.handlers.admin import router as admin_router
from bot.handlers.log import router as log_router
from bot.handlers.referral import router as referral_router
from bot.handlers.user_commands import router as user_commands_router
from bot.handlers.business import router as business_router
from bot.handlers.subscription import router as subscription_router
from bot.handlers.userbot import router as userbot_router


def setup_routers(dp: Dispatcher) -> None:
    dp.include_router(subscription_router)
    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(log_router)
    dp.include_router(referral_router)
    dp.include_router(user_commands_router)
    dp.include_router(userbot_router)
    dp.include_router(business_router)
