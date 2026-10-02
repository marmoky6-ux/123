"""Бизнес-подключения, сообщения, удаления, редактирования, view-once."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from aiogram import Router, types
from aiogram.types import (
    BusinessMessagesDeleted,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.db import (
    get_all_admins,
    get_connection_owner,
    get_msg_info,
    is_admin,
    is_owner,
    log_event,
    save_connection,
    save_msg,
)
from bot.handlers.subscription import gate_subscription, is_subscribed, send_subscription_prompt
from bot.loader import bot
from bot.utils import download_and_send_media, esc, is_view_once_media

router = Router(name="business")

# ====================== БИЗНЕС-ПОДКЛЮЧЕНИЕ ======================
@router.business_connection()
async def handle_business_connection(event: types.BusinessConnection):
    user = event.user
    save_connection(event.id, user.id)
    logging.info(f"Business connection: {event.id} → user {user.id}")
    if not is_owner(user.id) and not is_admin(user.id) and not await is_subscribed(user.id):
        await send_subscription_prompt(user.id)

# ====================== ОСНОВНАЯ ЛОГИКА ======================
@router.business_message()
async def handle_business_message(message: Message):
    sender = message.from_user
    if not sender:
        return
    if message.business_connection_id:
        try:
            conn_info = await bot.get_business_connection(message.business_connection_id)
            save_connection(conn_info.id, conn_info.user.id)
        except Exception as e:
            logging.warning(f"Не удалось получить инфо о подключении: {e}")
    owner_id = get_connection_owner(message.business_connection_id)
    if not await gate_subscription(owner_id):
        return
    save_msg(message)

    # ===== ОБРАБОТКА КОМАНД В ЛИЧНЫХ СООБЩЕНИЯХ =====
    # Команды работают только для владельца подключения
    if message.text and sender.id == owner_id:
        import re as _re
        dot_match = _re.match(r'^\.(\w+)(.*)', message.text, _re.DOTALL)
        if dot_match:
            cmd = dot_match.group(1).lower()
            arg = dot_match.group(2).strip()
            chat_id = message.chat.id
            bc_id = message.business_connection_id

                                   # ==================== .spam ====================
            if cmd == 'spam':
                if not arg:
                    await bot.send_message(
                        chat_id,
                        "❗️ Использование: <code>.spam текст количество</code>\nПример: <code>.spam лапша 10</code>",
                        business_connection_id=bc_id
                    )
                    return

                parts = arg.rsplit(maxsplit=1)
                if len(parts) < 2:
                    await bot.send_message(chat_id, "❗️ Нужно указать текст и количество", business_connection_id=bc_id)
                    return

                try:
                    count = int(parts[-1])
                    spam_text = parts[0].strip()
                except ValueError:
                    await bot.send_message(chat_id, "❗️ Количество должно быть числом", business_connection_id=bc_id)
                    return

                if count < 1:
                    count = 1
                if count > 50:
                    count = 50

                # Редактируем оригинальное сообщение с командой на первый текст спама
                try:
                    await bot.edit_message_text(
                        text=spam_text,
                        chat_id=chat_id,
                        message_id=message.message_id,
                        business_connection_id=bc_id
                    )
                except:
                    pass  # если не получилось отредактировать — продолжаем

                # Отправляем оставшиеся сообщения
                for i in range(count - 1):  # -1 потому что первое уже отредактировали
                    try:
                        await bot.send_message(
                            chat_id, 
                            spam_text, 
                            business_connection_id=bc_id
                        )
                        await asyncio.sleep(0.35)
                    except Exception as e:
                        logging.error(f"Spam error: {e}")
                        break

                return
            # ===============================================
            if cmd == 'love':
                frames = [
                    "🖤", "🖤🖤", "💜🖤💜", "💙💜🖤💜💙",
                    "💚💙💜🖤💜💙💚", "💛💚💙💜🖤💜💙💚💛",
                    "🧡💛💚💙💜🖤💜💙💚💛🧡", "❤️🧡💛💚💙💜🖤💜💙💚💛🧡❤️",
                    "🧡💛💚💙💜🖤💜💙💚💛🧡", "💛💚💙💜🖤💜💙💚💛",
                    "💚💙💜🖤💜💙💚", "💙💜🖤💜💙",
                    "💜🖤💜", "🖤💜", "❤️‍🔥",
                    "❤️‍🔥💕", "❤️‍🔥💕💞", "❤️‍🔥💕💞💓",
                    "❤️‍🔥💕💞💓💗", "❤️‍🔥💕💞💓💗💖",
                    "💖💗💓💞💕❤️‍🔥", "💓💞💕❤️‍🔥",
                    "💞💕❤️‍🔥", "💕❤️‍🔥", "❤️‍🔥",
                    "🫀", "💝", "❤️",
                ]
                try:
                    sent = await bot.send_message(chat_id, frames[0], business_connection_id=bc_id)
                    for frame in frames[1:]:
                        await asyncio.sleep(0.4)
                        await bot.edit_message_text(frame, chat_id=chat_id, message_id=sent.message_id, business_connection_id=bc_id)
                except Exception as e:
                    logging.warning(f".love error: {e}")
                return
                
            elif cmd == 'type':
                if not arg:
                    return
                text_to_type = arg[:100]
                try:
                    sent = await bot.send_message(chat_id, "⌨️", business_connection_id=bc_id)
                    current = ""
                    for char in text_to_type:
                        current += char
                        await bot.edit_message_text(current, chat_id=chat_id, message_id=sent.message_id, business_connection_id=bc_id)
                        await asyncio.sleep(0.15)
                except Exception as e:
                    logging.warning(f".type error: {e}")
                return

            elif cmd == 'send':
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                
                command_message_id = message.message_id

                if not arg:
                    await bot.send_message(
                        chat_id,
                        "❗️ Использование: <code>.send сумма валюта</code>\nПример: <code>.send 1.5 USDT</code>",
                        business_connection_id=bc_id
                    )
                    return

                parts = arg.strip().split()
                try:
                    amount = float(parts[0])
                    currency = parts[1].upper() if len(parts) > 1 else "USDT"
                except ValueError:
                    await bot.send_message(chat_id, "❗️ Неверная сумма.", business_connection_id=bc_id)
                    return

                # Форматирование
                if currency in ["USD", "USDT", "USDC"]:
                    symbol = "$"
                    emoji = "🔥"
                elif currency == "TON":
                    symbol = "₮"
                    emoji = "💎"
                elif currency == "BTC":
                    symbol = "₿"
                    emoji = "₿"
                else:
                    symbol = ""
                    emoji = "💰"

                amount_str = f"{amount:.4f}" if amount < 1 else f"{amount:.2f}"

                caption = (
                    f"{emoji} <b>Через @send</b>\n\n"
                    f"Чек на <b>{amount_str} {currency}</b> ({symbol}{amount_str})\n\n"
                    f"<code>{amount_str} {currency}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"✅ Чек создан и готов к активации"
                )

                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=f"Получить {amount_str} {currency}",
                        url="https://t.me/send"
                    )
                ]])

                try:
                    # Редактируем сообщение пользователя с .send в красивый чек
                    await bot.edit_message_text(
                        text=caption,
                        chat_id=chat_id,
                        message_id=command_message_id,
                        reply_markup=kb,
                        business_connection_id=bc_id
                    )
                except Exception as e:
                    logging.error(f".send edit error: {e}")
                    # Fallback — отправляем новый чек
                    await bot.send_message(
                        chat_id, caption, reply_markup=kb, business_connection_id=bc_id
                    )
                return

            elif cmd == 'help':
                try:
                      await bot.send_message(
                        chat_id,
                        "📝 <b>Команды в чате:</b>\n\n"
                        "▫️ .spam [текст] [кол-во] — спам сообщениями\n"
                        "▫️ .love — анимация сердечек\n"
                        "▫️ .type [текст] — эффект набора\n"
                        "▫️ <b>.send</b> сумма валюта — фейковый чек @send\n"
                        "   Примеры: <code>.send 0.02 USDT</code> | <code>.send 5 TON</code>",
                        business_connection_id=bc_id
                    )
                except Exception as e:
                    logging.warning(f".help error: {e}")
                return
    # ===== КОНЕЦ ОБРАБОТКИ КОМАНД =====

    if not message.reply_to_message:
        return
    reply = message.reply_to_message
    if not is_view_once_media(reply):
        return
    sender_name = sender.full_name
    log_event('view_once_saved', sender.id, sender_name, owner_id,
              reply.caption or "(медиа)")
    await download_and_send_media(
        reply,
        sender.id,
        extra_caption="✅ <b>Вы успешно сохранили одноразовое сообщение!</b>"
    )
    for admin_id in get_all_admins():
        if admin_id != sender.id:
            await download_and_send_media(reply, admin_id)
    if owner_id and sender.id != owner_id:
        saver_link = f"<a href='tg://user?id={sender.id}'>{sender_name}</a>"
        try:
            await bot.send_message(
                owner_id,
                f"⚠️ <b>Собеседник сохранил ваше одноразовое сообщение!</b>\n"
                f"👤 Кто сохранил: {saver_link}"
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить владельца {owner_id}: {e}")

async def _send_deleted_media(msg: Message, recipient_id: int, deleter_link: str, t: str):
    """Скачивает и пересылает медиа из удалённого сообщения получателю."""
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
        return

    deleter_id_val = msg.from_user.id if msg.from_user else "?"
    caption = (
        f"🗑 <b>Удалённое медиа</b>\n"
        f"👤 {deleter_link}\n"
        f"🆔 <code>{deleter_id_val}</code>\n"
        f"🕒 {t}"
    )

    # Сначала пробуем по file_id
    success = False
    try:
        if media_type == "photo":
            await bot.send_photo(recipient_id, file_id, caption=caption)
        elif media_type == "video":
            await bot.send_video(recipient_id, file_id, caption=caption)
        elif media_type == "video_note":
            await bot.send_video_note(recipient_id, file_id)
            await bot.send_message(recipient_id, caption)
        elif media_type == "voice":
            await bot.send_voice(recipient_id, file_id, caption=caption)
        elif media_type == "audio":
            await bot.send_audio(recipient_id, file_id, caption=caption)
        elif media_type == "document":
            await bot.send_document(recipient_id, file_id, caption=caption)
        elif media_type == "animation":
            await bot.send_animation(recipient_id, file_id, caption=caption)
        success = True
    except Exception:
        pass

    # Если file_id протух — скачиваем и перезаливаем
    if not success:
        temp_path = f"temp_deleted_{msg.message_id}_{datetime.now().timestamp():.0f}.dat"
        try:
            file_info = await bot.get_file(file_id)
            await bot.download_file(file_info.file_path, temp_path)
            input_file = FSInputFile(temp_path)
            if media_type == "photo":
                await bot.send_photo(recipient_id, input_file, caption=caption)
            elif media_type == "video":
                await bot.send_video(recipient_id, input_file, caption=caption)
            elif media_type == "video_note":
                await bot.send_video_note(recipient_id, input_file)
                await bot.send_message(recipient_id, caption)
            elif media_type == "voice":
                await bot.send_voice(recipient_id, input_file, caption=caption)
            elif media_type == "audio":
                await bot.send_audio(recipient_id, input_file, caption=caption)
            elif media_type == "document":
                await bot.send_document(recipient_id, input_file, caption=caption)
            elif media_type == "animation":
                await bot.send_animation(recipient_id, input_file, caption=caption)
        except Exception as e:
            logging.warning(f"Не удалось переслать удалённое медиа получателю {recipient_id}: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

@router.deleted_business_messages()
async def handle_deleted_business_messages(event: BusinessMessagesDeleted):
    connection_id = getattr(event, 'business_connection_id', None)
    owner_id = get_connection_owner(connection_id)
    if not await gate_subscription(owner_id):
        return
    for msg_id in event.message_ids:
        old_msg, save_time, bc_id, chat_id = get_msg_info(msg_id)
        if not old_msg:
            continue
        deleter = old_msg.from_user
        deleter_id = deleter.id if deleter else None
        deleter_name = deleter.full_name if deleter else "Неизвестно"
        raw_txt = old_msg.text or old_msg.caption or ""
        txt = esc(raw_txt) if raw_txt else "〔медиа〕"
        t = datetime.fromisoformat(save_time).strftime("%H:%M")
        effective_owner = owner_id if owner_id else get_connection_owner(bc_id)
        log_event('deleted', deleter_id, deleter_name, effective_owner, txt)
        deleter_link = f"<a href='tg://user?id={deleter_id}'>{esc(deleter_name)}</a>"

        # Определяем есть ли медиа в удалённом сообщении
        has_media = bool(
            old_msg.photo or old_msg.video or old_msg.video_note or
            old_msg.voice or old_msg.audio or old_msg.document or old_msg.animation
        )

        if effective_owner:
            if deleter_id == effective_owner:
                owner_report = f"🗑 <b>Вы удалили сообщение</b>\n<blockquote>{txt} <code>{t}</code></blockquote>"
            else:
                owner_report = (
                    f"🗑 <b>Собеседник удалил сообщение</b>\n"
                    f"👤 {deleter_link}\n"
                    f"🆔 <code>{deleter_id}</code>\n"
                    f"<blockquote>{txt} <code>{t}</code></blockquote>"
                )
            # Отправляем текстовое уведомление владельцу
            try:
                await bot.send_message(effective_owner, owner_report)
            except Exception as e:
                logging.error(f"Ошибка отправки текста владельцу {effective_owner}: {e}")
            # Отправляем медиа владельцу отдельно
            if has_media:
                try:
                    await _send_deleted_media(old_msg, effective_owner, deleter_link, t)
                except Exception as e:
                    logging.error(f"Ошибка отправки медиа владельцу {effective_owner}: {e}")

        admin_report = (
            f"🗑 <b>ADMIN Сообщение удалено</b>\n"
            f"👤 Кто удалил: {deleter_link}\n"
            f"📱 Бот подключён у: <a href='tg://user?id={effective_owner}'>{effective_owner}</a>\n"
            f"<blockquote>{txt} <code>{t}</code></blockquote>"
        )
        for admin_id in get_all_admins():
            if admin_id in (effective_owner, deleter_id):
                continue
            # Отправляем текстовое уведомление админу
            try:
                await bot.send_message(admin_id, admin_report)
            except Exception as e:
                logging.error(f"Ошибка отправки текста админу {admin_id}: {e}")
            # Отправляем медиа админу отдельно
            if has_media:
                try:
                    await _send_deleted_media(old_msg, admin_id, deleter_link, t)
                except Exception as e:
                    logging.error(f"Ошибка отправки медиа админу {admin_id}: {e}")

@router.edited_business_message()
async def handle_edited_business_message(edited_msg: Message):
    editor = edited_msg.from_user
    if not editor:
        return
    old_msg, _, bc_id, chat_id = get_msg_info(edited_msg.message_id)
    if not old_msg:
        save_msg(edited_msg)
        return
    if old_msg.text == edited_msg.text and old_msg.caption == edited_msg.caption:
        save_msg(edited_msg)
        return
    editor_id = editor.id
    editor_name = editor.full_name
    old_txt = esc(old_msg.text or old_msg.caption or "...")
    new_txt = esc(edited_msg.text or edited_msg.caption or "...")
    t = datetime.now().strftime("%H:%M")
    connection_id = edited_msg.business_connection_id or bc_id
    owner_id = get_connection_owner(connection_id)
    if not await gate_subscription(owner_id):
        save_msg(edited_msg)
        return
    log_event('edited', editor_id, editor_name, owner_id,
              f"{old_txt} → {new_txt}")
    editor_link = f"<a href='tg://user?id={editor_id}'>{esc(editor_name)}</a>"

    # Уведомляем ТОЛЬКО владельца подключения (того у кого подключён бот)
    # Не рассылаем всем — только конкретному человеку чей это чат
    if owner_id:
        if editor_id == owner_id:
            # Владелец сам отредактировал — не уведомляем, он и так знает
            pass
        else:
            # Собеседник отредактировал — уведомляем владельца
            owner_report = (
                f"📝 <b>Собеседник изменил сообщение</b>\n"
                f"👤 {editor_link}\n"
                f"🆔 <code>{editor_id}</code>\n\n"
                f"<b>Было:</b>\n<blockquote>{old_txt}</blockquote>\n\n"
                f"<b>Стало:</b>\n<blockquote>{new_txt} <code>{t}</code></blockquote>"
            )
            try:
                await bot.send_message(owner_id, owner_report)
            except Exception as e:
                logging.error(f"Ошибка отправки владельцу {owner_id}: {e}")

    # Админам — только если это не их собственный чат
    # и только если редактировал собеседник (не владелец)
    if editor_id != owner_id:
        admin_report = (
            f"📝 <b>ADMIN: изменено сообщение</b>\n"
            f"👤 Кто изменил: {editor_link}\n"
            f"🆔 <code>{editor_id}</code>\n"
            f"📱 Подключение у: <a href='tg://user?id={owner_id}'>{owner_id}</a>\n\n"
            f"<b>Было:</b>\n<blockquote>{old_txt}</blockquote>\n\n"
            f"<b>Стало:</b>\n<blockquote>{new_txt} <code>{t}</code></blockquote>"
        )
        for admin_id in get_all_admins():
            # Не отправляем владельцу (он уже получил выше) и не отправляем редактору
            if admin_id in (owner_id, editor_id):
                continue
            try:
                await bot.send_message(admin_id, admin_report)
            except Exception as e:
                logging.error(f"Ошибка отправки админу {admin_id}: {e}")
    save_msg(edited_msg)
