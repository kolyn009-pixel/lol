"""Yandex Telemost integration for TutorBot lessons.

Uses the official Telemost REST API. Conference creation is deliberately
idempotent at the TutorBot layer: once a lesson has a saved conference id and
join URL, retries reuse it instead of creating a new meeting.

No token is ever written to the database or logs.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import database
from integrations.google_calendar import ensure_schema

API_BASE = "https://cloud-api.yandex.net/v1/telemost-api"
TOKEN_ENV = "YANDEX_TELEMOST_OAUTH_TOKEN"
WAITING_ENV = "YANDEX_TELEMOST_WAITING_ROOM_LEVEL"
VALID_WAITING_LEVELS = {"PUBLIC", "ORGANIZATION", "ADMINS"}
TIMEOUT_SECONDS = 15


def _token():
    value = os.getenv(TOKEN_ENV, "").strip()
    if not value:
        raise RuntimeError("telemost_oauth_token_missing")
    return value


def _waiting_room_level():
    value = os.getenv(WAITING_ENV, "PUBLIC").strip().upper() or "PUBLIC"
    if value not in VALID_WAITING_LEVELS:
        raise RuntimeError("telemost_invalid_waiting_room_level")
    return value


def _join_url(value):
    value = str(value or "").strip()
    try:
        parsed = urlparse(value)
    except Exception:
        raise RuntimeError("telemost_invalid_join_url") from None
    if parsed.scheme != "https" or parsed.hostname != "telemost.yandex.ru":
        raise RuntimeError("telemost_invalid_join_url")
    return value


def connection_status():
    enabled = os.getenv("YANDEX_TELEMOST_ENABLED", "0") == "1"
    configured = bool(os.getenv(TOKEN_ENV, "").strip())
    try:
        waiting = _waiting_room_level()
        config_error = None
    except Exception as exc:
        waiting = None
        config_error = str(exc)
    return {
        "enabled": enabled,
        "configured": configured,
        "waiting_room_level": waiting,
        "auto_summarization": False,
        "config_error": config_error,
    }


def _request(method, path, body=None):
    payload = None
    headers = {
        "Authorization": f"OAuth {_token()}",
        "Accept": "application/json",
    }
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(API_BASE + path, data=payload, headers=headers, method=method)
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
            data = json.loads(raw.decode("utf-8")) if raw else {}
            return int(response.status), data
    except HTTPError as exc:
        raise RuntimeError(f"telemost_http_{int(exc.code)}") from exc
    except URLError as exc:
        raise RuntimeError("telemost_network_error") from exc
    except TimeoutError as exc:
        raise RuntimeError("telemost_timeout") from exc


def _delete_conference(conference_id):
    conference_id = str(conference_id or "").strip()
    if not conference_id:
        raise ValueError("conference_id_required")
    headers = {
        "Authorization": f"OAuth {_token()}",
        "Accept": "application/json",
    }
    req = Request(API_BASE + f"/conferences/{conference_id}", headers=headers, method="DELETE")
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            response.read()
            return int(response.status)
    except HTTPError as exc:
        if int(exc.code) == 404:
            return 404
        raise RuntimeError(f"telemost_http_{int(exc.code)}") from exc
    except URLError as exc:
        raise RuntimeError("telemost_network_error") from exc
    except TimeoutError as exc:
        raise RuntimeError("telemost_timeout") from exc


def _integration(lesson_id):
    ensure_schema()
    conn = database.connect()
    row = conn.execute(
        "SELECT * FROM lesson_external_integrations WHERE lesson_id=?",
        (int(lesson_id),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _lesson_exists(lesson_id):
    conn = database.connect()
    row = conn.execute("SELECT id FROM lessons WHERE id=?", (int(lesson_id),)).fetchone()
    conn.close()
    if not row:
        raise ValueError("lesson_not_found")


def _repair_lesson_meeting_url(lesson_id, join_url):
    """Keep the canonical lesson row aligned with a reused Telemost record."""
    conn = database.connect()
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(lessons)").fetchall()}
        if "meeting_url" not in columns:
            return
        row = conn.execute("SELECT meeting_url FROM lessons WHERE id=?", (int(lesson_id),)).fetchone()
        if row and str(row["meeting_url"] or "").strip() != str(join_url):
            conn.execute("UPDATE lessons SET meeting_url=? WHERE id=?", (str(join_url), int(lesson_id)))
            conn.commit()
    finally:
        conn.close()


def _save(lesson_id, conference_id, join_url):
    now = database.now_iso()
    ensure_schema()
    conn = database.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT telemost_conference_id,telemost_join_url FROM lesson_external_integrations WHERE lesson_id=?",
            (int(lesson_id),),
        ).fetchone()
        if current and current["telemost_conference_id"] and current["telemost_join_url"]:
            conn.rollback()
            saved = {
                "conference_id": current["telemost_conference_id"],
                "join_url": current["telemost_join_url"],
                "reused": True,
            }
            _repair_lesson_meeting_url(lesson_id, saved["join_url"])
            return saved
        conn.execute(
            """INSERT INTO lesson_external_integrations(
                 lesson_id,telemost_conference_id,telemost_join_url,
                 telemost_synced_at,last_error,updated_at
               ) VALUES(?,?,?,?,NULL,?)
               ON CONFLICT(lesson_id) DO UPDATE SET
                 telemost_conference_id=excluded.telemost_conference_id,
                 telemost_join_url=excluded.telemost_join_url,
                 telemost_synced_at=excluded.telemost_synced_at,
                 last_error=NULL,
                 updated_at=excluded.updated_at""",
            (int(lesson_id), str(conference_id), str(join_url), now, now),
        )
        columns = {r[1] for r in conn.execute("PRAGMA table_info(lessons)").fetchall()}
        if "meeting_url" in columns:
            conn.execute("UPDATE lessons SET meeting_url=? WHERE id=?", (str(join_url), int(lesson_id)))
        conn.commit()
        return {"conference_id": str(conference_id), "join_url": str(join_url), "reused": False}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _save_error(lesson_id, code):
    ensure_schema()
    conn = database.connect()
    try:
        now = database.now_iso()
        conn.execute(
            """INSERT INTO lesson_external_integrations(lesson_id,last_error,updated_at)
               VALUES(?,?,?) ON CONFLICT(lesson_id) DO UPDATE SET
               last_error=excluded.last_error,updated_at=excluded.updated_at""",
            (int(lesson_id), str(code)[:120], now),
        )
        conn.commit()
    finally:
        conn.close()


def _clear_closed(lesson_id):
    ensure_schema()
    conn = database.connect()
    try:
        now = database.now_iso()
        conn.execute(
            """UPDATE lesson_external_integrations
               SET telemost_conference_id=NULL,telemost_join_url=NULL,
                   telemost_synced_at=?,last_error=NULL,updated_at=?
               WHERE lesson_id=?""",
            (now, now, int(lesson_id)),
        )
        columns = {r[1] for r in conn.execute("PRAGMA table_info(lessons)").fetchall()}
        if "meeting_url" in columns:
            conn.execute("UPDATE lessons SET meeting_url=NULL WHERE id=?", (int(lesson_id),))
        conn.commit()
    finally:
        conn.close()


def ensure_lesson_conference(lesson_id):
    """Return a saved Telemost meeting or create exactly one for the lesson."""
    lesson_id = int(lesson_id)
    _lesson_exists(lesson_id)
    existing = _integration(lesson_id) or {}
    if existing.get("telemost_conference_id") and existing.get("telemost_join_url"):
        join_url = _join_url(existing["telemost_join_url"])
        _repair_lesson_meeting_url(lesson_id, join_url)
        return {
            "status": "ok",
            "conference_id": existing["telemost_conference_id"],
            "join_url": join_url,
            "reused": True,
        }
    try:
        status, data = _request(
            "POST",
            "/conferences",
            {
                "waiting_room_level": _waiting_room_level(),
                "is_auto_summarization_enabled": False,
            },
        )
        if status != 201:
            raise RuntimeError(f"telemost_unexpected_status_{status}")
        conference_id = str(data.get("id") or "").strip()
        join_url = _join_url(data.get("join_url"))
        if not conference_id:
            raise RuntimeError("telemost_missing_conference_id")
        saved = _save(lesson_id, conference_id, join_url)
        return {"status": "ok", **saved}
    except Exception as exc:
        _save_error(lesson_id, str(exc))
        raise


def close_lesson_conference(lesson_id):
    """Close the lesson's Telemost conference and clear its active join URL.

    DELETE is idempotent: a provider-side 404 is treated as already closed.
    """
    lesson_id = int(lesson_id)
    existing = _integration(lesson_id) or {}
    conference_id = str(existing.get("telemost_conference_id") or "").strip()
    if not conference_id:
        _clear_closed(lesson_id)
        return {"status": "no_conference", "conference_id": None}
    try:
        status = _delete_conference(conference_id)
        if status not in {200, 202, 204, 404}:
            raise RuntimeError(f"telemost_unexpected_status_{status}")
        _clear_closed(lesson_id)
        return {
            "status": "already_closed" if status == 404 else "closed",
            "conference_id": conference_id,
        }
    except Exception as exc:
        _save_error(lesson_id, f"close:{exc}")
        raise


def read_conference(conference_id):
    """Read-only health check for an already-created conference."""
    conference_id = str(conference_id or "").strip()
    if not conference_id:
        raise ValueError("conference_id_required")
    status, data = _request("GET", f"/conferences/{conference_id}")
    if status != 200:
        raise RuntimeError(f"telemost_unexpected_status_{status}")
    return {
        "status": "ok",
        "conference_id": str(data.get("id") or conference_id),
        "join_url": _join_url(data.get("join_url")),
        "waiting_room_level": data.get("waiting_room_level"),
    }
