"""Per-participant attendance timeline for group lessons and open events.

One participant can have multiple presence intervals. Teacher actions and future
automatic join/leave signals use the same event log, so reports can calculate
first arrival, last departure and net active time without losing reconnects.
"""
from __future__ import annotations

from datetime import datetime

import database

OBJECT_GROUP = "GROUP_LESSON"
OBJECT_EVENT = "OPEN_EVENT"
VALID_OBJECTS = {OBJECT_GROUP, OBJECT_EVENT}
VALID_EVENTS = {"JOIN", "LEAVE"}
VALID_SOURCES = {"TEACHER", "APP", "WEB", "SYSTEM"}


def _now():
    return database.now_iso()


def ensure_schema():
    c = database.connect()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS participant_attendance_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_type TEXT NOT NULL,
            object_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            happened_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'TEACHER',
            actor_id INTEGER,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_attendance_object_user_time
            ON participant_attendance_events(object_type,object_id,user_id,happened_at,id);
        """
    )
    c.commit(); c.close()


def _validate_object(object_type, object_id, user_id):
    kind = str(object_type or "").upper()
    if kind not in VALID_OBJECTS:
        raise ValueError("invalid_attendance_object")
    oid = int(object_id); uid = int(user_id)
    c = database.connect()
    if kind == OBJECT_GROUP:
        row = c.execute(
            "SELECT 1 FROM group_lesson_participants WHERE lesson_id=? AND user_id=?",
            (oid, uid),
        ).fetchone()
    else:
        row = c.execute(
            "SELECT 1 FROM open_event_participants WHERE event_id=? AND user_id=?",
            (oid, uid),
        ).fetchone()
    c.close()
    if not row:
        raise PermissionError("attendance_participant_not_found")
    return kind, oid, uid


def _parse(value):
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        raise ValueError("invalid_attendance_time") from None


def _latest(kind, oid, uid):
    c = database.connect()
    row = c.execute(
        """SELECT * FROM participant_attendance_events
           WHERE object_type=? AND object_id=? AND user_id=?
           ORDER BY datetime(happened_at) DESC,id DESC LIMIT 1""",
        (kind, oid, uid),
    ).fetchone()
    c.close()
    return dict(row) if row else None


def record(object_type, object_id, user_id, event_type, *, happened_at=None,
           source="TEACHER", actor_id=None, note=None):
    ensure_schema()
    kind, oid, uid = _validate_object(object_type, object_id, user_id)
    event = str(event_type or "").upper()
    source = str(source or "TEACHER").upper()
    if event not in VALID_EVENTS:
        raise ValueError("invalid_attendance_event")
    if source not in VALID_SOURCES:
        raise ValueError("invalid_attendance_source")
    at = str(happened_at or _now())
    _parse(at)
    latest = _latest(kind, oid, uid)
    if latest and latest["event_type"] == event:
        return {"status": "already_marked", "event": latest}
    if latest and _parse(at) < _parse(latest["happened_at"]):
        raise ValueError("attendance_time_before_latest_event")
    c = database.connect()
    cur = c.execute(
        """INSERT INTO participant_attendance_events(
             object_type,object_id,user_id,event_type,happened_at,source,actor_id,note,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (kind, oid, uid, event, at, source,
         int(actor_id) if actor_id is not None else None,
         str(note or "").strip()[:500] or None, _now()),
    )
    if kind == OBJECT_GROUP:
        if event == "JOIN":
            c.execute(
                """UPDATE group_lesson_participants
                   SET attendance_status='PRESENT',joined_at=COALESCE(joined_at,?),left_at=NULL,updated_at=?
                   WHERE lesson_id=? AND user_id=?""",
                (at, _now(), oid, uid),
            )
        else:
            c.execute(
                """UPDATE group_lesson_participants
                   SET attendance_status='LEFT',left_at=?,updated_at=?
                   WHERE lesson_id=? AND user_id=?""",
                (at, _now(), oid, uid),
            )
    else:
        # These additive columns are a fast summary; the event log remains canonical.
        cols = {r[1] for r in c.execute("PRAGMA table_info(open_event_participants)").fetchall()}
        if "joined_at" not in cols:
            c.execute("ALTER TABLE open_event_participants ADD COLUMN joined_at TEXT")
        if "left_at" not in cols:
            c.execute("ALTER TABLE open_event_participants ADD COLUMN left_at TEXT")
        if "attendance_status" not in cols:
            c.execute("ALTER TABLE open_event_participants ADD COLUMN attendance_status TEXT NOT NULL DEFAULT 'EXPECTED'")
        if event == "JOIN":
            c.execute(
                """UPDATE open_event_participants
                   SET attendance_status='PRESENT',joined_at=COALESCE(joined_at,?),left_at=NULL,updated_at=?
                   WHERE event_id=? AND user_id=?""",
                (at, _now(), oid, uid),
            )
        else:
            c.execute(
                """UPDATE open_event_participants
                   SET attendance_status='LEFT',left_at=?,updated_at=?
                   WHERE event_id=? AND user_id=?""",
                (at, _now(), oid, uid),
            )
    c.commit(); event_id = int(cur.lastrowid); c.close()
    return {"status": "ok", "attendance_event_id": event_id, "event_type": event, "happened_at": at}


def timeline(object_type, object_id, user_id):
    ensure_schema()
    kind, oid, uid = _validate_object(object_type, object_id, user_id)
    c = database.connect()
    rows = c.execute(
        """SELECT * FROM participant_attendance_events
           WHERE object_type=? AND object_id=? AND user_id=?
           ORDER BY datetime(happened_at),id""",
        (kind, oid, uid),
    ).fetchall(); c.close()
    return [dict(r) for r in rows]


def summary(object_type, object_id, user_id, *, as_of=None):
    rows = timeline(object_type, object_id, user_id)
    now_dt = _parse(as_of or _now())
    first_join = None; last_leave = None; active_since = None; total_seconds = 0
    intervals = []
    for row in rows:
        at = _parse(row["happened_at"])
        if row["event_type"] == "JOIN":
            if first_join is None:
                first_join = row["happened_at"]
            if active_since is None:
                active_since = at
        elif active_since is not None:
            seconds = max(0, int((at - active_since).total_seconds()))
            total_seconds += seconds
            intervals.append({"joined_at": active_since.isoformat(timespec="seconds"), "left_at": at.isoformat(timespec="seconds"), "minutes": round(seconds / 60, 1)})
            active_since = None; last_leave = row["happened_at"]
    present = active_since is not None
    if present:
        seconds = max(0, int((now_dt - active_since).total_seconds()))
        total_seconds += seconds
        intervals.append({"joined_at": active_since.isoformat(timespec="seconds"), "left_at": None, "minutes": round(seconds / 60, 1)})
    return {
        "object_type": str(object_type).upper(),
        "object_id": int(object_id),
        "user_id": int(user_id),
        "present": present,
        "first_joined_at": first_join,
        "last_left_at": last_leave,
        "total_minutes": round(total_seconds / 60, 1),
        "rejoins": max(0, sum(1 for r in rows if r["event_type"] == "JOIN") - 1),
        "intervals": intervals,
    }


def roster(object_type, object_id):
    ensure_schema(); kind = str(object_type or "").upper(); oid = int(object_id)
    c = database.connect()
    if kind == OBJECT_GROUP:
        rows = c.execute(
            """SELECT p.user_id,u.name,p.attendance_status FROM group_lesson_participants p
               JOIN users u ON u.id=p.user_id WHERE p.lesson_id=? ORDER BY u.name COLLATE NOCASE""",
            (oid,),
        ).fetchall()
    elif kind == OBJECT_EVENT:
        rows = c.execute(
            """SELECT p.user_id,u.name,COALESCE(p.attendance_status,'EXPECTED') attendance_status
               FROM open_event_participants p JOIN users u ON u.id=p.user_id
               WHERE p.event_id=? ORDER BY u.name COLLATE NOCASE""",
            (oid,),
        ).fetchall()
    else:
        c.close(); raise ValueError("invalid_attendance_object")
    c.close()
    out=[]
    for row in rows:
        item=dict(row); item["attendance"] = summary(kind, oid, int(row["user_id"])); out.append(item)
    return out
