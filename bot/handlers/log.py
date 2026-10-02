"""Лог сообщений за 7 дней + CSV-экспорт."""
from __future__ import annotations

import csv
import logging
import os
import tempfile
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from bot.db import (
    get_chat_log_both_sides,
    parse_log_message_row,
)
from bot.loader import bot
from bot.utils import esc

router = Router(name="log")

# ====================== ЛОГ СООБЩЕНИЙ ЗА 7 ДНЕЙ ======================
async def _resolve_log_rows(requester_id: int, target_id: int, limit: int):
    """Выборка лога: только чаты, где бот подключён у requester_id (одинаково для всех)."""
    return get_chat_log_both_sides(requester_id, target_id, limit)


async def _name_link(uid: int) -> str:
    try:
        u = await bot.get_chat(uid)
        name = esc(u.full_name or f"User_{uid}")
        uname = f" @{u.username}" if getattr(u, "username", None) else ""
        return f"<a href='tg://user?id={uid}'>{name}</a>{uname}"
    except Exception:
        return f"<a href='tg://user?id={uid}'>ID {uid}</a>"


@router.message(Command("log"))
async def cmd_log(message: Message):
    """
    /log <user_id> [лимит]
    Лог сообщений собеседника (и ваших в тех же чатах) за последние 7 дней.
    """
    requester = message.from_user

    args = message.text.split()[1:]
    if not args:
        return await message.answer(
            "📋 <b>Лог сообщений за 7 дней</b>\n\n"
            "Использование:\n"
            "• <code>/log 123456789</code> — последние 100 сообщений\n"
            "• <code>/log 123456789 50</code> — с лимитом (1–300)\n"
            "• <code>/logcsv 123456789</code> — выгрузка в CSV-файл\n\n"
            "Показываются сообщения в чатах, где бот подключён у вас."
        )

    try:
        target_id = int(args[0])
        limit = 100
        if len(args) >= 2:
            limit = int(args[1])
    except ValueError:
        return await message.answer(
            "❗️ ID и лимит должны быть числами.\nПример: <code>/log 123456789 50</code>"
        )

    if target_id == requester.id:
        return await message.answer("❗️ Укажите ID собеседника, а не свой.")

    limit = max(1, min(300, limit))
    rows = await _resolve_log_rows(requester.id, target_id, limit)

    if not rows:
        return await message.answer(
            f"📭 Сообщений от <code>{target_id}</code> за последние 7 дней не найдено "
            f"(в чатах, где бот подключён у вас)."
        )

    owner_link = await _name_link(requester.id)
    target_link = await _name_link(target_id)

    header = (
        f"📋 <b>Лог сообщений за 7 дней</b>\n"
        f"👤 Вы (владелец): {owner_link} <code>{requester.id}</code>\n"
        f"💬 Собеседник: {target_link} <code>{target_id}</code>\n"
        f"📊 Найдено: <b>{len(rows)}</b> (лимит {limit})\n"
        f"💾 CSV: <code>/logcsv {target_id} {limit}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
    )

    lines = []
    for user_id, msg_id, raw_json, timestamp, chat_id in reversed(rows):
        parsed = parse_log_message_row(user_id, msg_id, raw_json, timestamp, chat_id)
        if not parsed:
            continue
        media_label = f"[{parsed['media_type']}] " if parsed["media_type"] else ""
        if parsed["user_id"] == requester.id:
            side = "🟢 Вы"
        elif parsed["user_id"] == target_id:
            side = "🔵 Собеседник"
        else:
            side = "⚪"
        content = (media_label + esc(parsed["text"])).strip() or "(пусто)"
        short = content[:120] + ("…" if len(content) > 120 else "")
        t_short = parsed["timestamp"][5:16] if len(parsed["timestamp"]) >= 16 else parsed["timestamp"]
        lines.append(
            f"{side} <a href='tg://user?id={parsed['user_id']}'>{esc(parsed['name'])}</a> [{t_short}]:\n"
            f"<blockquote>{short}</blockquote>"
        )

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


@router.message(Command("logcsv"))
async def cmd_logcsv(message: Message):
    """
    /logcsv <user_id> [лимит]
    Экспорт лога сообщений за 7 дней в CSV-файл.
    """
    requester = message.from_user

    args = message.text.split()[1:]
    if not args:
        return await message.answer(
            "📁 <b>Экспорт лога в CSV</b>\n\n"
            "Использование:\n"
            "• <code>/logcsv 123456789</code> — до 300 сообщений\n"
            "• <code>/logcsv 123456789 100</code> — с лимитом (1–300)\n\n"
            "Файл придёт документом. Кодировка UTF-8, разделитель — запятая."
        )

    try:
        target_id = int(args[0])
        limit = 300
        if len(args) >= 2:
            limit = int(args[1])
    except ValueError:
        return await message.answer(
            "❗️ ID и лимит должны быть числами.\nПример: <code>/logcsv 123456789 100</code>"
        )

    if target_id == requester.id:
        return await message.answer("❗️ Укажите ID собеседника, а не свой.")

    limit = max(1, min(300, limit))
    rows = await _resolve_log_rows(requester.id, target_id, limit)

    if not rows:
        return await message.answer(
            f"📭 Сообщений от <code>{target_id}</code> за последние 7 дней не найдено."
        )

    try:
        owner_chat = await bot.get_chat(requester.id)
        owner_name = owner_chat.full_name or str(requester.id)
        owner_uname = getattr(owner_chat, "username", "") or ""
    except Exception:
        owner_name, owner_uname = str(requester.id), ""
    try:
        target_chat = await bot.get_chat(target_id)
        target_name = target_chat.full_name or str(target_id)
        target_uname = getattr(target_chat, "username", "") or ""
    except Exception:
        target_name, target_uname = str(target_id), ""

    fieldnames = [
        "timestamp", "side", "user_id", "name", "username",
        "msg_id", "chat_id", "media_type", "text"
    ]
    parsed_rows = []
    for user_id, msg_id, raw_json, timestamp, chat_id in reversed(rows):
        p = parse_log_message_row(user_id, msg_id, raw_json, timestamp, chat_id)
        if not p:
            continue
        if p["user_id"] == requester.id:
            side = "owner"
        elif p["user_id"] == target_id:
            side = "peer"
        else:
            side = "other"
        parsed_rows.append({
            "timestamp": p["timestamp"],
            "side": side,
            "user_id": p["user_id"],
            "name": p["name"],
            "username": p["username"],
            "msg_id": p["msg_id"],
            "chat_id": p["chat_id"] or "",
            "media_type": p["media_type"],
            "text": p["text"],
        })

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".csv", prefix=f"log_{target_id}_")
        os.close(fd)
        with open(tmp_path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(
                f"# owner={requester.id} ({owner_name}"
                f"{' @' + owner_uname if owner_uname else ''}); "
                f"peer={target_id} ({target_name}"
                f"{' @' + target_uname if target_uname else ''}); "
                f"period=last_7_days; exported={datetime.now().isoformat()}\n"
            )
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            writer.writerows(parsed_rows)

        filename = (
            f"log_{requester.id}_{target_id}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        caption = (
            f"📁 <b>Экспорт лога за 7 дней</b>\n"
            f"👤 Вы: {esc(owner_name)}"
            f"{' @' + esc(owner_uname) if owner_uname else ''} <code>{requester.id}</code>\n"
            f"💬 Собеседник: {esc(target_name)}"
            f"{' @' + esc(target_uname) if target_uname else ''} <code>{target_id}</code>\n"
            f"📊 Записей: <b>{len(parsed_rows)}</b>\n"
            f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        await message.answer_document(
            FSInputFile(tmp_path, filename=filename),
            caption=caption
        )
    except Exception as e:
        logging.error(f"logcsv error: {e}")
        await message.answer(f"❌ Ошибка при создании CSV: {esc(str(e))}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


