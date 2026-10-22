from __future__ import annotations

from datetime import datetime, timedelta
import database
from core import schedule_sync

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
      note TEXT,
      exchange_mode TEXT,
      occupant_proposed_start TEXT,
      occupant_proposed_end TEXT,
      apply_requester_before_start TEXT,
      apply_requester_before_end TEXT,
      apply_occupant_before_start TEXT,
      apply_occupant_before_end TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_slot_change_status
      ON slot_change_requests(status, created_at);
    CREATE INDEX IF NOT EXISTS idx_slot_change_student
      ON slot_change_requests(requester_student_id, status);
    """)
    cols={r['name'] for r in c.execute('PRAGMA table_info(slot_change_requests)').fetchall()}
    if 'exchange_mode' not in cols:c.execute('ALTER TABLE slot_change_requests ADD COLUMN exchange_mode TEXT')
    if 'occupant_proposed_start' not in cols:c.execute('ALTER TABLE slot_change_requests ADD COLUMN occupant_proposed_start TEXT')
    if 'occupant_proposed_end' not in cols:c.execute('ALTER TABLE slot_change_requests ADD COLUMN occupant_proposed_end TEXT')
    if 'apply_requester_before_start' not in cols:c.execute('ALTER TABLE slot_change_requests ADD COLUMN apply_requester_before_start TEXT')
    if 'apply_requester_before_end' not in cols:c.execute('ALTER TABLE slot_change_requests ADD COLUMN apply_requester_before_end TEXT')
    if 'apply_occupant_before_start' not in cols:c.execute('ALTER TABLE slot_change_requests ADD COLUMN apply_occupant_before_start TEXT')
    if 'apply_occupant_before_end' not in cols:c.execute('ALTER TABLE slot_change_requests ADD COLUMN apply_occupant_before_end TEXT')
    c.commit(); c.close()


def _iso(dt):
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _sync_moved(ids):
    try:
        return schedule_sync.sync_lessons_blocking(ids)
    except Exception as exc:
        return {'synced_lesson_ids': [], 'failed': [{'reason': 'schedule_sync_error', 'detail': type(exc).__name__}]}


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


def find_occupant(start_dt: datetime, end_dt: datetime, exclude_lesson_id=None, exclude_lesson_ids=None):
    """Find an actual overlap; touching endpoints are available."""
    from core.lesson_time import lesson_timezone
    tz = lesson_timezone()

    def parsed(raw):
        value = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        return value.replace(tzinfo=tz) if value.tzinfo is None else value.astimezone(tz)

    start, end = parsed(start_dt), parsed(end_dt)
    if end <= start:
        raise ValueError('invalid_interval')
    excluded = {int(x) for x in (exclude_lesson_ids or []) if x is not None}
    if exclude_lesson_id is not None:
        excluded.add(int(exclude_lesson_id))
    c = database.connect()
    try:
        marks = ",".join("?" for _ in ACTIVE_STATUSES)
        rows = c.execute(f"SELECT * FROM lessons WHERE lesson_status IN ({marks})", ACTIVE_STATUSES).fetchall()
    finally:
        c.close()
    hits = [r for r in rows if int(r['id']) not in excluded
            and start < parsed(r['end_time']) and parsed(r['start_time']) < end]
    return min(hits, key=lambda r: (parsed(r['start_time']), int(r['id']))) if hits else None

def _cascade_target(occupant, desired_end, requester_lesson_id):
    if not occupant:return None
    occ_start=datetime.fromisoformat(occupant['start_time']);occ_end=datetime.fromisoformat(occupant['end_time'])
    duration=occ_end-occ_start
    candidate=desired_end.replace(second=0,microsecond=0)
    for _ in range(9):
        end=candidate+duration
        if candidate.date()!=desired_end.date() or end.date()!=desired_end.date():break
        if is_inside_working_hours(candidate,end) and not find_occupant(candidate,end,exclude_lesson_ids=[requester_lesson_id,occupant['id']]):
            return candidate,end
        candidate += timedelta(minutes=30)
    return None


def create_request(student_id, lesson_id, desired_start, desired_end, requested_by, note=None):
    ensure_schema()
    start_dt = desired_start if isinstance(desired_start, datetime) else datetime.fromisoformat(desired_start)
    end_dt = desired_end if isinstance(desired_end, datetime) else datetime.fromisoformat(desired_end)
    occupant = find_occupant(start_dt, end_dt, lesson_id)
    outside = 0 if is_inside_working_hours(start_dt, end_dt) else 1
    mode=None;occ_proposed_start=None;occ_proposed_end=None
    if occupant:
        target=_cascade_target(occupant,end_dt,int(lesson_id))
        if target:
            mode='SHIFT'
            occ_proposed_start,occ_proposed_end=target
        else:
            mode='SWAP'
    now = datetime.now().isoformat(timespec="seconds")
    c = database.connect()
    cur = c.execute("""
      INSERT INTO slot_change_requests(
        requester_student_id,requester_lesson_id,requested_by_telegram_id,
        desired_start,desired_end,outside_working_hours,
        occupant_lesson_id,occupant_student_id,status,created_at,updated_at,note,
        exchange_mode,occupant_proposed_start,occupant_proposed_end
      ) VALUES(?,?,?,?,?,?,?,?, 'PENDING_ADMIN',?,?,?,?,?,?)
    """, (
        int(student_id), int(lesson_id), int(requested_by) if requested_by else None,
        start_dt.isoformat(), end_dt.isoformat(), outside,
        int(occupant["id"]) if occupant else None,
        int(occupant["user_id"]) if occupant else None,
        now, now, note,mode,
        occ_proposed_start.isoformat() if occ_proposed_start else None,
        occ_proposed_end.isoformat() if occ_proposed_end else None,
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


def _same_times(lesson,start,end):
    return str(lesson['start_time'])==str(start) and str(lesson['end_time'])==str(end)


def _ensure_apply_snapshot(req,a,b):
    fields=(req['apply_requester_before_start'],req['apply_requester_before_end'],req['apply_occupant_before_start'],req['apply_occupant_before_end'])
    if all(fields):return req
    now=database.now_iso();c=database.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        cur=c.execute("""
          UPDATE slot_change_requests
          SET apply_requester_before_start=COALESCE(apply_requester_before_start,?),
              apply_requester_before_end=COALESCE(apply_requester_before_end,?),
              apply_occupant_before_start=COALESCE(apply_occupant_before_start,?),
              apply_occupant_before_end=COALESCE(apply_occupant_before_end,?),
              updated_at=?
          WHERE id=?
        """,(a['start_time'],a['end_time'],b['start_time'],b['end_time'],now,int(req['id'])))
        if cur.rowcount!=1:raise ValueError('reschedule_request_not_found')
        c.commit()
    except Exception:c.rollback();raise
    finally:c.close()
    return get_request(int(req['id']))


def _apply_shift(req,a,b):
    new_a_start=datetime.fromisoformat(req['desired_start']);new_a_end=datetime.fromisoformat(req['desired_end'])
    new_b_start=datetime.fromisoformat(req['occupant_proposed_start']);new_b_end=datetime.fromisoformat(req['occupant_proposed_end'])
    if find_occupant(new_a_start,new_a_end,exclude_lesson_ids=[a['id'],b['id']]):raise ValueError('Желаемое время уже занято.')
    if find_occupant(new_b_start,new_b_end,exclude_lesson_ids=[a['id'],b['id']]):raise ValueError('Предложенное время второго ученика уже занято.')
    if not is_inside_working_hours(new_a_start,new_a_end) or not is_inside_working_hours(new_b_start,new_b_end):raise ValueError('Одно из новых времён вышло за рабочие часы.')
    c=database.connect()
    try:
        c.execute('BEGIN IMMEDIATE');now=datetime.now().isoformat(timespec='seconds')
        c.execute('UPDATE lessons SET start_time=?,end_time=?,updated_at=? WHERE id=?',(new_a_start.isoformat(),new_a_end.isoformat(),now,a['id']))
        c.execute('UPDATE lessons SET start_time=?,end_time=?,updated_at=? WHERE id=?',(new_b_start.isoformat(),new_b_end.isoformat(),now,b['id']))
        c.commit()
    except Exception:c.rollback();raise
    finally:c.close()
    return database.get_lesson(a['id']),database.get_lesson(b['id'])


def swap_times(req_id):
    """Apply approved exchange once and reconcile Calendar/Telemost after commit.

    A durable before-state snapshot makes stale APPLYING recovery idempotent: if
    lesson times already equal the intended target, a retry only re-syncs them
    instead of swapping them back.
    """
    req=get_request(req_id)
    if not req or not req["occupant_lesson_id"]:
        raise ValueError("Для этого запроса нет второго занятия.")
    a=database.get_lesson(req["requester_lesson_id"]); b=database.get_lesson(req["occupant_lesson_id"])
    if not a or not b: raise ValueError("Одно из занятий не найдено.")
    if a["lesson_status"] != "CONFIRMED" or b["lesson_status"] != "CONFIRMED":
        raise ValueError("Обмен возможен только для подтверждённых занятий.")
    req=_ensure_apply_snapshot(req,a,b)
    before_a_start=req['apply_requester_before_start'];before_a_end=req['apply_requester_before_end']
    before_b_start=req['apply_occupant_before_start'];before_b_end=req['apply_occupant_before_end']
    mode=str(req['exchange_mode'] or '').upper()
    if mode=='SHIFT' and req['occupant_proposed_start'] and req['occupant_proposed_end']:
        target_a_start=req['desired_start'];target_a_end=req['desired_end']
        target_b_start=req['occupant_proposed_start'];target_b_end=req['occupant_proposed_end']
    else:
        target_a_start=before_b_start;target_a_end=before_b_end
        target_b_start=before_a_start;target_b_end=before_a_end
    a=database.get_lesson(req["requester_lesson_id"]);b=database.get_lesson(req["occupant_lesson_id"])
    already_applied=_same_times(a,target_a_start,target_a_end) and _same_times(b,target_b_start,target_b_end)
    still_original=_same_times(a,before_a_start,before_a_end) and _same_times(b,before_b_start,before_b_end)
    if already_applied:
        result=(a,b)
    elif not still_original:
        raise ValueError('reschedule_apply_state_changed')
    elif mode=='SHIFT' and req['occupant_proposed_start'] and req['occupant_proposed_end']:
        result=_apply_shift(req,a,b)
    else:
        c=database.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            now=datetime.now().isoformat(timespec='seconds')
            c.execute("UPDATE lessons SET start_time=?,end_time=?,updated_at=? WHERE id=?",(target_a_start,target_a_end,now,a["id"]))
            c.execute("UPDATE lessons SET start_time=?,end_time=?,updated_at=? WHERE id=?",(target_b_start,target_b_end,now,b["id"]))
            c.commit()
        except Exception:
            c.rollback(); raise
        finally:c.close()
        result=(database.get_lesson(a["id"]), database.get_lesson(b["id"]))
    _sync_moved([a['id'],b['id']])
    return result


def move_to_requested(req_id):
    """Move one lesson and reconcile external links after the local commit."""
    req=get_request(req_id)
    if not req: raise ValueError("Запрос не найден.")
    old_lesson_id=int(req["requester_lesson_id"])
    new_lesson_id=int(database.free_reschedule_lesson(old_lesson_id,req["desired_start"],req["desired_end"]))
    try:
        from web_backend import teacher_day_off_state
        teacher_day_off_state.inherit_marker(old_lesson_id,new_lesson_id)
    except Exception:
        pass
    _sync_moved([old_lesson_id,new_lesson_id])
    return database.get_lesson(new_lesson_id)
