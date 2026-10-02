"""Пользовательские команды: /help, /send, /love, /type и .команды."""
from __future__ import annotations

import asyncio
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.handlers.referral import cmd_ref
from bot.utils import esc

router = Router(name="user_commands")


@router.message(F.text.regexp(r'^\.(\w+)'))
async def dot_command_router(message: Message):
    import re
    match = re.match(r'^\.(\w+)(.*)', message.text, re.DOTALL)
    if not match:
        return
    cmd = match.group(1).lower()
    rest = match.group(2).strip()
    # Подменяем message.text и вызываем нужный хендлер напрямую
    if cmd == 'help':
        message.text = f'/help {rest}'.strip()
        await cmd_help(message)
    elif cmd == 'love':
        await cmd_love(message)
    elif cmd == 'type':
        message.text = f'/type {rest}'.strip()
        await cmd_type(message)
    elif cmd == 'send':
        await cmd_send(message)
    elif cmd == 'ref':
        await cmd_ref(message)

@router.message(Command("help"))
async def cmd_help(message: Message):
    parts = message.text.split(None, 1)

    # Детальная справка по конкретной команде
    if len(parts) > 1:
        key = parts[1].strip().lower().lstrip("/")
        helps = {
            "send": (
                "💸 <b>/send</b>\n\n"
                "Отправляет сообщение с кнопкой-ссылкой.\n"
                "Использование: /send"
            ),
            "love": (
                "❤️ <b>/love</b>\n\n"
                "Запускает красивую анимацию из сердечек всех цветов радуги.\n"
                "Использование: /love"
            ),
            "type": (
                "⌨️ <b>/type</b>\n\n"
                "Отправляет текст по одному символу с эффектом живого набора.\n"
                "Использование: /type [текст]\n"
                "Пример: /type Привет как дела"
            ),
            "ref": (
                "🔗 <b>/ref</b>\n\n"
                "Генерирует вашу персональную реферальную ссылку.\n"
                "За каждого приглашённого приходит уведомление."
            ),
            "log": (
                "📋 <b>/log</b>\n\n"
                "Лог сообщений собеседника за последние 7 дней "
                "в чатах, где у вас подключён бизнес-бот.\n\n"
                "• <code>/log 123456789</code> — последние 100\n"
                "• <code>/log 123456789 50</code> — с лимитом (1–300)\n\n"
                "Для файла: <code>/logcsv 123456789</code>"
            ),
            "logcsv": (
                "📁 <b>/logcsv</b>\n\n"
                "Экспорт лога сообщений за 7 дней в CSV-файл (UTF-8).\n\n"
                "• <code>/logcsv 123456789</code> — до 300 записей\n"
                "• <code>/logcsv 123456789 100</code> — с лимитом\n\n"
                "Колонки: timestamp, side, user_id, name, username, "
                "msg_id, chat_id, media_type, text"
            ),
        }
        text = helps.get(key, f"❓ Команда <code>{esc(key)}</code> не найдена.\n\nНапиши /help для полного списка.")
        return await message.answer(text)
  # Общая справка
    await message.answer(
        "📝 <b>Команды бота:</b>\n\n"
        "▫️ /send — отправить сообщение с кнопкой\n"
        "▫️ /love — анимация влюблённых эмодзи\n"
        "▫️ /type [текст] — набор текста по одной букве\n"
        "▫️ /spam текст количество — спам сообщениями (до 50)\n"
        "▫️ /ref — реферальная ссылка\n"
        "▫️ /log ID — лог сообщений собеседника за 7 дней\n"
        "▫️ /logcsv ID — экспорт лога в CSV\n"
        "▫️ /userbot — «передумал писать» (кнопки + ссылки для установки)\n"
        "   Пример: <code>/log 123456789</code> · <code>/logcsv 123456789 50</code>\n\n"
        "ℹ️ Справка по команде: /help [команда]\n"
        "Пример: <code>/help type</code>"
    )
    
@router.message(Command("send"))
async def cmd_send(message: Message):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💸 Перейти", url="https://t.me/feofilov_for_salle")
    ]])
    await message.answer(
        "✅ <b>Чек активирован</b>\n\n"
        "💰 Получатель может забрать средства по кнопке ниже:",
        reply_markup=kb
    )

@router.message(Command("love"))
async def cmd_love(message: Message):
    frames = [
        "🖤", "🖤🖤", "💜🖤💜", "💙💜🖤💜💙",
        "💚💙💜🖤💜💙💚", "💛💚💙💜🖤💜💙💚💛",
        "🧡💛💚💙💜🖤💜💙💚💛🧡", "❤️🧡💛💚💙💜🖤💜💙💚💛🧡❤️",
        "🧡💛💚💙💜🖤💜💙💚💛🧡", "💛💚💙💜🖤💜💙💚💛",
        "💚💙💜🖤💜💙💚", "💙💜🖤💜💙",
        "💜🖤💜", "🖤💜", "❤️\u200d🔥",
        "❤️\u200d🔥💕", "❤️\u200d🔥💕💞", "❤️\u200d🔥💕💞💓",
        "❤️\u200d🔥💕💞💓💗", "❤️\u200d🔥💕💞💓💗💖",
        "💖💗💓💞💕❤️\u200d🔥", "💓💞💕❤️\u200d🔥",
        "💞💕❤️\u200d🔥", "💕❤️\u200d🔥", "❤️\u200d🔥",
        "🫀", "💝", "❤️",
    ]
    sent = await message.answer(frames[0])
    for frame in frames[1:]:
        await asyncio.sleep(0.4)
        try:
            await sent.edit_text(frame)
        except Exception:
            break

@router.message(Command("type"))
async def cmd_type(message: Message):
    parts = message.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        return await message.answer("❗️ Использование: /type [текст]\nПример: /type Привет")
    text = parts[1].strip()
    if len(text) > 100:
        return await message.answer("❗️ Максимум 100 символов.")
    sent = await message.answer("⌨️")
    current = ""
    for char in text:
        current += char
        try:
            await sent.edit_text(current)
            await asyncio.sleep(0.15)
        except Exception:
            break
