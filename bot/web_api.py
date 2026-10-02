"""HTTP API для входа и управления userbot из Mini App.

Работает в том же процессе, что и бот — общий _pending_login / Telethon.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.parse
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from bot.config import API_TOKEN
from bot.db import (
    delete_userbot_session,
    get_userbot_session,
    save_userbot_session,
    set_userbot_active,
)
from bot.userbot_manager import (
    clear_pending_login,
    complete_phone_login,
    is_userbot_running,
    notify_userbot_deleted,
    start_client,
    start_phone_login,
    stop_client,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Userbot Mini App API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validate_init_data(init_data: str) -> dict[str, Any]:
    """Проверка Telegram WebApp initData → user dict."""
    if not init_data or not init_data.strip():
        raise HTTPException(401, "Нет initData. Открой Mini App из бота.")
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        raise HTTPException(401, "Битый initData")
    check_hash = parsed.pop("hash", None)
    if not check_hash:
        raise HTTPException(401, "Нет hash в initData")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", API_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, check_hash):
        raise HTTPException(401, "Подпись initData неверна")
    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(401, "Нет user в initData")
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        raise HTTPException(401, "Битый user JSON")
    if not user.get("id"):
        raise HTTPException(401, "Нет user.id")
    return user


def _auth_user(init_data: str | None, x_init_data: str | None) -> int:
    raw = (init_data or x_init_data or "").strip()
    user = _validate_init_data(raw)
    return int(user["id"])


def _status_payload(uid: int) -> dict[str, Any]:
    row = get_userbot_session(uid)
    running = is_userbot_running(uid)
    if not row:
        return {
            "user_id": uid,
            "has_session": False,
            "active": False,
            "running": running,
            "status_text": "не подключён",
        }
    has_session = bool(row[0] and row[0] != "pending")
    active = bool(row[3])
    if has_session and active and running:
        status_text = "активен"
    elif has_session and active and not running:
        status_text = "в БД, но не запущен"
    elif has_session:
        status_text = "сохранён, выключен"
    else:
        status_text = "ожидает входа"
    return {
        "user_id": uid,
        "has_session": has_session,
        "active": active,
        "running": running,
        "api_id": row[1],
        "status_text": status_text,
    }


class InitBody(BaseModel):
    init_data: str = ""


class PhoneBody(BaseModel):
    init_data: str = ""
    api_id: int
    api_hash: str
    phone: str = Field(..., min_length=8)


class CodeBody(BaseModel):
    init_data: str = ""
    code: str = Field(..., min_length=3)
    password: str | None = None


class SessionBody(BaseModel):
    init_data: str = ""
    api_id: int | None = None
    api_hash: str | None = None
    session: str = Field(..., min_length=10)


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/userbot/status")
async def status(init_data: str = "", x_telegram_init_data: str | None = Header(None)):
    uid = _auth_user(init_data, x_telegram_init_data)
    return _status_payload(uid)


@app.post("/api/userbot/phone")
async def api_phone(body: PhoneBody, x_telegram_init_data: str | None = Header(None)):
    uid = _auth_user(body.init_data, x_telegram_init_data)
    phone = body.phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone.lstrip("+")
    save_userbot_session(uid, "pending", int(body.api_id), str(body.api_hash).strip())
    set_userbot_active(uid, False)
    msg = await start_phone_login(uid, phone, int(body.api_id), str(body.api_hash).strip())
    ok = not msg.startswith("❌")
    return {"ok": ok, "message": msg, "user_id": uid}


@app.post("/api/userbot/code")
async def api_code(body: CodeBody, x_telegram_init_data: str | None = Header(None)):
    uid = _auth_user(body.init_data, x_telegram_init_data)
    code = body.code.strip().replace(" ", "")
    msg, session = await complete_phone_login(uid, code, body.password)
    need_2fa = "2FA" in msg or "пароль" in msg.lower()
    ok = session is not None
    return {
        "ok": ok,
        "need_2fa": need_2fa and not ok,
        "message": msg,
        "user_id": uid,
        "has_session": bool(session),
        "status": _status_payload(uid) if ok else None,
    }


@app.post("/api/userbot/session")
async def api_session(body: SessionBody, x_telegram_init_data: str | None = Header(None)):
    uid = _auth_user(body.init_data, x_telegram_init_data)
    row = get_userbot_session(uid)
    api_id = body.api_id if body.api_id is not None else (row[1] if row else None)
    api_hash = body.api_hash if body.api_hash else (row[2] if row else None)
    if not api_id or not api_hash:
        raise HTTPException(400, "Нужны api_id и api_hash")
    session = body.session.strip()
    save_userbot_session(uid, session, int(api_id), str(api_hash))
    status_msg = await start_client(uid, session, int(api_id), str(api_hash))
    ok = not status_msg.startswith("❌")
    return {
        "ok": ok,
        "message": status_msg,
        "user_id": uid,
        "status": _status_payload(uid),
    }


@app.post("/api/userbot/on")
async def api_on(body: InitBody, x_telegram_init_data: str | None = Header(None)):
    uid = _auth_user(body.init_data, x_telegram_init_data)
    row = get_userbot_session(uid)
    if not row or not row[0] or row[0] == "pending":
        return {
            "ok": False,
            "message": "❌ Сессия не найдена. Сначала войди через API + телефон.",
            "status": _status_payload(uid),
        }
    set_userbot_active(uid, True)
    status_msg = await start_client(
        uid, row[0], row[1], row[2], notify_event="on", send_session_file=False
    )
    ok = not status_msg.startswith("❌")
    return {"ok": ok, "message": status_msg, "status": _status_payload(uid)}


@app.post("/api/userbot/off")
async def api_off(body: InitBody, x_telegram_init_data: str | None = Header(None)):
    uid = _auth_user(body.init_data, x_telegram_init_data)
    await stop_client(uid, notify=True)
    set_userbot_active(uid, False)
    return {
        "ok": True,
        "message": "⏸ Userbot выключен. Сессия сохранена.",
        "status": _status_payload(uid),
    }


@app.post("/api/userbot/delete")
async def api_delete(body: InitBody, x_telegram_init_data: str | None = Header(None)):
    uid = _auth_user(body.init_data, x_telegram_init_data)
    await stop_client(uid, notify=False)
    clear_pending_login(uid)
    delete_userbot_session(uid)
    await notify_userbot_deleted(uid)
    return {
        "ok": True,
        "message": "🗑 Сессия userbot удалена.",
        "status": _status_payload(uid),
    }
