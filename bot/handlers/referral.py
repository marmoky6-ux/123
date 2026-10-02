"""Реферальная система."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db import get_referral_count, get_top_referrers, is_admin
from bot.loader import bot
from bot.utils import esc

router = Router(name="referral")


@router.message(Command("ref"))
async def cmd_ref(message: Message):
    user = message.from_user
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    count = get_referral_count(user.id)
    await message.answer(
        f"🔗 <b>Ваша реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"👥 Приглашено пользователей: <b>{count}</b>\n\n"
        f"Отправьте эту ссылку друзьям — когда они запустят бота по ней, "
        f"вы получите уведомление."
    )


@router.message(Command("toprefs"))
async def cmd_toprefs(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ У вас нет прав доступа.")
    top = get_top_referrers(10)
    if not top:
        return await message.answer("📭 Рефералов пока нет.")
    text = "🏆 <b>Топ пригласивших пользователей:</b>\n\n"
    for i, (uid, cnt) in enumerate(top, start=1):
        try:
            u = await bot.get_chat(uid)
            name = esc(u.full_name or f"User_{uid}")
            link = f"<a href='tg://user?id={uid}'>{name}</a>"
        except Exception:
            link = f"ID: <code>{uid}</code>"
        text += f"{i}. {link} <code>{uid}</code> — <b>{cnt}</b> чел.\n"
    await message.answer(text, disable_web_page_preview=True)
