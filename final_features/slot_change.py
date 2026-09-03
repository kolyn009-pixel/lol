from __future__ import annotations

from datetime import datetime, timedelta
import database

ACTIVE_STATUSES = ("PENDING", "CONFIRMED", "IN_PROGRESS")


def ensure_schema():
    c = database.connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS slot_change_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      requester_student_id INTEGER NOT NULL,
      requester_lesson_id INTEGER NOT NULL,
      requested_by_telegram_id INTEGER,
      desired_start TEXT NOT NULL,
      desired_end TEXT NOT NULL,
      outside_working_hours INTEGER NOT NULL DEFAULT 0,
      occupant_lesson_id INTEGER,
      occupant_student_id INTEGER,
      status TEXT NOT NULL DEFAULT 'PENDING_ADMIN',
      occupant_response TEXT,
      admin_preapproved_by INTEGER,
      admin_final_by INTEGER,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      resolved_at TEXT,
      note TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_slot_change_status
      ON slot_change_requests(status, created_at);
    CREATE INDEX IF NOT EXISTS idx_slot_change_student
      ON slot_change_requests(requester_student_id, status);
    """)
    c.commit(); c.close()


def _iso(dt):
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def parse_user_datetime(text: str, tz=None):
    value = (text or "").strip()
    formats = (
        "%d.%m.%Y %H:%M", "%d.%m.%y %H:%M",
        "%Y-%m-%d %H:%M", "%d.%m %H:%M",
    )
    now = datetime.now(tz) if tz else datetime.now()
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%d.%m %H:%M":
                dt = dt.replace(year=now.year)
                if dt < now - timedelta(days=1):
                    dt = dt.replace(year=now.year + 1)
            if tz and dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            return dt
        except ValueError:
            pass
    raise ValueError("Укажите дату и время, например: 25.08.2026 18:30")


def lesson_owner(lesson_id: int):
    lesson = database.get_lesson(int(lesson_id))
    return int(lesson["user_id"]) if lesson else None


def is_inside_working_hours(start_dt: datetime, end_dt: datetime) -> bool:
    rows = database.get_effective_working_hours(start_dt)
    if not rows:
        return False
    for r in rows:
        try:
            sh, sm = map(int, str(r["start_time"]).split(":")[:2])
            eh, em = map(int, str(r["end_time"]).split(":")[:2])
            ws = start_dt.replace(hour=sh, minute=sm, second=0, microsecond=0)
            we = start_dt.replace(hour=eh, minute=em, second=0, microsecond=0)
            if start_dt >= ws and end_dt <= we:
                return True
        except Exception:
            continue
    return False


def find_occupant(start_dt: datetime, end_dt: datetime, exclude_lesson_id=None):
    c = database.connect()
    marks = ",".join("?" for _ in ACTIVE_STATUSES)
    params = [*ACTIVE_STATUSES, _iso(end_dt), _iso(start_dt)]
    sql = f"""
      SELECT * FROM lessons
      WHERE lesson_status IN ({marks})
        AND start_time < ?
        AND end_time > ?
    """
    if exclude_lesson_id is not None:
        sql += " AND id<>?"
        params.append(int(exclude_lesson_id))
    sql += " ORDER BY start_time LIMIT 1"
    row = c.execute(sql, params).fetchone()
    c.close()
    return row


def create_request(student_id, lesson_id, desired_start, desired_end, requested_by, note=None):
    ensure_schema()
    start_dt = desired_start if isinstance(desired_start, datetime) else datetime.fromisoformat(desired_start)
    end_dt = desired_end if isinstance(desired_end, datetime) else datetime.fromisoformat(desired_end)
    occupant = find_occupant(start_dt, end_dt, lesson_id)
    outside = 0 if is_inside_working_hours(start_dt, end_dt) else 1
    now = datetime.now().isoformat(timespec="seconds")
    c = database.connect()
    cur = c.execute("""
      INSERT INTO slot_change_requests(
        requester_student_id,requester_lesson_id,requested_by_telegram_id,
        desired_start,desired_end,outside_working_hours,
        occupant_lesson_id,occupant_student_id,status,created_at,updated_at,note
      ) VALUES(?,?,?,?,?,?,?,?, 'PENDING_ADMIN',?,?,?)
    """, (
        int(student_id), int(lesson_id), int(requested_by) if requested_by else None,
        start_dt.isoformat(), end_dt.isoformat(), outside,
        int(occupant["id"]) if occupant else None,
        int(occupant["user_id"]) if occupant else None,
        now, now, note,
    ))
    rid = cur.lastrowid
    c.commit(); c.close()
    return rid


def get_request(req_id):
    ensure_schema(); c=database.connect()
    row=c.execute("SELECT * FROM slot_change_requests WHERE id=?",(int(req_id),)).fetchone(); c.close(); return row


def requests_for_student(student_id, active_only=True):
    ensure_schema(); c=database.connect()
    sql="SELECT * FROM slot_change_requests WHERE requester_student_id=?"
    p=[int(student_id)]
    if active_only:
        sql += " AND status IN ('PENDING_ADMIN','WAITING_OCCUPANT','WAITING_FINAL_ADMIN')"
    rows=c.execute(sql+" ORDER BY id DESC",p).fetchall(); c.close(); return rows


def set_status(req_id, status, **fields):
    ensure_schema(); now=datetime.now().isoformat(timespec="seconds")
    allowed={"occupant_response","admin_preapproved_by","admin_final_by","resolved_at","note"}
    parts=["status=?","updated_at=?"]; vals=[status,now]
    for k,v in fields.items():
        if k in allowed:
            parts.append(f"{k}=?"); vals.append(v)
    if status in ("APPLIED","DECLINED","CANCELLED") and "resolved_at" not in fields:
        parts.append("resolved_at=?"); vals.append(now)
    vals.append(int(req_id))
    c=database.connect(); c.execute(f"UPDATE slot_change_requests SET {','.join(parts)} WHERE id=?",vals); c.commit(); c.close()


def swap_times(req_id):
    """Swap two confirmed lesson times transactionally. Returns both updated lessons."""
    req=get_request(req_id)
    if not req or not req["occupant_lesson_id"]:
        raise ValueError("Для этого запроса нет второго занятия.")
    a=database.get_lesson(req["requester_lesson_id"]); b=database.get_lesson(req["occupant_lesson_id"])
    if not a or not b: raise ValueError("Одно из занятий не найдено.")
    if a["lesson_status"] != "CONFIRMED" or b["lesson_status"] != "CONFIRMED":
        raise ValueError("Обмен возможен только для подтверждённых занятий.")
    c=database.connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute("UPDATE lessons SET start_time=?,end_time=?,updated_at=? WHERE id=?",(b["start_time"],b["end_time"],datetime.now().isoformat(timespec='seconds'),a["id"]))
        c.execute("UPDATE lessons SET start_time=?,end_time=?,updated_at=? WHERE id=?",(a["start_time"],a["end_time"],datetime.now().isoformat(timespec='seconds'),b["id"]))
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:c.close()
    return database.get_lesson(a["id"]), database.get_lesson(b["id"])


def move_to_requested(req_id):
    req=get_request(req_id)
    if not req: raise ValueError("Запрос не найден.")
    return database.free_reschedule_lesson(req["requester_lesson_id"],req["desired_start"],req["desired_end"])
