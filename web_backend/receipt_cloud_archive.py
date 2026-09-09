"""Stage 13: durable receipt archive on Yandex Disk.

The accounting database remains the source of truth. Receipt files are copied to
cloud storage asynchronously; payment/receipt processing never waits for Yandex
Disk. Failed uploads are retried with bounded exponential backoff.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from database import connect, now_iso

DISK_API = "https://cloud-api.yandex.net/v1/disk"
TELEGRAM_API = "https://api.telegram.org"
ARCHIVE_ROOT = os.getenv("ADELIA_RECEIPT_ARCHIVE_ROOT", "/TutorBot/Receipts").rstrip("/")
MAX_RECEIPT_BYTES = 25 * 1024 * 1024
MAX_ATTEMPTS = 12


def ensure_table():
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS receipt_cloud_archives (
            receipt_id INTEGER PRIMARY KEY,
            provider TEXT NOT NULL DEFAULT 'YANDEX_DISK',
            remote_path TEXT,
            sha256 TEXT,
            size_bytes INTEGER,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            archived_at TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_receipt_cloud_archive_status
            ON receipt_cloud_archives(status, updated_at);
        """
    )
    conn.commit(); conn.close()


def configured():
    return bool(os.getenv("YANDEX_DISK_OAUTH_TOKEN", "").strip())


def _safe_name(value, fallback="receipt"):
    text = re.sub(r"[^0-9A-Za-zА-Яа-я._-]+", "_", str(value or "").strip(), flags=re.UNICODE)
    text = text.strip("._-")[:80]
    return text or fallback


def _ext(file_type):
    value = str(file_type or "").strip().lower().lstrip(".")
    return value if value in {"pdf", "jpg", "jpeg", "png", "webp"} else "bin"


def _receipt(receipt_id):
    conn = connect()
    row = conn.execute(
        """
        SELECT r.id,r.payment_id,r.user_id,r.telegram_file_id,r.source_platform,
               r.file_type,r.created_at,u.name
        FROM receipts r JOIN users u ON u.id=r.user_id
        WHERE r.id=? LIMIT 1
        """,
        (int(receipt_id),),
    ).fetchone()
    conn.close(); return dict(row) if row else None


def _telegram_bytes(file_id):
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token: raise RuntimeError("telegram_bot_token_missing")
    q = urlencode({"file_id": str(file_id)})
    with urlopen(f"{TELEGRAM_API}/bot{token}/getFile?{q}", timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("ok") or not (payload.get("result") or {}).get("file_path"):
        raise RuntimeError("telegram_file_lookup_failed")
    remote = payload["result"]["file_path"]
    with urlopen(f"{TELEGRAM_API}/file/bot{token}/{quote(remote, safe='/')}", timeout=30) as resp:
        length = int(resp.headers.get("Content-Length") or 0)
        if length > MAX_RECEIPT_BYTES: raise RuntimeError("receipt_file_too_large")
        data = resp.read(MAX_RECEIPT_BYTES + 1)
    if len(data) > MAX_RECEIPT_BYTES: raise RuntimeError("receipt_file_too_large")
    return data


def _disk_request(method, path, params=None, data=None, content_type=None):
    token = os.getenv("YANDEX_DISK_OAUTH_TOKEN", "").strip()
    if not token: raise RuntimeError("yandex_disk_token_missing")
    url = DISK_API + path
    if params: url += "?" + urlencode(params)
    headers = {"Authorization": f"OAuth {token}", "Accept": "application/json"}
    if content_type: headers["Content-Type"] = content_type
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=25) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        if method == "PUT" and path == "/resources" and exc.code == 409: return {}
        raise RuntimeError(f"yandex_disk_http_{exc.code}") from None


def _mkdirs(remote_path):
    parts = [p for p in str(remote_path).split("/") if p]
    current = ""
    for part in parts:
        current += "/" + part
        _disk_request("PUT", "/resources", {"path": current})


def _upload(remote_path, data):
    parent = remote_path.rsplit("/", 1)[0]
    _mkdirs(parent)
    link = _disk_request("GET", "/resources/upload", {"path": remote_path, "overwrite": "true"})
    href = link.get("href")
    if not href: raise RuntimeError("yandex_upload_link_missing")
    req = Request(href, data=data, headers={"Content-Type": "application/octet-stream"}, method="PUT")
    try:
        with urlopen(req, timeout=60) as resp:
            if int(getattr(resp, "status", 200)) not in {200, 201, 202, 204}:
                raise RuntimeError("yandex_upload_failed")
    except HTTPError as exc:
        raise RuntimeError(f"yandex_upload_http_{exc.code}") from None


def _remote_path(item):
    try: dt = datetime.fromisoformat(str(item.get("created_at") or ""))
    except Exception: dt = datetime.now()
    student = _safe_name(item.get("name"), f"student_{item['user_id']}")
    name = f"payment_{int(item['payment_id'])}_receipt_{int(item['id'])}.{_ext(item.get('file_type'))}"
    return f"{ARCHIVE_ROOT}/{dt:%Y}/{dt:%m}/{student}_{int(item['user_id'])}/{name}"


def _retry_seconds(attempts):
    # 1m, 2m, 4m ... capped at 6h. Permanent/unsupported rows stop at MAX_ATTEMPTS.
    return min(6 * 60 * 60, 60 * (2 ** max(0, min(int(attempts), 8))))


def archive_receipt(receipt_id):
    ensure_table(); rid = int(receipt_id)
    conn = connect()
    existing = conn.execute("SELECT * FROM receipt_cloud_archives WHERE receipt_id=?", (rid,)).fetchone()
    if existing and str(existing["status"]).upper() == "ARCHIVED":
        result = dict(existing); conn.close(); return {"status": "ok", "archive": result, "already_archived": True}
    if existing and int(existing["attempts"] or 0) >= MAX_ATTEMPTS:
        result = dict(existing); conn.close(); return {"status": "failed", "archive": result, "max_attempts": True}
    conn.execute(
        """INSERT INTO receipt_cloud_archives(receipt_id,status,attempts,updated_at)
           VALUES(?, 'PENDING', 0, ?)
           ON CONFLICT(receipt_id) DO UPDATE SET updated_at=excluded.updated_at""",
        (rid, now_iso()),
    ); conn.commit(); conn.close()
    item = _receipt(rid)
    if not item: raise ValueError("receipt_not_found")
    try:
        source = str(item.get("source_platform") or "").upper()
        if source not in {"TELEGRAM", "TG"} or not item.get("telegram_file_id"):
            raise RuntimeError("receipt_source_not_supported")
        data = _telegram_bytes(item["telegram_file_id"])
        digest = hashlib.sha256(data).hexdigest(); remote = _remote_path(item)
        _upload(remote, data)
        conn = connect(); conn.execute(
            """UPDATE receipt_cloud_archives SET provider='YANDEX_DISK',remote_path=?,sha256=?,
               size_bytes=?,status='ARCHIVED',attempts=attempts+1,last_error=NULL,
               archived_at=?,updated_at=? WHERE receipt_id=?""",
            (remote, digest, len(data), now_iso(), now_iso(), rid),
        ); conn.commit(); row=conn.execute("SELECT * FROM receipt_cloud_archives WHERE receipt_id=?",(rid,)).fetchone();conn.close()
        return {"status":"ok","archive":dict(row)}
    except Exception as exc:
        error = str(exc)[:160]
        conn = connect(); conn.execute(
            """UPDATE receipt_cloud_archives SET
               status=CASE WHEN attempts+1>=? THEN 'FAILED' ELSE 'RETRY' END,
               attempts=attempts+1,last_error=?,updated_at=? WHERE receipt_id=?""",
            (MAX_ATTEMPTS, error, now_iso(), rid),
        ); conn.commit(); conn.close(); return {"status":"retry","error":error,"receipt_id":rid}


def archive_pending(limit=20):
    """Process a due batch without retry-hammering cloud APIs."""
    ensure_table(); limit=max(1,min(int(limit),100)); conn=connect()
    rows=conn.execute(
        """
        SELECT r.id,a.attempts,a.updated_at,a.status
        FROM receipts r
        LEFT JOIN receipt_cloud_archives a ON a.receipt_id=r.id
        WHERE a.receipt_id IS NULL OR a.status IN ('PENDING','RETRY')
        ORDER BY r.id LIMIT ?
        """,
        (max(limit * 5, limit),),
    ).fetchall();conn.close()
    now=datetime.now();due=[]
    for r in rows:
        if len(due)>=limit:break
        if r['status'] is None or str(r['status']).upper()=='PENDING':
            due.append(int(r['id']));continue
        try:updated=datetime.fromisoformat(str(r['updated_at']))
        except Exception:updated=now-timedelta(days=1)
        if now-updated>=timedelta(seconds=_retry_seconds(r['attempts'] or 0)):
            due.append(int(r['id']))
    return [archive_receipt(rid) for rid in due]


def queue_stats():
    """Cheap operational counters for monitoring and pre-production checks."""
    ensure_table();conn=connect()
    rows=conn.execute("SELECT status,COUNT(*) c FROM receipt_cloud_archives GROUP BY status").fetchall()
    total=conn.execute("SELECT COUNT(*) c FROM receipts").fetchone();conn.close()
    counts={str(r['status']).upper():int(r['c'] or 0) for r in rows}
    tracked=sum(counts.values())
    return {
        'receipts_total':int(total['c'] or 0),'untracked':max(0,int(total['c'] or 0)-tracked),
        'pending':counts.get('PENDING',0),'retry':counts.get('RETRY',0),
        'archived':counts.get('ARCHIVED',0),'failed':counts.get('FAILED',0),
    }
