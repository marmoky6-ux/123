"""Обязательная подписка на канал + middleware."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import REQUIRED_CHANNEL_CHAT_ID, REQUIRED_CHANNEL_LINK
from bot.db import is_admin, is_owner
from bot.loader import bot
from bot.utils import esc

router = Router(name="subscription")

_last_sub_prompt: dict[int, float] = {}
_SUB_PROMPT_COOLDOWN = 60


def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=REQUIRED_CHANNEL_LINK)],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")],
        ]
    )


async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(
            chat_id=REQUIRED_CHANNEL_CHAT_ID, user_id=user_id
        )
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logging.warning(f"Не удалось проверить подписку пользователя {user_id}: {e}")
        return True


async def send_subscription_prompt(chat_id: int) -> None:
    try:
        await bot.send_message(
            chat_id,
            "🔒 <b>Требуется подписка на канал</b>\n\n"
            f"Чтобы пользоваться ботом, подпишись на канал {esc(REQUIRED_CHANNEL_LINK)}\n"
            "После подписки нажми кнопку «Я подписался» ниже.",
            reply_markup=subscription_keyboard(),
        )
    except Exception as e:
        logging.warning(f"Не удалось отправить запрос подписки {chat_id}: {e}")


async def gate_subscription(owner_id: int | None) -> bool:
    if owner_id is None:
        return True
    if is_owner(owner_id) or is_admin(owner_id):
        return True
    if await is_subscribed(owner_id):
        return True
    now = datetime.now().timestamp()
    last = _last_sub_prompt.get(owner_id, 0)
    if now - last > _SUB_PROMPT_COOLDOWN:
        _last_sub_prompt[owner_id] = now
        await send_subscription_prompt(owner_id)
    return False


class SubscriptionMiddleware(BaseMiddleware):
    """Блокирует использование бота в ЛС, пока пользователь не подписан."""

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        user = event.from_user
        if user is None or event.chat is None or event.chat.type != "private":
            return await handler(event, data)
        if is_owner(user.id) or is_admin(user.id):
            return await handler(event, data)
        if await is_subscribed(user.id):
            return await handler(event, data)
        await send_subscription_prompt(event.chat.id)
        return None


@router.callback_query(lambda c: c.data == "check_sub")
async def callback_check_sub(callback: types.CallbackQuery):
    user = callback.from_user
    if is_owner(user.id) or is_admin(user.id) or await is_subscribed(user.id):
        try:
            await callback.message.edit_text(
                "✅ <b>Подписка подтверждена!</b>\n\nОтправь /start, чтобы продолжить."
            )
        except Exception:
            pass
        await callback.answer("Спасибо за подписку! ✅")
    else:
        await callback.answer("❌ Вы ещё не подписаны на канал.", show_alert=True)
