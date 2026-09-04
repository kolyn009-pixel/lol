from __future__ import annotations

import json
import os
import random
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import database

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()


def vk_peer(user_id: int):
    c = database.connect()
    try:
        row = c.execute(
            """
            SELECT external_id
            FROM channel_identities
            WHERE user_id=? AND channel='VK' AND enabled=1
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
        return int(row["external_id"]) if row else None
    finally:
        c.close()


def telegram_chat(user_id: int):
    user = database.get_user(int(user_id))
    if not user or not user["telegram_id"]:
        return None
    return int(user["telegram_id"])


def send_telegram_chat(chat_id: int, text: str):
    if not BOT_TOKEN or not chat_id:
        return False
    payload = urlencode({"chat_id": int(chat_id), "text": str(text)}).encode("utf-8")
    req = Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "TutorBot-Channel/1.0"},
    )
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(data.get("ok"))
    except Exception as exc:
        print("CHANNEL TELEGRAM SEND ERROR:", repr(exc))
        return False


def send_telegram(user_id: int, text: str):
    chat_id = telegram_chat(int(user_id))
    return send_telegram_chat(chat_id, text) if chat_id else False


def send_vk(user_id: int, text: str):
    peer = vk_peer(int(user_id))
    if not peer:
        return False
    try:
        from . import app as vk_app
        vk_app.send(peer, str(text), linked=True)
        return True
    except Exception as exc:
        print("CHANNEL VK SEND ERROR:", repr(exc))
        return False


def send_student(user_id: int, text: str, telegram=True, vk=True):
    result = {"telegram": False, "vk": False}
    if telegram:
        result["telegram"] = send_telegram(int(user_id), text)
    if vk:
        result["vk"] = send_vk(int(user_id), text)
    return result
