"""Команды подключения userbot + Mini App."""
from __future__ import annotations

import json
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from bot.config import MINI_APP_URL
from bot.db import (
    delete_userbot_session,
    get_userbot_session,
    save_userbot_session,
    set_userbot_active,
)
from bot.userbot_manager import (
    clear_pending_login,
    complete_phone_login,
    get_pending_login,
    is_userbot_running,
    notify_userbot_deleted,
    start_client,
    start_phone_login,
    stop_client,
)
from bot.utils import esc

router = Router(name="userbot")
logger = logging.getLogger(__name__)

MY_TELEGRAM_ORG = "https://my.telegram.org/auth"
USERBOT_APPS_URL = "https://my.telegram.org/apps"


def _userbot_keyboard(has_session: bool, is_active: bool) -> InlineKeyboardMarkup:
    """Клавиатура: Mini App + ссылки + быстрые действия."""
    rows: list[list[InlineKeyboardButton]] = []

    if MINI_APP_URL and MINI_APP_URL.startswith("http"):
        rows.append([
            InlineKeyboardButton(
                text="🚀 Открыть Mini App (установка)",
                web_app=WebAppInfo(url=MINI_APP_URL),
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="🔑 Получить API ID / Hash",
            url=MY_TELEGRAM_ORG,
        )
    ])
    rows.append([
        InlineKeyboardButton(
            text="📱 Apps (my.telegram.org)",
            url=USERBOT_APPS_URL,
        )
    ])

    if has_session:
        if is_active:
            rows.append([
                InlineKeyboardButton(text="⏸ Выключить", callback_data="userbot_off"),
            ])
        else:
            rows.append([
                InlineKeyboardButton(text="▶️ Включить", callback_data="userbot_on"),
            ])
        rows.append([
            InlineKeyboardButton(text="🗑 Удалить сессию", callback_data="userbot_delete"),
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="📖 Как подключить (шаги)",
                callback_data="userbot_howto",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("userbot"))
async def cmd_userbot(message: Message):
    uid = message.from_user.id
    row = get_userbot_session(uid)
    running = is_userbot_running(uid)

    has_session = bool(row and row[0] and row[0] != "pending")
    is_active = bool(row and row[3]) if row else False

    if row and row[3]:
        status = "🟢 активен" if running else "🟡 в БД, но не запущен"
    elif row and has_session:
        status = "⏸ сохранён, выключен"
    else:
        status = "⚪ не подключён"

    if MINI_APP_URL and MINI_APP_URL.startswith("http"):
        mini_hint = (
            "🚀 <b>Рекомендуется:</b> открой <b>Mini App</b> кнопкой ниже — "
            "там пошаговая установка без команд.\n\n"
        )
    else:
        mini_hint = (
            "⚠️ Mini App URL не задан в <code>config.MINI_APP_URL</code>. "
            "Залей папку <code>miniapp/</code> на сайт и укажи ссылку.\n\n"
        )

    text = (
        f"🖋 <b>Userbot — «передумал писать»</b>\n\n"
        f"Статус: <b>{status}</b>\n\n"
        f"{mini_hint}"
        f"Без userbot бот работает как раньше (business).\n"
        f"С userbot уведомляет, когда собеседник начал печатать и передумал.\n\n"
        f"<b>Вручную:</b>\n"
        f"1. API: <code>/userbot_api ID HASH</code>\n"
        f"2. <code>/userbot_phone +79001234567</code>\n"
        f"3. <code>/userbot_code 12345</code>\n"
        f"4. 2FA: <code>/userbot_2fa пароль</code>\n\n"
        f"Или сессия: <code>/userbot_session СТРОКА</code>"
    )
    await message.answer(
        text,
        reply_markup=_userbot_keyboard(has_session, is_active),
        disable_web_page_preview=True,
    )


@router.message(F.web_app_data)
async def on_web_app_data(message: Message):
    """Обработка данных из Mini App."""
    try:
        payload = json.loads(message.web_app_data.data)
    except Exception:
        return await message.answer("❌ Не удалось разобрать данные Mini App.")

    action = (payload.get("action") or "").strip().lower()
    uid = message.from_user.id

    if action == "api":
        try:
            api_id = int(payload.get("api_id"))
            api_hash = str(payload.get("api_hash") or "").strip()
        except (TypeError, ValueError):
            return await message.answer("❗️ api_id должен быть числом.")
        if not api_hash or len(api_hash) < 8:
            return await message.answer("❗️ api_hash слишком короткий.")
        row = get_userbot_session(uid)
        session = row[0] if row else ""
        save_userbot_session(uid, session or "pending", api_id, api_hash)
        if not session or session == "pending":
            set_userbot_active(uid, False)
        return await message.answer(
            "✅ API сохранены через Mini App.\n"
            "Дальше в Mini App введи номер телефона."
        )

    if action == "phone":
        phone = str(payload.get("phone") or "").strip()
        if not phone:
            return await message.answer("❗️ Укажи номер телефона.")
        row = get_userbot_session(uid)
        api_id = row[1] if row else None
        api_hash = row[2] if row else None
        msg = await start_phone_login(uid, phone, api_id, api_hash)
        return await message.answer(msg)

    if action == "code":
        code = str(payload.get("code") or "").strip().replace(" ", "")
        if not code:
            return await message.answer("❗️ Укажи код.")
        text, _ = await complete_phone_login(uid, code)
        return await message.answer(text)

    if action == "2fa":
        password = str(payload.get("password") or "").strip()
        if not password:
            return await message.answer("❗️ Укажи пароль 2FA.")
        pending = get_pending_login(uid)
        if not pending:
            return await message.answer("❌ Нет ожидания 2FA. Начни с шага «телефон».")
        try:
            client = pending["client"]
            await client.sign_in(password=password)
            session_string = client.session.save()
            await client.disconnect()
            clear_pending_login(uid)
            save_userbot_session(
                uid, session_string, pending["api_id"], pending["api_hash"]
            )
            status = await start_client(
                uid, session_string, pending["api_id"], pending["api_hash"]
            )
            return await message.answer(status)
        except Exception as e:
            return await message.answer(f"❌ 2FA ошибка: {esc(str(e))}")

    if action == "session":
        session_string = str(payload.get("session") or "").strip()
        if len(session_string) < 10:
            return await message.answer("❗️ Строка сессии слишком короткая.")
        row = get_userbot_session(uid)
        api_id = row[1] if row else None
        api_hash = row[2] if row else None
        if payload.get("api_id"):
            try:
                api_id = int(payload["api_id"])
            except (TypeError, ValueError):
                pass
        if payload.get("api_hash"):
            api_hash = str(payload["api_hash"]).strip() or api_hash
        save_userbot_session(uid, session_string, api_id, api_hash)
        status = await start_client(uid, session_string, api_id, api_hash)
        return await message.answer(status)

    await message.answer(f"❓ Неизвестное действие Mini App: <code>{esc(action)}</code>")


@router.callback_query(lambda c: c.data == "userbot_howto")
async def callback_userbot_howto(callback):
    await callback.answer()
    await callback.message.answer(
        "📖 <b>Пошаговая установка userbot</b>\n\n"
        "1️⃣ Открой <a href='https://my.telegram.org/auth'>my.telegram.org</a>\n"
        "2️⃣ Войди → <b>API development tools</b>\n"
        "3️⃣ Создай приложение → скопируй <code>api_id</code> и <code>api_hash</code>\n"
        "4️⃣ В боте или Mini App:\n"
        "   <code>/userbot_api 12345678 abcdef...</code>\n"
        "5️⃣ <code>/userbot_phone +79001234567</code>\n"
        "6️⃣ <code>/userbot_code 12345</code>\n"
        "7️⃣ 2FA: <code>/userbot_2fa пароль</code>\n\n"
        "✅ Готово — мониторинг «передумал писать» активен.",
        disable_web_page_preview=True,
    )


@router.callback_query(lambda c: c.data == "userbot_on")
async def callback_userbot_on(callback):
    uid = callback.from_user.id
    row = get_userbot_session(uid)
    if not row or not row[0] or row[0] == "pending":
        await callback.answer("❌ Сессия не найдена", show_alert=True)
        return
    set_userbot_active(uid, True)
    status = await start_client(
        uid, row[0], row[1], row[2], notify_event="on", send_session_file=False
    )
    await callback.answer()
    await callback.message.answer(status)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_userbot_keyboard(True, True)
        )
    except Exception:
        pass


@router.callback_query(lambda c: c.data == "userbot_off")
async def callback_userbot_off(callback):
    uid = callback.from_user.id
    await stop_client(uid, notify=True)
    set_userbot_active(uid, False)
    await callback.answer("⏸ Выключен")
    await callback.message.answer(
        "⏸ Userbot выключен. Сессия сохранена — включить: /userbot_on или кнопку ▶️"
    )
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_userbot_keyboard(True, False)
        )
    except Exception:
        pass


@router.callback_query(lambda c: c.data == "userbot_delete")
async def callback_userbot_delete(callback):
    uid = callback.from_user.id
    await stop_client(uid, notify=False)
    clear_pending_login(uid)
    delete_userbot_session(uid)
    await notify_userbot_deleted(uid)
    await callback.answer("🗑 Удалено")
    await callback.message.answer("🗑 Сессия userbot удалена.")
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_userbot_keyboard(False, False)
        )
    except Exception:
        pass


@router.message(Command("userbot_api"))
async def cmd_userbot_api(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔑 Открыть my.telegram.org", url=MY_TELEGRAM_ORG)
        ]])
        return await message.answer(
            "Использование:\n<code>/userbot_api API_ID API_HASH</code>\n\n"
            "Взять: my.telegram.org → API development tools",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    try:
        api_id = int(parts[1])
        api_hash = parts[2].strip()
    except ValueError:
        return await message.answer("❗️ API_ID должен быть числом.")

    row = get_userbot_session(message.from_user.id)
    session = row[0] if row else ""
    save_userbot_session(message.from_user.id, session or "pending", api_id, api_hash)
    if not session or session == "pending":
        set_userbot_active(message.from_user.id, False)

    await message.answer(
        f"✅ API сохранены.\n"
        f"Дальше: <code>/userbot_phone +79001234567</code>\n"
        f"или <code>/userbot_session СТРОКА_СЕССИИ</code>"
    )


@router.message(Command("userbot_phone"))
async def cmd_userbot_phone(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer(
            "Использование: <code>/userbot_phone +79001234567</code>"
        )
    phone = parts[1].strip()
    row = get_userbot_session(message.from_user.id)
    api_id = row[1] if row else None
    api_hash = row[2] if row else None
    msg = await start_phone_login(message.from_user.id, phone, api_id, api_hash)
    await message.answer(msg)


@router.message(Command("userbot_code"))
async def cmd_userbot_code(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Использование: <code>/userbot_code 12345</code>")
    code = parts[1].strip().replace(" ", "")
    text, _ = await complete_phone_login(message.from_user.id, code)
    await message.answer(text)


@router.message(Command("userbot_2fa"))
async def cmd_userbot_2fa(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Использование: <code>/userbot_2fa ваш_пароль</code>")
    if not get_pending_login(message.from_user.id):
        return await message.answer("❌ Нет ожидания 2FA. Начните с /userbot_phone")
    pending = get_pending_login(message.from_user.id)
    password = parts[1].strip()
    try:
        client = pending["client"]
        await client.sign_in(password=password)
        session_string = client.session.save()
        await client.disconnect()
        clear_pending_login(message.from_user.id)
        save_userbot_session(
            message.from_user.id,
            session_string,
            pending["api_id"],
            pending["api_hash"],
        )
        status = await start_client(
            message.from_user.id,
            session_string,
            pending["api_id"],
            pending["api_hash"],
        )
        await message.answer(status)
    except Exception as e:
        await message.answer(f"❌ 2FA ошибка: {esc(str(e))}")


@router.message(Command("userbot_session"))
async def cmd_userbot_session(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or len(parts[1].strip()) < 10:
        return await message.answer(
            "Использование: <code>/userbot_session СТРОКА</code>\n\n"
            "Строку сессии можно получить скриптом Telethon StringSession."
        )
    session_string = parts[1].strip()
    row = get_userbot_session(message.from_user.id)
    api_id = row[1] if row else None
    api_hash = row[2] if row else None
    save_userbot_session(message.from_user.id, session_string, api_id, api_hash)
    status = await start_client(message.from_user.id, session_string, api_id, api_hash)
    await message.answer(status)
    try:
        await message.delete()
    except Exception:
        pass


@router.message(Command("userbot_on"))
async def cmd_userbot_on(message: Message):
    row = get_userbot_session(message.from_user.id)
    if not row or not row[0] or row[0] == "pending":
        return await message.answer(
            "❌ Сессия не найдена. Сначала /userbot_phone или /userbot_session"
        )
    set_userbot_active(message.from_user.id, True)
    status = await start_client(
        message.from_user.id, row[0], row[1], row[2],
        notify_event="on", send_session_file=False,
    )
    await message.answer(status)


@router.message(Command("userbot_off"))
async def cmd_userbot_off(message: Message):
    await stop_client(message.from_user.id, notify=True)
    set_userbot_active(message.from_user.id, False)
    await message.answer("⏸ Userbot выключен. Сессия сохранена — включить: /userbot_on")


@router.message(Command("userbot_delete"))
async def cmd_userbot_delete(message: Message):
    await stop_client(message.from_user.id, notify=False)
    clear_pending_login(message.from_user.id)
    delete_userbot_session(message.from_user.id)
    await notify_userbot_deleted(message.from_user.id)
    await message.answer("🗑 Сессия userbot удалена.")
