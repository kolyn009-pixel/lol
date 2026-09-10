"""Runtime v2 for group lessons.

Adds:
- per-student subscription consumption for each group lesson;
- temporary membership pauses (sick leave / vacation) without leaving a group;
- homework fan-out visibility rules and a unified student homework inbox;
- teacher review queue for group homework.

This module is additive and leaves production individual-lesson behavior intact.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import database
from web_backend import group_lessons, group_finance

PAUSE_TYPES = {"SICK", "VACATION"}
ACTIVE_MEMBER_STATUSES = {"ACTIVE", "PAUSED"}


def _now():
    return database.now_iso()


def ensure_schema():
    group_lessons.ensure_schema()
    group_finance.ensure_schema()
    c = database.connect()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS group_member_pauses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            pause_type TEXT NOT NULL,
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            cancelled_at TEXT,
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_subscription_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(subscription_id,lesson_id,user_id,reason),
            FOREIGN KEY(subscription_id) REFERENCES group_subscriptions(id) ON DELETE CASCADE,
            FOREIGN KEY(lesson_id) REFERENCES group_lessons(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_homework_delivery (
            homework_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'ASSIGNED',
            assigned_at TEXT NOT NULL,
            reminded_at TEXT,
            hidden_reason TEXT,
            PRIMARY KEY(homework_id,user_id),
            FOREIGN KEY(homework_id) REFERENCES group_homework(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_group_pause_active
            ON group_member_pauses(group_id,user_id,starts_at,ends_at,cancelled_at);
        CREATE INDEX IF NOT EXISTS idx_group_usage_lesson
            ON group_subscription_usage(lesson_id,user_id,reason);
        CREATE INDEX IF NOT EXISTS idx_group_hw_delivery_user
            ON group_homework_delivery(user_id,state,assigned_at DESC);
        """
    )
    c.commit(); c.close()


def active_pause(group_id, user_id, at=None):
    ensure_schema()
    point = str(at or _now())
    c = database.connect()
    row = c.execute(
        """SELECT * FROM group_member_pauses
           WHERE group_id=? AND user_id=? AND cancelled_at IS NULL
             AND starts_at<=? AND ends_at>=?
           ORDER BY ends_at DESC LIMIT 1""",
        (int(group_id), int(user_id), point, point),
    ).fetchone()
    c.close()
    return dict(row) if row else None


def pause_membership(group_id, user_id, pause_type, starts_at, ends_at, reason=None):
    ensure_schema(); gid=int(group_id); uid=int(user_id)
    ptype=str(pause_type or "").upper()
    if ptype not in PAUSE_TYPES:
        raise ValueError("invalid_pause_type")
    start=datetime.fromisoformat(str(starts_at)); end=datetime.fromisoformat(str(ends_at))
    if end < start:
        raise ValueError("invalid_pause_range")
    c=database.connect()
    member=c.execute("SELECT * FROM group_members WHERE group_id=? AND user_id=? AND status IN ('ACTIVE','PAUSED')",(gid,uid)).fetchone()
    if not member:
        c.close(); raise PermissionError("not_group_member")
    overlap=c.execute(
        """SELECT id FROM group_member_pauses
           WHERE group_id=? AND user_id=? AND cancelled_at IS NULL
             AND NOT(ends_at<? OR starts_at>?) LIMIT 1""",
        (gid,uid,start.isoformat(),end.isoformat()),
    ).fetchone()
    if overlap:
        c.close(); raise ValueError("pause_overlap")
    cur=c.execute(
        """INSERT INTO group_member_pauses(group_id,user_id,pause_type,starts_at,ends_at,reason,created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (gid,uid,ptype,start.isoformat(),end.isoformat(),str(reason or "")[:1000] or None,_now()),
    )
    c.execute("UPDATE group_members SET status='PAUSED' WHERE group_id=? AND user_id=?",(gid,uid))
    # Future generated lessons during pause should not require attendance/access.
    c.execute(
        """UPDATE group_lesson_participants
           SET attendance_status='PAUSED',access_granted=0,updated_at=?
           WHERE user_id=? AND lesson_id IN (
             SELECT id FROM group_lessons WHERE group_id=? AND start_time>=? AND start_time<=?
           )""",
        (_now(),uid,gid,start.isoformat(),end.isoformat()),
    )
    pause_id=int(cur.lastrowid); c.commit(); c.close()
    return {"status":"ok","pause_id":pause_id,"group_id":gid,"user_id":uid,"pause_type":ptype,"starts_at":start.isoformat(),"ends_at":end.isoformat()}


def cancel_pause(pause_id):
    ensure_schema(); pid=int(pause_id); now=_now(); c=database.connect()
    row=c.execute("SELECT * FROM group_member_pauses WHERE id=?",(pid,)).fetchone()
    if not row:
        c.close(); raise ValueError("pause_not_found")
    c.execute("UPDATE group_member_pauses SET cancelled_at=? WHERE id=?",(now,pid))
    # Restore membership only if no other pause is active now.
    other=c.execute(
        """SELECT 1 FROM group_member_pauses WHERE group_id=? AND user_id=? AND id<>?
           AND cancelled_at IS NULL AND starts_at<=? AND ends_at>=? LIMIT 1""",
        (int(row["group_id"]),int(row["user_id"]),pid,now,now),
    ).fetchone()
    if not other:
        c.execute("UPDATE group_members SET status='ACTIVE' WHERE group_id=? AND user_id=? AND status='PAUSED'",(int(row["group_id"]),int(row["user_id"])))
    c.commit(); c.close(); return {"status":"ok","pause_id":pid}


def refresh_pause_states(at=None):
    ensure_schema(); point=str(at or _now()); c=database.connect()
    # Any currently paused member without an active pause returns to ACTIVE.
    rows=c.execute("SELECT group_id,user_id FROM group_members WHERE status='PAUSED'").fetchall(); changed=0
    for r in rows:
        active=c.execute(
            """SELECT 1 FROM group_member_pauses WHERE group_id=? AND user_id=? AND cancelled_at IS NULL
               AND starts_at<=? AND ends_at>=? LIMIT 1""",
            (int(r["group_id"]),int(r["user_id"]),point,point),
        ).fetchone()
        if not active:
            c.execute("UPDATE group_members SET status='ACTIVE' WHERE group_id=? AND user_id=?",(int(r["group_id"]),int(r["user_id"])))
            changed += 1
    c.commit(); c.close(); return {"status":"ok","reactivated":changed}


def reserve_subscription_for_student(lesson_id, user_id):
    """Consume one lesson from this student's subscription only.

    Safe for a lesson with many students: uniqueness includes user_id.
    """
    ensure_schema(); lid=int(lesson_id); uid=int(user_id); now=_now(); c=database.connect()
    lesson=c.execute("SELECT group_id FROM group_lessons WHERE id=?",(lid,)).fetchone()
    if not lesson:
        c.close(); raise ValueError("group_lesson_not_found")
    existing=c.execute(
        "SELECT * FROM group_subscription_usage WHERE lesson_id=? AND user_id=? AND reason='LESSON_RESERVE' LIMIT 1",
        (lid,uid),
    ).fetchone()
    if existing:
        c.close(); return {"status":"already_reserved","subscription_id":int(existing["subscription_id"])}
    # Direct paid lesson does not consume a subscription.
    direct=c.execute("SELECT id FROM group_payments WHERE group_lesson_id=? AND user_id=? AND status='PAID' LIMIT 1",(lid,uid)).fetchone()
    if direct:
        c.close(); return {"status":"direct_payment","payment_id":int(direct["id"])}
    # Respect membership pause.
    pause=c.execute(
        """SELECT 1 FROM group_member_pauses WHERE group_id=? AND user_id=? AND cancelled_at IS NULL
           AND starts_at<=? AND ends_at>=? LIMIT 1""",
        (int(lesson["group_id"]),uid,now,now),
    ).fetchone()
    if pause:
        c.close(); return {"status":"paused"}
    sub=c.execute(
        """SELECT * FROM group_subscriptions
           WHERE group_id=? AND user_id=? AND status='ACTIVE' AND lessons_remaining>0
             AND (expires_at IS NULL OR expires_at>?)
             AND (paused_until IS NULL OR paused_until<=? OR paused_from>?)
           ORDER BY id LIMIT 1""",
        (int(lesson["group_id"]),uid,now,now,now),
    ).fetchone()
    if not sub:
        c.close(); raise ValueError("group_subscription_unavailable")
    sid=int(sub["id"])
    cur=c.execute("UPDATE group_subscriptions SET lessons_remaining=lessons_remaining-1,updated_at=? WHERE id=? AND lessons_remaining>0",(now,sid))
    if cur.rowcount != 1:
        c.rollback(); c.close(); raise ValueError("group_subscription_race")
    c.execute(
        "INSERT INTO group_subscription_usage(subscription_id,lesson_id,user_id,delta,reason,created_at) VALUES(?,?,?,-1,'LESSON_RESERVE',?)",
        (sid,lid,uid,now),
    )
    remaining=int(sub["lessons_remaining"])-1
    if remaining<=0:
        c.execute("UPDATE group_subscriptions SET status='EXHAUSTED',updated_at=? WHERE id=?",(now,sid))
    c.commit(); c.close(); return {"status":"ok","subscription_id":sid,"lessons_remaining":max(0,remaining)}


def refund_subscription_for_student(lesson_id, user_id):
    ensure_schema(); lid=int(lesson_id); uid=int(user_id); now=_now(); c=database.connect()
    reserve=c.execute(
        """SELECT * FROM group_subscription_usage
           WHERE lesson_id=? AND user_id=? AND reason='LESSON_RESERVE'
           ORDER BY id DESC LIMIT 1""",
        (lid,uid),
    ).fetchone()
    if not reserve:
        c.close(); return {"status":"nothing_to_refund"}
    refunded=c.execute(
        """SELECT 1 FROM group_subscription_usage
           WHERE subscription_id=? AND lesson_id=? AND user_id=? AND reason='LESSON_REFUND' LIMIT 1""",
        (int(reserve["subscription_id"]),lid,uid),
    ).fetchone()
    if refunded:
        c.close(); return {"status":"already_refunded"}
    sid=int(reserve["subscription_id"])
    c.execute("UPDATE group_subscriptions SET lessons_remaining=lessons_remaining+1,status='ACTIVE',updated_at=? WHERE id=?",(now,sid))
    c.execute(
        "INSERT INTO group_subscription_usage(subscription_id,lesson_id,user_id,delta,reason,created_at) VALUES(?,?,?,1,'LESSON_REFUND',?)",
        (sid,lid,uid,now),
    )
    c.commit(); c.close(); return {"status":"ok","subscription_id":sid}


def materialize_group_homework(homework_id):
    """Create per-student delivery rows, excluding students paused at assignment time."""
    ensure_schema(); hid=int(homework_id); now=_now(); c=database.connect()
    hw=c.execute("SELECT * FROM group_homework WHERE id=?",(hid,)).fetchone()
    if not hw:
        c.close(); raise ValueError("group_homework_not_found")
    members=c.execute("SELECT user_id,status FROM group_members WHERE group_id=? AND status IN ('ACTIVE','PAUSED')",(int(hw["group_id"]),)).fetchall()
    assigned=0; skipped=0
    for m in members:
        uid=int(m["user_id"])
        pause=c.execute(
            """SELECT 1 FROM group_member_pauses WHERE group_id=? AND user_id=? AND cancelled_at IS NULL
               AND starts_at<=? AND ends_at>=? LIMIT 1""",
            (int(hw["group_id"]),uid,now,now),
        ).fetchone()
        if pause:
            c.execute(
                "INSERT OR REPLACE INTO group_homework_delivery(homework_id,user_id,state,assigned_at,hidden_reason) VALUES(?,?,'HIDDEN',?,'MEMBERSHIP_PAUSED')",
                (hid,uid,now),
            ); skipped += 1
        else:
            c.execute(
                "INSERT OR IGNORE INTO group_homework_delivery(homework_id,user_id,state,assigned_at) VALUES(?,?,'ASSIGNED',?)",
                (hid,uid,now),
            ); assigned += 1
    c.commit(); c.close(); return {"status":"ok","homework_id":hid,"assigned":assigned,"skipped_paused":skipped}


def unified_homework_for_student(user_id):
    """Return individual + group homework in a single feed with explicit source labels."""
    ensure_schema(); uid=int(user_id); c=database.connect(); out=[]
    # Existing canonical individual homework table, when present.
    individual_table=c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='homeworks'").fetchone()
    if individual_table:
        cols={r["name"] for r in c.execute("PRAGMA table_info(homeworks)").fetchall()}
        if {"id","user_id"}.issubset(cols):
            select_cols=["id"]
            for k in ("description","deadline","status","lesson_id","created_at"):
                select_cols.append(k if k in cols else f"NULL AS {k}")
            rows=c.execute(f"SELECT {','.join(select_cols)} FROM homeworks WHERE user_id=? ORDER BY id DESC",(uid,)).fetchall()
            for r in rows:
                out.append({"source":"INDIVIDUAL","source_label":"Индивидуальное занятие","homework_id":int(r["id"]),"title":r["description"] or "Домашнее задание","deadline":r["deadline"],"status":r["status"],"lesson_id":r["lesson_id"],"created_at":r["created_at"]})
    group_rows=c.execute(
        """SELECT h.*,g.name AS group_name,d.state AS delivery_state,s.status AS submission_status,s.reviewed_at
           FROM group_homework_delivery d
           JOIN group_homework h ON h.id=d.homework_id
           JOIN study_groups g ON g.id=h.group_id
           LEFT JOIN group_homework_submissions s ON s.homework_id=h.id AND s.user_id=d.user_id
           WHERE d.user_id=? AND d.state<>'HIDDEN'
           ORDER BY h.created_at DESC""",
        (uid,),
    ).fetchall()
    for r in group_rows:
        out.append({"source":"GROUP","source_label":f"Группа: {r['group_name']}","group_id":int(r["group_id"]),"group_name":r["group_name"],"homework_id":int(r["id"]),"title":r["title"],"description":r["description"],"deadline":r["due_at"],"status":r["submission_status"] or r["delivery_state"],"lesson_id":r["lesson_id"],"created_at":r["created_at"]})
    c.close()
    out.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return out


def teacher_group_homework_queue(group_id, homework_id=None, only_pending=True):
    """Queue used by the teacher's 'Review in order' action."""
    ensure_schema(); gid=int(group_id); c=database.connect(); params=[gid]
    where="h.group_id=? AND d.state<>'HIDDEN'"
    if homework_id is not None:
        where += " AND h.id=?"; params.append(int(homework_id))
    if only_pending:
        where += " AND s.id IS NOT NULL AND COALESCE(s.status,'')<>'REVIEWED'"
    rows=c.execute(
        f"""SELECT h.id AS homework_id,h.title,h.due_at,u.id AS user_id,u.name AS student_name,
                    s.id AS submission_id,s.status,s.text_answer,s.file_ref,s.submitted_at,s.teacher_comment,s.score
             FROM group_homework h
             JOIN group_homework_delivery d ON d.homework_id=h.id
             JOIN users u ON u.id=d.user_id
             LEFT JOIN group_homework_submissions s ON s.homework_id=h.id AND s.user_id=d.user_id
             WHERE {where}
             ORDER BY h.created_at,u.name COLLATE NOCASE""",
        tuple(params),
    ).fetchall(); c.close()
    return [dict(r) for r in rows]


def reminder_targets_for_homework(homework_id):
    """Students who still have not submitted and are not paused/hidden."""
    ensure_schema(); hid=int(homework_id); c=database.connect()
    rows=c.execute(
        """SELECT d.user_id,u.name,d.reminded_at
           FROM group_homework_delivery d JOIN users u ON u.id=d.user_id
           LEFT JOIN group_homework_submissions s ON s.homework_id=d.homework_id AND s.user_id=d.user_id
           WHERE d.homework_id=? AND d.state='ASSIGNED' AND s.id IS NULL
           ORDER BY u.name COLLATE NOCASE""",
        (hid,),
    ).fetchall(); c.close(); return [dict(r) for r in rows]


def mark_homework_reminded(homework_id,user_id):
    ensure_schema(); c=database.connect(); cur=c.execute(
        "UPDATE group_homework_delivery SET reminded_at=? WHERE homework_id=? AND user_id=? AND state='ASSIGNED'",
        (_now(),int(homework_id),int(user_id)),
    ); c.commit(); c.close()
    if not cur.rowcount: raise ValueError("homework_delivery_not_found")
    return {"status":"ok","homework_id":int(homework_id),"user_id":int(user_id)}
