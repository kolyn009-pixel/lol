from __future__ import annotations

import json
import mimetypes
import os
import random
import uuid
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import database

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
VK_TOKEN = os.getenv("VK_TOKEN", "").strip()
VK_API_VERSION = os.getenv("VK_API_VERSION", "5.199").strip() or "5.199"


def _json_request(url, data=None, headers=None, timeout=40):
    body = None
    hdr = {"User-Agent": "TutorBot-Attachment/1.0"}
    if headers:
        hdr.update(headers)
    if data is not None:
        body = data if isinstance(data, (bytes, bytearray)) else urlencode(data).encode("utf-8")
        if not headers or "Content-Type" not in headers:
            hdr["Content-Type"] = "application/x-www-form-urlencoded"
    with urlopen(Request(url, data=body, headers=hdr), timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _bytes_request(url, timeout=60):
    with urlopen(Request(url, headers={"User-Agent": "TutorBot-Attachment/1.0"}), timeout=timeout) as resp:
        return resp.read()


def _multipart(fields, files):
    boundary = "----TutorBot" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks += [f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), str(value).encode("utf-8"), b"\r\n"]
    for field, filename, content, content_type in files:
        chunks += [f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode("utf-8"), f"Content-Type: {content_type}\r\n\r\n".encode(), content, b"\r\n"]
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _vk_api(method, **params):
    if not VK_TOKEN:
        raise RuntimeError("VK_TOKEN is not configured")
    payload = dict(params); payload["access_token"] = VK_TOKEN; payload["v"] = VK_API_VERSION
    data = _json_request(f"https://api.vk.com/method/{method}", payload)
    if "error" in data:
        raise RuntimeError(f"VK API {method}: {data['error']}")
    return data.get("response")


def _vk_peer(user_id):
    c = database.connect()
    try:
        row = c.execute("SELECT external_id FROM channel_identities WHERE user_id=? AND channel='VK' AND enabled=1 LIMIT 1", (int(user_id),)).fetchone()
        return int(row["external_id"]) if row else None
    finally:
        c.close()


def telegram_file_bytes(file_id):
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured")
    info = _json_request(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile", {"file_id": str(file_id)})
    if not info.get("ok"):
        raise RuntimeError(f"Telegram getFile failed: {info}")
    return _bytes_request(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{info['result']['file_path']}")


def telegram_send_bytes(chat_id, content, filename, caption="", as_photo=False, content_type=None):
    if not BOT_TOKEN or not chat_id:
        return False
    method = "sendPhoto" if as_photo else "sendDocument"; field = "photo" if as_photo else "document"
    ctype = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body, form_type = _multipart({"chat_id": int(chat_id), "caption": str(caption or "")[:1000]}, [(field, filename, content, ctype)])
    try:
        result = _json_request(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", body, {"Content-Type": form_type}, timeout=60)
        return bool(result.get("ok"))
    except Exception as exc:
        print("ATTACHMENT TELEGRAM SEND ERROR:", repr(exc)); return False


def _vk_upload_document(peer_id, content, filename, content_type=None):
    server = _vk_api("docs.getMessagesUploadServer", peer_id=int(peer_id), type="doc")
    ctype = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body, form_type = _multipart({}, [("file", filename, content, ctype)])
    uploaded = _json_request(server["upload_url"], body, {"Content-Type": form_type}, timeout=90)
    saved = _vk_api("docs.save", file=uploaded["file"], title=filename)
    doc = (saved.get("doc") if isinstance(saved, dict) else None) or (saved[0] if isinstance(saved, list) and saved else None)
    if not doc:
        raise RuntimeError(f"VK docs.save returned no document: {saved}")
    key = f"doc{doc['owner_id']}_{doc['id']}"
    if doc.get("access_key"): key += f"_{doc['access_key']}"
    return key


def _vk_upload_photo(peer_id, content, filename="image.jpg", content_type="image/jpeg"):
    server = _vk_api("photos.getMessagesUploadServer", peer_id=int(peer_id))
    body, form_type = _multipart({}, [("photo", filename, content, content_type or "image/jpeg")])
    uploaded = _json_request(server["upload_url"], body, {"Content-Type": form_type}, timeout=90)
    saved = _vk_api("photos.saveMessagesPhoto", photo=uploaded["photo"], server=uploaded["server"], hash=uploaded["hash"])
    photo = saved[0] if saved else None
    if not photo:
        raise RuntimeError("VK photo save returned no photo")
    key = f"photo{photo['owner_id']}_{photo['id']}"
    if photo.get("access_key"): key += f"_{photo['access_key']}"
    return key


def vk_send_bytes(peer_id, content, filename, caption="", as_photo=False, content_type=None):
    try:
        attachment = _vk_upload_photo(peer_id, content, filename, content_type or "image/jpeg") if as_photo else _vk_upload_document(peer_id, content, filename, content_type)
        _vk_api("messages.send", peer_id=int(peer_id), random_id=random.randint(1, 2_000_000_000), message=str(caption or ""), attachment=attachment)
        return True
    except Exception as exc:
        print("ATTACHMENT VK SEND ERROR:", repr(exc)); return False


def telegram_to_student(user_id, file_id, filename, caption="", as_photo=False, content_type=None):
    content = telegram_file_bytes(file_id); user = database.get_user(int(user_id)); tg_ok = vk_ok = False
    if user and user["telegram_id"]:
        tg_ok = telegram_send_bytes(int(user["telegram_id"]), content, filename, caption, as_photo, content_type)
    peer = _vk_peer(int(user_id))
    if peer:
        vk_ok = vk_send_bytes(peer, content, filename, caption, as_photo, content_type)
    return {"telegram": tg_ok, "vk": vk_ok}


def vk_attachment_descriptor(item):
    kind = str(item.get("type") or ""); obj = item.get(kind) or {}
    if kind == "doc":
        return {"kind":"document","url":obj.get("url"),"filename":obj.get("title") or f"document_{obj.get('id','')}","content_type":mimetypes.guess_type(obj.get("title") or "")[0] or "application/octet-stream","vk_key":"doc%s_%s%s" % (obj.get("owner_id"),obj.get("id"),("_"+str(obj.get("access_key"))) if obj.get("access_key") else "")}
    if kind == "photo":
        sizes = obj.get("sizes") or []; best = max(sizes, key=lambda x:int(x.get("width",0))*int(x.get("height",0)), default={})
        return {"kind":"photo","url":best.get("url"),"filename":f"photo_{obj.get('id','')}.jpg","content_type":"image/jpeg","vk_key":"photo%s_%s%s" % (obj.get("owner_id"),obj.get("id"),("_"+str(obj.get("access_key"))) if obj.get("access_key") else "")}
    return None


def _descriptors(attachments):
    return [d for d in (vk_attachment_descriptor(x) for x in (attachments or [])) if d and d.get("url")]


def _send_existing_vk(peer, descriptors, caption=""):
    if not peer or not descriptors:
        return 0
    _vk_api("messages.send", peer_id=int(peer), random_id=random.randint(1,2_000_000_000), message=str(caption or ""), attachment=",".join(x["vk_key"] for x in descriptors if x.get("vk_key")))
    return len(descriptors)


def vk_forward_to_student(user_id, attachments, caption=""):
    user = database.get_user(int(user_id)); peer = _vk_peer(int(user_id)); result = {"telegram":0,"vk":0}; descriptors = _descriptors(attachments)
    if peer and descriptors:
        try: result["vk"] = _send_existing_vk(peer, descriptors, caption)
        except Exception as exc: print("ATTACHMENT VK FORWARD ERROR:", repr(exc))
    if user and user["telegram_id"]:
        for item in descriptors:
            try:
                content = _bytes_request(item["url"], timeout=90)
                if telegram_send_bytes(int(user["telegram_id"]),content,item["filename"],caption,item["kind"]=="photo",item["content_type"]): result["telegram"] += 1
            except Exception as exc: print("ATTACHMENT VK->TG ERROR:", repr(exc))
    return result


def vk_forward_to_admin_telegram(attachments, caption=""):
    from core import admin_roles
    descriptors = _descriptors(attachments); sent = 0
    for admin in admin_roles.list_admins():
        if not admin["active"] or not admin["telegram_id"]: continue
        for item in descriptors:
            try:
                content = _bytes_request(item["url"], timeout=90)
                if telegram_send_bytes(int(admin["telegram_id"]),content,item["filename"],caption,item["kind"]=="photo",item["content_type"]): sent += 1
            except Exception as exc: print("ATTACHMENT VK->ADMIN TG ERROR:", repr(exc))
    return sent


def vk_forward_to_admin_vk(attachments, caption=""):
    from . import schema
    descriptors = _descriptors(attachments); sent = 0
    for peer in schema.get_admin_external_ids("VK"):
        try: sent += _send_existing_vk(int(peer), descriptors, caption)
        except Exception as exc: print("ATTACHMENT VK->ADMIN VK ERROR:", repr(exc))
    return sent
