from __future__ import annotations

import json
import re
from typing import Iterable

import database


def initialize():
    conn = database.connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS homework_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                homework_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                filename TEXT,
                mime_type TEXT,
                telegram_file_id TEXT,
                vk_attachment_key TEXT,
                vk_url TEXT,
                source_channel TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(homework_id, kind, COALESCE(telegram_file_id,''), COALESCE(vk_attachment_key,''), COALESCE(filename,''))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_homework_attachments_hw ON homework_attachments(homework_id,id)"
        )
        conn.commit()
    finally:
        conn.close()


def _now():
    return database.now_iso()


def _normalize_kind(value):
    value = str(value or "document").lower()
    return "photo" if value in {"photo", "image", "picture"} else "document"


def save_reference(
    homework_id: int,
    *,
    kind: str,
    filename: str | None = None,
    mime_type: str | None = None,
    telegram_file_id: str | None = None,
    vk_attachment_key: str | None = None,
    vk_url: str | None = None,
    source_channel: str | None = None,
):
    initialize()
    now = _now()
    conn = database.connect()
    try:
        existing = conn.execute(
            """
            SELECT id FROM homework_attachments
            WHERE homework_id=?
              AND kind=?
              AND COALESCE(telegram_file_id,'')=COALESCE(?, '')
              AND COALESCE(vk_attachment_key,'')=COALESCE(?, '')
              AND COALESCE(filename,'')=COALESCE(?, '')
            LIMIT 1
            """,
            (
                int(homework_id),
                _normalize_kind(kind),
                telegram_file_id,
                vk_attachment_key,
                filename,
            ),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE homework_attachments
                SET mime_type=COALESCE(?,mime_type),
                    telegram_file_id=COALESCE(?,telegram_file_id),
                    vk_attachment_key=COALESCE(?,vk_attachment_key),
                    vk_url=COALESCE(?,vk_url),
                    source_channel=COALESCE(?,source_channel),
                    updated_at=?
                WHERE id=?
                """,
                (
                    mime_type,
                    telegram_file_id,
                    vk_attachment_key,
                    vk_url,
                    source_channel,
                    now,
                    int(existing["id"]),
                ),
            )
            conn.commit()
            return int(existing["id"])

        cur = conn.execute(
            """
            INSERT INTO homework_attachments(
                homework_id,kind,filename,mime_type,
                telegram_file_id,vk_attachment_key,vk_url,
                source_channel,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                int(homework_id),
                _normalize_kind(kind),
                filename,
                mime_type,
                telegram_file_id,
                vk_attachment_key,
                vk_url,
                source_channel,
                now,
                now,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_for_homework(homework_id: int):
    initialize()
    conn = database.connect()
    try:
        return list(
            conn.execute(
                "SELECT * FROM homework_attachments WHERE homework_id=? ORDER BY id",
                (int(homework_id),),
            ).fetchall()
        )
    finally:
        conn.close()


def count_for_homework(homework_id: int):
    initialize()
    conn = database.connect()
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM homework_attachments WHERE homework_id=?",
                (int(homework_id),),
            ).fetchone()["n"]
            or 0
        )
    finally:
        conn.close()


def save_vk_descriptors(homework_id: int, descriptors: Iterable[dict]):
    ids = []
    for item in descriptors or []:
        ids.append(
            save_reference(
                int(homework_id),
                kind=item.get("kind") or "document",
                filename=item.get("filename"),
                mime_type=item.get("content_type"),
                vk_attachment_key=item.get("vk_key"),
                vk_url=item.get("url"),
                source_channel="VK",
            )
        )
    return ids


def set_telegram_file_id(attachment_id: int, telegram_file_id: str):
    if not telegram_file_id:
        return
    initialize()
    conn = database.connect()
    try:
        conn.execute(
            "UPDATE homework_attachments SET telegram_file_id=?,updated_at=? WHERE id=?",
            (str(telegram_file_id), _now(), int(attachment_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _extract_tg_file_id(result: dict, kind: str):
    if not isinstance(result, dict):
        return None
    message = result.get("result") or result
    if _normalize_kind(kind) == "photo":
        photos = message.get("photo") or []
        if photos:
            return photos[-1].get("file_id")
    doc = message.get("document") or {}
    return doc.get("file_id")


def _telegram_send_remote(chat_id: int, item, caption=""):
    from vk_adapter import attachment_bridge as bridge

    file_id = item["telegram_file_id"]
    method = "sendPhoto" if item["kind"] == "photo" else "sendDocument"
    field = "photo" if item["kind"] == "photo" else "document"
    if not bridge.BOT_TOKEN:
        return False

    try:
        if file_id:
            result = bridge._json_request(
                f"https://api.telegram.org/bot{bridge.BOT_TOKEN}/{method}",
                {
                    "chat_id": int(chat_id),
                    field: str(file_id),
                    "caption": str(caption or "")[:1000],
                },
            )
            return bool(result.get("ok"))

        if item["vk_url"]:
            content = bridge._bytes_request(item["vk_url"], timeout=90)
            ctype = item["mime_type"] or "image/jpeg" if item["kind"] == "photo" else "application/octet-stream"
            body, form_type = bridge._multipart(
                {"chat_id": int(chat_id), "caption": str(caption or "")[:1000]},
                [(field, item["filename"] or ("image.jpg" if item["kind"] == "photo" else "document"), content, ctype)],
            )
            result = bridge._json_request(
                f"https://api.telegram.org/bot{bridge.BOT_TOKEN}/{method}",
                body,
                {"Content-Type": form_type},
                timeout=90,
            )
            if result.get("ok"):
                new_id = _extract_tg_file_id(result, item["kind"])
                if new_id:
                    set_telegram_file_id(int(item["id"]), new_id)
                return True
    except Exception as exc:
        print("HOMEWORK ATTACHMENT TG SEND ERROR:", repr(exc))
    return False


def _vk_send_remote(peer_id: int, item, caption=""):
    from vk_adapter import attachment_bridge as bridge

    try:
        if item["vk_attachment_key"]:
            bridge._vk_api(
                "messages.send",
                peer_id=int(peer_id),
                random_id=__import__("random").randint(1, 2_000_000_000),
                message=str(caption or ""),
                attachment=str(item["vk_attachment_key"]),
            )
            return True

        if item["telegram_file_id"]:
            content = bridge.telegram_file_bytes(item["telegram_file_id"])
            key = (
                bridge._vk_upload_photo(peer_id, content, item["filename"] or "image.jpg", item["mime_type"] or "image/jpeg")
                if item["kind"] == "photo"
                else bridge._vk_upload_document(peer_id, content, item["filename"] or "document", item["mime_type"])
            )
            bridge._vk_api(
                "messages.send",
                peer_id=int(peer_id),
                random_id=__import__("random").randint(1, 2_000_000_000),
                message=str(caption or ""),
                attachment=key,
            )
            conn = database.connect()
            try:
                conn.execute(
                    "UPDATE homework_attachments SET vk_attachment_key=?,updated_at=? WHERE id=?",
                    (key, _now(), int(item["id"])),
                )
                conn.commit()
            finally:
                conn.close()
            return True
    except Exception as exc:
        print("HOMEWORK ATTACHMENT VK SEND ERROR:", repr(exc))
    return False


def resend_to_student(homework_id: int, caption=""):
    homework = database.get_homework(int(homework_id))
    if not homework:
        return {"telegram": 0, "vk": 0, "count": 0}
    user = database.get_user(int(homework["user_id"]))
    rows = list_for_homework(int(homework_id))
    result = {"telegram": 0, "vk": 0, "count": len(rows)}
    if not user:
        return result

    vk_peer = None
    try:
        from vk_adapter.service import vk_peer_for_user
        vk_peer = vk_peer_for_user(int(user["id"]))
    except Exception:
        pass

    for item in rows:
        if user["telegram_id"] and _telegram_send_remote(int(user["telegram_id"]), item, caption):
            result["telegram"] += 1
        if vk_peer and _vk_send_remote(int(vk_peer), item, caption):
            result["vk"] += 1
    return result


def send_to_admin_telegram(homework_id: int, chat_id: int, caption=""):
    rows = list_for_homework(int(homework_id))
    sent = 0
    for item in rows:
        if _telegram_send_remote(int(chat_id), item, caption):
            sent += 1
    return sent


def install_vk_bridge():
    """Persist refs whenever the existing VK homework delivery forwards attachments.

    Existing non-homework attachment forwarding is left unchanged. Homework id is
    recognized from the caption generated by vk_adapter.app ("ДЗ #123").
    """
    from vk_adapter import attachment_bridge as bridge

    current = bridge.vk_forward_to_student
    if getattr(current, "_homework_refs_installed", False):
        return

    def wrapped(user_id, attachments, caption=""):
        match = re.search(r"ДЗ\s*#(\d+)", str(caption or ""), re.I)
        if not match:
            return current(user_id, attachments, caption)

        homework_id = int(match.group(1))
        descriptors = bridge._descriptors(attachments)
        ids = save_vk_descriptors(homework_id, descriptors)
        result = {"telegram": 0, "vk": 0}
        user = database.get_user(int(user_id))
        peer = bridge._vk_peer(int(user_id))

        if peer and descriptors:
            try:
                result["vk"] = bridge._send_existing_vk(peer, descriptors, caption)
            except Exception as exc:
                print("HOMEWORK VK SEND ERROR:", repr(exc))

        if user and user["telegram_id"]:
            for attachment_id in ids:
                conn = database.connect()
                try:
                    row = conn.execute(
                        "SELECT * FROM homework_attachments WHERE id=?",
                        (int(attachment_id),),
                    ).fetchone()
                finally:
                    conn.close()
                if row and _telegram_send_remote(int(user["telegram_id"]), row, caption):
                    result["telegram"] += 1
        return result

    wrapped._homework_refs_installed = True
    bridge.vk_forward_to_student = wrapped


initialize()
