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

def _runtime_secret_path(env_name: str, filename: str) -> Path:
    explicit = str(os.getenv(env_name, "") or "").strip()
    if explicit:
        return Path(explicit)
    db_path = str(os.getenv("ADELIA_DB_PATH", "") or "").strip()
    if db_path:
        return Path(db_path).expanduser().resolve().parent / filename
    return BASE_DIR / filename

TOKEN_PATH = _runtime_secret_path("GOOGLE_CALENDAR_TOKEN_FILE", "token.json")
CREDENTIALS_PATH = _runtime_secret_path("GOOGLE_CALENDAR_CREDENTIALS_FILE", "credentials.json")
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

def calendar_service():
    """Public canonical Google Calendar service for legacy read-only callers."""
    return _service()


def _lesson(lesson_id):
    conn = database.connect()
    row = conn.execute(
        """
        SELECT l.*, u.name AS student_name, u.grade AS student_grade, u.board_url AS student_board_url
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
    from core.calendar_policy import lesson_color_id, lesson_summary_prefix

    subject = str(lesson.get("subject") or "Занятие").capitalize()
    goal = str(lesson.get("study_goal") or "").strip()
    student = str(lesson.get("student_name") or "Ученик")
    title = (
        lesson_summary_prefix(lesson)
        + f"{subject}{' · ' + goal if goal else ''} — {student}"
    )
    from core.lesson_reschedule_details import previous, grade_label, interval
    before = previous(lesson)
    grade = grade_label(lesson.get('student_grade'))
    title += f" · {grade}"
    description = ["Аделия | TutorBot", f"Ученик: {student}", f"Класс: {grade}"]
    color = lesson_color_id(lesson)
    if before:
        title = "🔁 ПЕРЕНЕСЕНО · " + title
        description += [f"Было: {interval(before)}", f"Стало: {interval(lesson)}", "Время московское (МСК)."]
        # Lifecycle and urgent payment warnings remain visible.
        from core.calendar_policy import lesson_state
        if lesson_state(lesson) not in {'ATTENTION', 'IN_PROGRESS', 'COMPLETED'}:
            color = "7"  # Peacock / turquoise.
    if lesson.get("meeting_url"):
        description.append(f"Telemost: {lesson['meeting_url']}")
    if lesson.get("student_board_url"):
        description.append(f"Доска: {lesson['student_board_url']}")
    from core.lesson_time import lesson_timezone
    timezone = str(lesson_timezone())
    return {
        "summary": title,
        "description": "\n".join(description),
        "start": {"dateTime": lesson["start_time"], "timeZone": timezone},
        "end": {"dateTime": lesson["end_time"], "timeZone": timezone},
        "colorId": color,
        "extendedProperties": {
            "private": {
                "tutorbot_lesson_id": str(lesson["id"]),
            }
        },
    }


def _is_not_found(exc):
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status in (404, 410)


def _remote_lesson_events(service, lesson_id):
    """Return live Google events for exactly one TutorBot lesson."""
    items = []
    page = None

    while True:
        response = service.events().list(
            calendarId=CALENDAR_ID,
            privateExtendedProperty=f"tutorbot_lesson_id={int(lesson_id)}",
            showDeleted=False,
            singleEvents=True,
            maxResults=250,
            pageToken=page,
        ).execute()

        items.extend(
            event
            for event in response.get("items", [])
            if event.get("status") != "cancelled"
            and event.get("id")
        )

        page = response.get("nextPageToken")
        if not page:
            break

    return items


def _event_start(event):
    start = event.get("start") or {}
    return str(start.get("dateTime") or start.get("date") or "")


def _choose_remote_event(events, lesson, preferred_ids=()):
    if not events:
        return None

    by_id = {
        str(event["id"]): event
        for event in events
        if event.get("id")
    }

    for event_id in preferred_ids:
        if event_id and str(event_id) in by_id:
            return by_id[str(event_id)]

    expected = str(lesson.get("start_time") or "")

    matching = [
        event
        for event in events
        if _event_start(event).startswith(expected)
    ]

    pool = matching or events

    return sorted(
        pool,
        key=lambda event: (
            str(event.get("created") or ""),
            str(event.get("id") or ""),
        ),
    )[0]


def _delete_remote_duplicates(service, events, keep_id):
    deleted = 0

    for event in events:
        event_id = str(event.get("id") or "")

        if not event_id or event_id == str(keep_id):
            continue

        try:
            service.events().delete(
                calendarId=CALENDAR_ID,
                eventId=event_id,
            ).execute()
            deleted += 1
        except Exception as exc:
            if not _is_not_found(exc):
                raise

    return deleted


def sync_lesson(lesson_id):
    """Create or update exactly one Google event for a lesson."""
    lesson = _lesson(lesson_id)
    from core.calendar_policy import should_keep_lesson_event
    if not should_keep_lesson_event(lesson):
        return cancel_lesson(lesson_id)
    existing = _integration(lesson_id) or {}

    service = _service()
    body = _event_body(lesson)

    canonical_id = existing.get("google_event_id")
    legacy_id = lesson.get("google_event_id")

    try:
        remote = _remote_lesson_events(
            service,
            lesson_id,
        )

        chosen = _choose_remote_event(
            remote,
            lesson,
            (
                canonical_id,
                legacy_id,
            ),
        )

        if chosen:
            event_id = chosen["id"]

            event = service.events().update(
                calendarId=CALENDAR_ID,
                eventId=event_id,
                body=body,
            ).execute()

            _delete_remote_duplicates(
                service,
                remote,
                event_id,
            )

        elif canonical_id or legacy_id:
            try:
                event = service.events().update(
                    calendarId=CALENDAR_ID,
                    eventId=canonical_id or legacy_id,
                    body=body,
                ).execute()

            except Exception as exc:
                if not _is_not_found(exc):
                    raise

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
            raise RuntimeError(
                "google_calendar_missing_event_id"
            )

        _save(
            lesson_id,
            event_id=event_id,
            error=None,
        )

        return {
            "status": "ok",
            "event_id": event_id,
            "html_link": event.get("htmlLink"),
        }

    except Exception as exc:
        _save(
            lesson_id,
            event_id=canonical_id,
            error=f"google:{type(exc).__name__}",
        )
        raise


def cancel_lesson(lesson_id):
    """Remove all events owned by this lesson, including legacy-only ids.

    Never delete an id reassigned to a replacement lesson. On provider failure,
    retain ownership ids so the next reconciliation can retry.
    """
    existing = _integration(lesson_id) or {}
    lesson = _lesson(lesson_id)
    service = _service()
    try:
        remote = _remote_lesson_events(service, lesson_id)
        ids = {str(x['id']) for x in remote}
        ids.update(str(x) for x in (existing.get('google_event_id'), lesson.get('google_event_id')) if x)
        deleted = 0
        for event_id in sorted(ids):
            try:
                event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
                owner = event.get('extendedProperties', {}).get('private', {}).get('tutorbot_lesson_id')
                if owner is not None and str(owner) != str(int(lesson_id)):
                    continue
                if event.get('status') != 'cancelled':
                    service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
                    deleted += 1
            except Exception as exc:
                if not _is_not_found(exc):
                    raise
        _save(lesson_id, error=None)
        return {'status': 'ok', 'deleted': deleted}
    except Exception as exc:
        _save(lesson_id, error=f'google:{type(exc).__name__}')
        raise
