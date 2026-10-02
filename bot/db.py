"""Работа с SQLite-базой business_bot.db."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from aiogram import types
from aiogram.types import Message

from bot.config import DB_PATH, OWNER_ID


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute(
        'INSERT OR REPLACE INTO settings (key, value) VALUES ("owner_id", ?)',
        (str(OWNER_ID),),
    )

    cursor.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            msg_id INTEGER NOT NULL,
            business_connection_id TEXT,
            chat_id INTEGER,
            raw_json TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(user_id, msg_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS business_connections (
            connection_id TEXT PRIMARY KEY,
            owner_user_id INTEGER NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            actor_user_id INTEGER,
            actor_name TEXT,
            connection_owner_id INTEGER,
            msg_text TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )

    cursor.execute("PRAGMA table_info(messages)")
    msg_columns = [row[1] for row in cursor.fetchall()]
    if "business_connection_id" not in msg_columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN business_connection_id TEXT")
    if "chat_id" not in msg_columns:
        cursor.execute("ALTER TABLE messages ADD COLUMN chat_id INTEGER")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER NOT NULL,
            invited_id INTEGER NOT NULL UNIQUE,
            timestamp TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS userbot_sessions (
            user_id INTEGER PRIMARY KEY,
            session_string TEXT NOT NULL,
            api_id INTEGER,
            api_hash TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_admin(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result


def save_msg(message: Message) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO messages "
        "(user_id, msg_id, business_connection_id, chat_id, raw_json, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            message.from_user.id,
            message.message_id,
            message.business_connection_id,
            message.chat.id if message.chat else None,
            message.model_dump_json(),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_msg_info(msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT raw_json, timestamp, business_connection_id, chat_id FROM messages WHERE msg_id = ?",
        (msg_id,),
    )
    res = cursor.fetchone()
    conn.close()
    if res:
        return types.Message.model_validate_json(res[0]), res[1], res[2], res[3]
    return None, None, None, None


def save_connection(connection_id: str, owner_user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO business_connections (connection_id, owner_user_id) VALUES (?, ?)",
        (connection_id, owner_user_id),
    )
    conn.commit()
    conn.close()


def get_connection_owner(connection_id: str) -> int | None:
    if not connection_id:
        return None
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT owner_user_id FROM business_connections WHERE connection_id = ?",
        (connection_id,),
    )
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None


def log_event(
    event_type: str,
    actor_user_id: int,
    actor_name: str,
    connection_owner_id: int,
    msg_text: str = "",
) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO events "
        "(event_type, actor_user_id, actor_name, connection_owner_id, msg_text, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            event_type,
            actor_user_id,
            actor_name,
            connection_owner_id,
            msg_text,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_recent_events(limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM messages")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users


def get_stats_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT user_id), COUNT(*) FROM messages")
    total_users, total_messages = cursor.fetchone() or (0, 0)
    cursor.execute(
        """
        SELECT user_id, COUNT(*) as count FROM messages
        GROUP BY user_id ORDER BY count DESC LIMIT 1
        """
    )
    most_active = cursor.fetchone()
    conn.close()
    return total_users, total_messages, most_active


def get_all_admins():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins")
    admins = [row[0] for row in cursor.fetchall()]
    conn.close()
    return admins


def cleanup_db():
    """Удаляет записи старше 7 дней из таблиц messages и events."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE timestamp < datetime('now', '-7 days')")
    deleted_msgs = cursor.rowcount
    cursor.execute("DELETE FROM events WHERE timestamp < datetime('now', '-7 days')")
    deleted_events = cursor.rowcount
    conn.commit()
    conn.close()
    logging.info(
        f"🧹 Очистка БД: удалено {deleted_msgs} сообщений и {deleted_events} событий старше 7 дней"
    )
    return deleted_msgs, deleted_events


def clear_db() -> dict:
    """Полная очистка таблиц messages и events."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages")
    msgs_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM events")
    events_count = cursor.fetchone()[0]
    cursor.execute("DELETE FROM messages")
    cursor.execute("DELETE FROM events")
    conn.commit()
    conn.close()
    logging.info(
        f"🗑 Полная очистка БД: удалено {msgs_count} сообщений и {events_count} событий"
    )
    return {"messages": msgs_count, "events": events_count}


def add_referral(inviter_id: int, invited_id: int) -> bool:
    if inviter_id == invited_id:
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO referrals (inviter_id, invited_id, timestamp) VALUES (?, ?, ?)",
            (inviter_id, invited_id, datetime.now().isoformat()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_referral_count(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_referral_inviter(invited_id: int) -> int | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT inviter_id FROM referrals WHERE invited_id = ?", (invited_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_top_referrers(limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT inviter_id, COUNT(*) as cnt FROM referrals "
        "GROUP BY inviter_id ORDER BY cnt DESC LIMIT ?",
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def add_admin(user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()


def remove_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return False
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True


def get_last_messages(limit: int = 50, user_id: int | None = None):
    limit = max(1, min(300, limit))
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if user_id:
        cursor.execute(
            "SELECT user_id, msg_id, raw_json, timestamp FROM messages "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
    else:
        cursor.execute(
            "SELECT user_id, msg_id, raw_json, timestamp FROM messages "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_last_media(limit: int = 10, user_id: int | None = None):
    limit = max(1, min(50, limit))
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if user_id:
        cursor.execute(
            "SELECT user_id, msg_id, raw_json, timestamp FROM messages "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 1000",
            (user_id,),
        )
    else:
        cursor.execute(
            "SELECT user_id, msg_id, raw_json, timestamp FROM messages "
            "ORDER BY id DESC LIMIT 1000"
        )
    rows = cursor.fetchall()
    conn.close()

    media_rows = []
    for row in rows:
        try:
            msg = types.Message.model_validate_json(row[2])
            if (
                msg.photo
                or msg.video
                or msg.video_note
                or msg.voice
                or msg.audio
                or msg.document
                or msg.animation
            ):
                media_rows.append(row)
                if len(media_rows) >= limit:
                    break
        except Exception:
            pass
    return media_rows


def user_has_connections(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM business_connections WHERE owner_user_id = ? LIMIT 1",
        (user_id,),
    )
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_chat_log_both_sides(owner_id: int, target_user_id: int, limit: int = 100):
    """Сообщения обеих сторон за последние 7 дней в чатах владельца."""
    limit = max(1, min(300, limit))
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT m.chat_id FROM messages m "
        "JOIN business_connections bc ON m.business_connection_id = bc.connection_id "
        "WHERE bc.owner_user_id = ? AND m.user_id = ? AND m.chat_id IS NOT NULL "
        "AND m.timestamp >= datetime('now', '-7 days')",
        (owner_id, target_user_id),
    )
    chat_ids = [r[0] for r in cursor.fetchall()]
    if not chat_ids:
        cursor.execute(
            "SELECT m.user_id, m.msg_id, m.raw_json, m.timestamp, m.chat_id "
            "FROM messages m "
            "JOIN business_connections bc ON m.business_connection_id = bc.connection_id "
            "WHERE bc.owner_user_id = ? AND m.user_id = ? "
            "AND m.timestamp >= datetime('now', '-7 days') "
            "ORDER BY m.id DESC LIMIT ?",
            (owner_id, target_user_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        return rows
    placeholders = ",".join("?" * len(chat_ids))
    cursor.execute(
        "SELECT m.user_id, m.msg_id, m.raw_json, m.timestamp, m.chat_id "
        "FROM messages m "
        "JOIN business_connections bc ON m.business_connection_id = bc.connection_id "
        "WHERE bc.owner_user_id = ? AND m.chat_id IN (" + placeholders + ") "
        "AND m.timestamp >= datetime('now', '-7 days') "
        "ORDER BY m.id DESC LIMIT ?",
        (owner_id, *chat_ids, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def parse_log_message_row(user_id, msg_id, raw_json, timestamp, chat_id):
    """Разбирает строку из БД в словарь для лога/CSV."""
    try:
        msg = types.Message.model_validate_json(raw_json)
    except Exception:
        return None
    txt = msg.text or msg.caption or ""
    media_type = ""
    if msg.photo:
        media_type = "photo"
    elif msg.video:
        media_type = "video"
    elif msg.video_note:
        media_type = "video_note"
    elif msg.voice:
        media_type = "voice"
    elif msg.audio:
        media_type = "audio"
    elif msg.document:
        media_type = "document"
    elif msg.animation:
        media_type = "animation"
    elif msg.sticker:
        media_type = "sticker"
    name = msg.from_user.full_name if msg.from_user else f"ID {user_id}"
    uid = msg.from_user.id if msg.from_user else user_id
    username = (getattr(msg.from_user, "username", None) or "") if msg.from_user else ""
    try:
        t = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        t = timestamp or ""
    return {
        "user_id": uid,
        "name": name,
        "username": username,
        "msg_id": msg_id,
        "chat_id": chat_id,
        "timestamp": t,
        "media_type": media_type,
        "text": txt,
    }


# ---------- userbot sessions ----------

def save_userbot_session(
    user_id: int,
    session_string: str,
    api_id: int | None = None,
    api_hash: str | None = None,
) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO userbot_sessions "
        "(user_id, session_string, api_id, api_hash, is_active, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        (user_id, session_string, api_id, api_hash, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_userbot_session(user_id: int):
    """Возвращает (session_string, api_id, api_hash, is_active) или None."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT session_string, api_id, api_hash, is_active FROM userbot_sessions WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def set_userbot_active(user_id: int, active: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE userbot_sessions SET is_active = ? WHERE user_id = ?",
        (1 if active else 0, user_id),
    )
    conn.commit()
    conn.close()


def delete_userbot_session(user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM userbot_sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_all_active_userbot_sessions():
    """Список (user_id, session_string, api_id, api_hash) для активных сессий."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, session_string, api_id, api_hash FROM userbot_sessions WHERE is_active = 1"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_all_userbot_sessions():
    """Все сессии: (user_id, session_string, api_id, api_hash, is_active, created_at)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id, session_string, api_id, api_hash, is_active, created_at "
        "FROM userbot_sessions ORDER BY created_at DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows
