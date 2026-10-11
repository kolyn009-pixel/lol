"""Durable media store for the unified Adelia conversation.

External messenger URLs/file_ids are transport details only.  Every chat attachment
is copied into TutorBot storage and referenced by an opaque token so Telegram, VK
and Web all render the same durable object.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import uuid
from pathlib import Path

import database

MAX_BYTES = 20 * 1024 * 1024
_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")


def _root() -> Path:
    custom = str(os.getenv("ADELIA_MESSAGE_MEDIA_DIR") or "").strip()
    if custom:
        root = Path(custom)
    else:
        db_path = Path(database.current_db_name()).resolve()
        root = db_path.parent / "storage" / "message_media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(value):
    name = os.path.basename(str(value or "attachment")).strip() or "attachment"
    name = re.sub(r"[\\/\x00-\x1f]+", "_", name)
    return name[:180]


def _paths(token):
    if not _TOKEN_RE.fullmatch(str(token or "")):
        raise ValueError("invalid_media_token")
    folder = _root() / token[:2]
    return folder, folder / (token + ".json")


def store_bytes(student_id, content, filename, mime=None, kind=None, origin=None, external_ref=None, participant_type='STUDENT', participant_id=None):
    data = bytes(content or b"")
    if not data:
        raise ValueError("empty_media")
    if len(data) > MAX_BYTES:
        raise ValueError("media_too_large")
    uid = int(student_id)
    name = _safe_name(filename)
    ctype = str(mime or mimetypes.guess_type(name)[0] or "application/octet-stream").split(";", 1)[0].strip()
    token = uuid.uuid4().hex
    ext = Path(name).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", ext or ""):
        guessed = mimetypes.guess_extension(ctype) or ""
        ext = guessed if re.fullmatch(r"\.[a-z0-9]{1,10}", guessed or "") else ""
    folder, meta_path = _paths(token)
    folder.mkdir(parents=True, exist_ok=True)
    blob_path = folder / (token + ext)
    digest = hashlib.sha256(data).hexdigest()
    with open(blob_path, "xb") as fh:
        fh.write(data)
    os.chmod(blob_path, 0o640)
    meta = {
        "token": token,
        "student_id": uid,
        "participant_type": str(participant_type or "STUDENT").upper(),
        "participant_id": int(participant_id) if participant_id is not None else None,
        "kind": str(kind or ("photo" if ctype.startswith("image/") else "document")).lower(),
        "name": name,
        "mime": ctype,
        "size": len(data),
        "sha256": digest,
        "origin": str(origin or "SYSTEM").upper(),
        "external_ref": str(external_ref or "")[:500] or None,
        "blob": blob_path.name,
        "url": f"/api/message-media/{token}",
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    os.chmod(meta_path, 0o640)
    return dict(meta)


def metadata(token):
    folder, meta_path = _paths(str(token))
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    blob = folder / str(meta.get("blob") or "")
    if not blob.is_file():
        return None
    meta["path"] = str(blob)
    meta.setdefault("url", f"/api/message-media/{token}")
    return meta


def read(token):
    meta = metadata(token)
    if not meta:
        raise FileNotFoundError("media_not_found")
    path = Path(meta["path"])
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != str(meta.get("sha256") or ""):
        raise IOError("media_checksum_mismatch")
    return meta, data


def attachment_items(value):
    if not value:
        return []
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        items = value.get("items")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
        return [value]
    return []


def bundle(items):
    clean = [dict(x) for x in (items or []) if isinstance(x, dict)]
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    return {"kind": "bundle", "items": clean, "count": len(clean)}
