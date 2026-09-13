"""Resilient Google Calendar integration for TutorBot.

Designed for a long-running server process:
- reuses a persisted refresh token;
- refreshes access tokens automatically;
- atomically rewrites token.json after refresh;
- never launches an interactive OAuth flow from the production worker;
- keeps external event ids in a dedicated integration table;
- recreates events safely when a remote event was deleted manually.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import database

SCOPES = ["https://www.googleapis.com/auth/calendar"]
BASE_DIR = Path(__file__).resolve().parents[1]
TOKEN_PATH = Path(os.getenv("GOOGLE_CALENDAR_TOKEN_FILE", str(BASE_DIR / "token.json")))
CREDENTIALS_PATH = Path(os.getenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", str(BASE_DIR / "credentials.json")))
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")


def ensure_schema():
    conn = database.connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS lesson_external_integrations (
            lesson_id INTEGER PRIMARY KEY,
            google_event_id TEXT,
            telemost_conference_id TEXT,
            telemost_join_url TEXT,
            google_synced_at TEXT,
            telemost_synced_at TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_lesson_external_google_event
            ON lesson_external_integrations(google_event_id);
        """
    )
    conn.commit()
    conn.close()


def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _load_credentials():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise RuntimeError("google_calendar_dependencies_missing") from exc

    if not TOKEN_PATH.exists():
        raise RuntimeError("google_calendar_not_connected")

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise RuntimeError("google_calendar_refresh_failed") from exc
        _atomic_write(TOKEN_PATH, creds.to_json())
        return creds

    raise RuntimeError("google_calendar_reconnect_required")


def connection_status():
    try:
        creds = _load_credentials()
        return {
            "connected": True,
            "refresh_token": bool(getattr(creds, "refresh_token", None)),
            "token_file": str(TOKEN_PATH),
            "calendar_id": CALENDAR_ID,
        }
    except Exception as exc:
        return {
            "connected": False,
            "error": str(exc),
            "token_file": str(TOKEN_PATH),
            "calendar_id": CALENDAR_ID,
        }


def _service():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("google_calendar_dependencies_missing") from exc
    return build("calendar", "v3", credentials=_load_credentials(), cache_discovery=False)


def _lesson(lesson_id):
    conn = database.connect()
    row = conn.execute(
        """
        SELECT l.*, u.name AS student_name, u.board_url AS student_board_url
        FROM lessons l
        JOIN users u ON u.id=l.user_id
        WHERE l.id=?
        LIMIT 1
        """,
        (int(lesson_id),),
    ).fetchone()
    conn.close()
    if not row:
        raise ValueError("lesson_not_found")
    return dict(row)


def _integration(lesson_id):
    ensure_schema()
    conn = database.connect()
    row = conn.execute(
        "SELECT * FROM lesson_external_integrations WHERE lesson_id=?",
        (int(lesson_id),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _save(lesson_id, event_id=None, error=None):
    ensure_schema()
    conn = database.connect()
    conn.execute(
        """
        INSERT INTO lesson_external_integrations(
            lesson_id, google_event_id, google_synced_at, last_error, updated_at
        ) VALUES(?,?,?,?,?)
        ON CONFLICT(lesson_id) DO UPDATE SET
            google_event_id=COALESCE(excluded.google_event_id, lesson_external_integrations.google_event_id),
            google_synced_at=excluded.google_synced_at,
            last_error=excluded.last_error,
            updated_at=excluded.updated_at
        """,
        (int(lesson_id), event_id, database.now_iso(), error, database.now_iso()),
    )
    conn.commit()
    conn.close()


def _event_body(lesson):
    subject = str(lesson.get("subject") or "Занятие").capitalize()
    goal = str(lesson.get("study_goal") or "").strip()
    student = str(lesson.get("student_name") or "Ученик")
    title = f"{subject}{' · ' + goal if goal else ''} — {student}"
    description = ["Аделия | TutorBot", f"Ученик: {student}"]
    if lesson.get("meeting_url"):
        description.append(f"Telemost: {lesson['meeting_url']}")
    if lesson.get("student_board_url"):
        description.append(f"Доска: {lesson['student_board_url']}")
    timezone = str(database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara")
    return {
        "summary": title,
        "description": "\n".join(description),
        "start": {"dateTime": lesson["start_time"], "timeZone": timezone},
        "end": {"dateTime": lesson["end_time"], "timeZone": timezone},
        "extendedProperties": {
            "private": {
                "tutorbot_lesson_id": str(lesson["id"]),
            }
        },
    }


def _is_not_found(exc):
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status == 404 or "404" in str(exc)


def sync_lesson(lesson_id):
    """Create or update one Google Calendar event for an existing lesson."""
    lesson = _lesson(lesson_id)
    existing = _integration(lesson_id) or {}
    service = _service()
    body = _event_body(lesson)
    event_id = existing.get("google_event_id")
    try:
        if event_id:
            try:
                event = service.events().update(
                    calendarId=CALENDAR_ID,
                    eventId=event_id,
                    body=body,
                ).execute()
            except Exception as exc:
                if not _is_not_found(exc):
                    raise
                # Someone may delete an event in Google Calendar manually. The
                # local lesson is authoritative, so recreate exactly one event.
                event = service.events().insert(
                    calendarId=CALENDAR_ID,
                    body=body,
                ).execute()
        else:
            event = service.events().insert(
                calendarId=CALENDAR_ID,
                body=body,
            ).execute()
        event_id = event.get("id")
        if not event_id:
            raise RuntimeError("google_calendar_missing_event_id")
        _save(lesson_id, event_id=event_id, error=None)
        return {"status": "ok", "event_id": event_id, "html_link": event.get("htmlLink")}
    except Exception as exc:
        _save(lesson_id, event_id=event_id, error=f"google:{type(exc).__name__}")
        raise


def cancel_lesson(lesson_id):
    existing = _integration(lesson_id) or {}
    event_id = existing.get("google_event_id")
    if not event_id:
        return {"status": "noop"}
    service = _service()
    try:
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    except Exception as exc:
        # Deletion is idempotent at our layer; a missing remote event must not
        # make a local lesson impossible to cancel.
        if not _is_not_found(exc):
            _save(lesson_id, event_id=event_id, error=f"google:{type(exc).__name__}")
            raise
    _save(lesson_id, event_id=event_id, error=None)
    return {"status": "ok", "event_id": event_id}
