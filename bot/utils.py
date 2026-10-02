"""Вспомогательные функции."""
from __future__ import annotations

import html
import logging
import os
from datetime import datetime

from aiogram.types import Message, FSInputFile

from bot.loader import bot


def esc(text: str) -> str:
    """Экранирует спецсимволы HTML."""
    return html.escape(str(text)) if text else ""


def is_view_once_media(message: Message) -> bool:
    if not message:
        return False
    if message.has_protected_content or message.has_media_spoiler:
        return True
    has_media = bool(
        message.photo
        or message.video
        or message.video_note
        or message.voice
        or message.animation
        or message.audio
        or message.document
    )
    if has_media and message.has_protected_content:
        return True
    if message.video and getattr(message.video, "duration", 0) == 0:
        return True
    return False


async def download_and_send_media(
    original_msg: Message, recipient_id: int, extra_caption: str = ""
) -> bool:
    try:
        media = None
        media_type = None
        if original_msg.photo:
            media = original_msg.photo[-1]
            media_type = "photo"
        elif original_msg.video:
            media = original_msg.video
            media_type = "video"
        elif original_msg.video_note:
            media = original_msg.video_note
            media_type = "video_note"
        elif original_msg.voice:
            media = original_msg.voice
            media_type = "voice"
        if not media:
            return False
        file_info = await bot.get_file(media.file_id)
        file_path = f"temp_{media.file_id}_{datetime.now().timestamp():.0f}.dat"
        await bot.download_file(file_info.file_path, file_path)
        user_link = (
            f"<a href='tg://user?id={original_msg.from_user.id}'>"
            f"{original_msg.from_user.full_name}</a>"
        )
        caption = (
            f"💾 <b>⚠️ ОДНОРАЗОВОЕ сообщение сохранено!</b>\n"
            f"👤 От: {user_link}\n"
            f"🕒 {datetime.now().strftime('%H:%M:%S')}"
        )
        if original_msg.caption:
            caption += f"\n📝 Текст: {original_msg.caption}"
        if extra_caption:
            caption += f"\n{extra_caption}"
        if media_type == "photo":
            await bot.send_photo(recipient_id, FSInputFile(file_path), caption=caption)
        elif media_type == "video":
            await bot.send_video(recipient_id, FSInputFile(file_path), caption=caption)
        elif media_type == "video_note":
            await bot.send_video_note(recipient_id, FSInputFile(file_path))
            if caption:
                await bot.send_message(recipient_id, caption)
        elif media_type == "voice":
            await bot.send_voice(recipient_id, FSInputFile(file_path), caption=caption)
        if os.path.exists(file_path):
            os.remove(file_path)
        return True
    except Exception as e:
        logging.error(f"Ошибка при сохранении одноразового медиа для {recipient_id}: {e}")
        return False
