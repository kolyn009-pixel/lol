"""Group Lessons v1 domain model.

A group is a persistent learning space with its own price, recruitment state,
shared board/meeting context and regular schedule. Students may join permanently
or attend one-off lessons. Additional regular times are proposed to the whole
group; accepted times become group slots while dissenting students are opted out
of that slot only.

Homework is assigned once to the group but submissions remain private per
student. Access to a concrete lesson is granted only when payment/coverage has
been confirmed for that participant.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import math

import database

VALID_RECRUITMENT = {"OPEN", "CLOSED", "WAITLIST"}
VALID_MEMBER_STATUS = {"PENDING", "ACTIVE", "LEFT", "WAITLIST"}
VALID_JOIN_KIND = {"PERMANENT", "ONE_OFF"}
VALID_CHAT_MODE = {"OPEN", "ANNOUNCEMENTS", "CLOSED"}
VALID_VOTES = {"YES", "NO"}
MIN_DURATION = 30
MAX_DURATION = 240


def _now():
    return database.now_iso()


def _clean(value, limit=200):
    return " ".join(str(value or "").strip().split())[:limit]


def ensure_schema():
    c = database.connect()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS study_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            subject TEXT NOT NULL,
            study_goal TEXT NOT NULL,
            description TEXT,
            price_per_lesson INTEGER NOT NULL,
            max_members INTEGER NOT NULL DEFAULT 8,
            min_attendees INTEGER NOT NULL DEFAULT 2,
            recruitment_status TEXT NOT NULL DEFAULT 'OPEN',
            chat_mode TEXT NOT NULL DEFAULT 'OPEN',
            board_url TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            joined_at TEXT NOT NULL,
            left_at TEXT,
            source TEXT NOT NULL DEFAULT 'TEACHER',
            UNIQUE(group_id,user_id),
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_join_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            join_kind TEXT NOT NULL DEFAULT 'PERMANENT',
            target_lesson_id INTEGER,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by INTEGER,
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_schedule_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            weekday INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            proposal_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_schedule_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            weekday INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            majority_percent INTEGER NOT NULL DEFAULT 50,
            status TEXT NOT NULL DEFAULT 'VOTING',
            closes_at TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_schedule_votes (
            proposal_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            vote TEXT NOT NULL,
            voted_at TEXT NOT NULL,
            PRIMARY KEY(proposal_id,user_id),
            FOREIGN KEY(proposal_id) REFERENCES group_schedule_proposals(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_slot_optouts (
            slot_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY(slot_id,user_id),
            FOREIGN KEY(slot_id) REFERENCES group_schedule_slots(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            slot_id INTEGER,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            price_per_student INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'SCHEDULED',
            board_url TEXT,
            telemost_conference_id TEXT,
            telemost_join_url TEXT,
            quorum_checked_at TEXT,
            cancelled_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(group_id,start_time),
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(slot_id) REFERENCES group_schedule_slots(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS group_lesson_participants (
            lesson_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            participation_kind TEXT NOT NULL DEFAULT 'PERMANENT',
            payment_status TEXT NOT NULL DEFAULT 'PENDING',
            access_granted INTEGER NOT NULL DEFAULT 0,
            attendance_status TEXT NOT NULL DEFAULT 'EXPECTED',
            joined_at TEXT,
            left_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(lesson_id,user_id),
            FOREIGN KEY(lesson_id) REFERENCES group_lessons(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_membership_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            source_lesson_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            UNIQUE(group_id,user_id,source_lesson_id),
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(source_lesson_id) REFERENCES group_lessons(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            sender_user_id INTEGER,
            sender_role TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            deleted_at TEXT,
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(sender_user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS group_homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            lesson_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            due_at TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(lesson_id) REFERENCES group_lessons(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS group_homework_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            homework_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            text_answer TEXT,
            file_ref TEXT,
            status TEXT NOT NULL DEFAULT 'SUBMITTED',
            teacher_comment TEXT,
            score REAL,
            submitted_at TEXT NOT NULL,
            reviewed_at TEXT,
            UNIQUE(homework_id,user_id),
            FOREIGN KEY(homework_id) REFERENCES group_homework(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_group_members_active
            ON group_members(group_id,status,user_id);
        CREATE INDEX IF NOT EXISTS idx_group_slots_active
            ON group_schedule_slots(group_id,active,weekday,start_time);
        CREATE INDEX IF NOT EXISTS idx_group_lessons_time
            ON group_lessons(group_id,start_time,status);
        CREATE INDEX IF NOT EXISTS idx_group_participant_access
            ON group_lesson_participants(lesson_id,payment_status,access_granted);
        CREATE INDEX IF NOT EXISTS idx_group_join_requests_user
            ON group_join_requests(user_id,status,created_at);
        CREATE INDEX IF NOT EXISTS idx_group_homework_group
            ON group_homework(group_id,created_at DESC);
        """
    )
    c.commit()
    c.close()


def _group(group_id):
    ensure_schema()
    c = database.connect()
    row = c.execute("SELECT * FROM study_groups WHERE id=?", (int(group_id),)).fetchone()
    c.close()
    if not row:
        raise ValueError("group_not_found")
    return dict(row)


def create_group(name, subject, study_goal, price_per_lesson, max_members=8,
                 min_attendees=2, description=None, board_url=None,
                 recruitment_status="OPEN", chat_mode="OPEN", created_by=None):
    ensure_schema()
    name = _clean(name, 100)
    subject = _clean(subject, 50).upper()
    study_goal = _clean(study_goal, 50).upper()
    description = _clean(description, 1000) or None
    recruitment_status = str(recruitment_status or "OPEN").upper()
    chat_mode = str(chat_mode or "OPEN").upper()
    price = int(price_per_lesson)
    max_members = int(max_members)
    min_attendees = int(min_attendees)
    if len(name) < 2:
        raise ValueError("group_name_required")
    if price < 0:
        raise ValueError("invalid_group_price")
    if max_members < 2 or max_members > 100:
        raise ValueError("invalid_max_members")
    if min_attendees < 2 or min_attendees > max_members:
        raise ValueError("invalid_min_attendees")
    if recruitment_status not in VALID_RECRUITMENT:
        raise ValueError("invalid_recruitment_status")
    if chat_mode not in VALID_CHAT_MODE:
        raise ValueError("invalid_chat_mode")
    now = _now()
    c = database.connect()
    cur = c.execute(
        """INSERT INTO study_groups(
             name,subject,study_goal,description,price_per_lesson,max_members,
             min_attendees,recruitment_status,chat_mode,board_url,created_by,
             created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (name, subject, study_goal, description, price, max_members,
         min_attendees, recruitment_status, chat_mode, _clean(board_url, 1200) or None,
         int(created_by) if created_by is not None else None, now, now),
    )
    gid = int(cur.lastrowid)
    c.commit()
    c.close()
    return get_group(gid)


def get_group(group_id, user_id=None):
    g = _group(group_id)
    c = database.connect()
    members = c.execute(
        """SELECT gm.user_id,gm.status,gm.joined_at,u.name
           FROM group_members gm JOIN users u ON u.id=gm.user_id
           WHERE gm.group_id=? AND gm.status='ACTIVE'
           ORDER BY u.name COLLATE NOCASE""", (int(group_id),)
    ).fetchall()
    slots = c.execute(
        "SELECT * FROM group_schedule_slots WHERE group_id=? AND active=1 ORDER BY weekday,start_time",
        (int(group_id),),
    ).fetchall()
    c.close()
    result = dict(g)
    result["member_count"] = len(members)
    result["members"] = [dict(r) for r in members]
    result["slots"] = [dict(r) for r in slots]
    if user_id is not None:
        uid = int(user_id)
        result["my_membership"] = next((dict(r) for r in members if int(r["user_id"]) == uid), None)
        c = database.connect()
        optouts = c.execute(
            """SELECT o.slot_id FROM group_slot_optouts o
               JOIN group_schedule_slots s ON s.id=o.slot_id
               WHERE s.group_id=? AND o.user_id=?""", (int(group_id), uid)
        ).fetchall()
        c.close()
        result["my_optout_slot_ids"] = [int(r["slot_id"]) for r in optouts]
    return result


def list_catalog(user_id=None, include_closed=False):
    ensure_schema()
    c = database.connect()
    where = "g.active=1" if include_closed else "g.active=1 AND g.recruitment_status IN ('OPEN','WAITLIST')"
    rows = c.execute(
        f"""SELECT g.*,
               (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id=g.id AND gm.status='ACTIVE') AS member_count
            FROM study_groups g WHERE {where}
            ORDER BY g.created_at DESC"""
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["places_left"] = max(0, int(item["max_members"]) - int(item["member_count"]))
        if user_id is not None:
            membership = c.execute(
                "SELECT status FROM group_members WHERE group_id=? AND user_id=?",
                (int(item["id"]), int(user_id)),
            ).fetchone()
            item["my_status"] = membership["status"] if membership else None
        out.append(item)
    c.close()
    return out


def set_recruitment(group_id, status):
    status = str(status or "").upper()
    if status not in VALID_RECRUITMENT:
        raise ValueError("invalid_recruitment_status")
    _group(group_id)
    c = database.connect()
    c.execute("UPDATE study_groups SET recruitment_status=?,updated_at=? WHERE id=?", (status, _now(), int(group_id)))
    c.commit(); c.close()
    return {"status": "ok", "group_id": int(group_id), "recruitment_status": status}


def request_join(user_id, group_id, join_kind="PERMANENT", target_lesson_id=None):
    g = _group(group_id)
    uid = int(user_id)
    if not database.get_user(uid):
        raise PermissionError("student_not_found")
    kind = str(join_kind or "PERMANENT").upper()
    if kind not in VALID_JOIN_KIND:
        raise ValueError("invalid_join_kind")
    if g["recruitment_status"] == "CLOSED":
        raise ValueError("group_recruitment_closed")
    if kind == "PERMANENT":
        c = database.connect()
        active = c.execute("SELECT COUNT(*) n FROM group_members WHERE group_id=? AND status='ACTIVE'", (int(group_id),)).fetchone()["n"]
        c.close()
        if int(active) >= int(g["max_members"]) and g["recruitment_status"] != "WAITLIST":
            raise ValueError("group_full")
    if kind == "ONE_OFF" and not target_lesson_id:
        raise ValueError("target_lesson_required")
    c = database.connect()
    cur = c.execute(
        """INSERT INTO group_join_requests(group_id,user_id,join_kind,target_lesson_id,status,created_at)
           VALUES(?,?,?,?, 'PENDING',?)""",
        (int(group_id), uid, kind, int(target_lesson_id) if target_lesson_id else None, _now()),
    )
    rid = int(cur.lastrowid)
    c.commit(); c.close()
    return {"status": "ok", "request_id": rid, "group_id": int(group_id), "join_kind": kind}


def approve_join(request_id, teacher_id):
    ensure_schema()
    c = database.connect()
    req = c.execute("SELECT * FROM group_join_requests WHERE id=?", (int(request_id),)).fetchone()
    if not req:
        c.close(); raise ValueError("join_request_not_found")
    if req["status"] != "PENDING":
        c.close(); raise ValueError("join_request_not_pending")
    now = _now()
    if req["join_kind"] == "PERMANENT":
        g = c.execute("SELECT max_members FROM study_groups WHERE id=?", (int(req["group_id"]),)).fetchone()
        active = c.execute("SELECT COUNT(*) n FROM group_members WHERE group_id=? AND status='ACTIVE'", (int(req["group_id"]),)).fetchone()["n"]
        if int(active) >= int(g["max_members"]):
            c.close(); raise ValueError("group_full")
        c.execute(
            """INSERT INTO group_members(group_id,user_id,status,joined_at,source)
               VALUES(?,?,'ACTIVE',?,'SELF_SERVICE')
               ON CONFLICT(group_id,user_id) DO UPDATE SET status='ACTIVE',left_at=NULL,joined_at=excluded.joined_at""",
            (int(req["group_id"]), int(req["user_id"]), now),
        )
    else:
        lesson = c.execute("SELECT * FROM group_lessons WHERE id=? AND group_id=?", (int(req["target_lesson_id"]), int(req["group_id"]))).fetchone()
        if not lesson:
            c.close(); raise ValueError("group_lesson_not_found")
        c.execute(
            """INSERT INTO group_lesson_participants(lesson_id,user_id,participation_kind,payment_status,access_granted,attendance_status,created_at,updated_at)
               VALUES(?,?,'ONE_OFF','PENDING',0,'EXPECTED',?,?)
               ON CONFLICT(lesson_id,user_id) DO UPDATE SET participation_kind='ONE_OFF',updated_at=excluded.updated_at""",
            (int(req["target_lesson_id"]), int(req["user_id"]), now, now),
        )
    c.execute("UPDATE group_join_requests SET status='APPROVED',reviewed_at=?,reviewed_by=? WHERE id=?", (now, int(teacher_id), int(request_id)))
    c.commit(); c.close()
    return {"status": "ok", "request_id": int(request_id)}


def leave_group(user_id, group_id):
    _group(group_id)
    c = database.connect()
    cur = c.execute(
        "UPDATE group_members SET status='LEFT',left_at=? WHERE group_id=? AND user_id=? AND status='ACTIVE'",
        (_now(), int(group_id), int(user_id)),
    )
    c.commit(); c.close()
    if not cur.rowcount:
        raise ValueError("active_membership_not_found")
    return {"status": "ok", "group_id": int(group_id), "user_id": int(user_id)}


def add_initial_slot(group_id, weekday, start_time, duration_minutes):
    _group(group_id)
    weekday = int(weekday); duration = int(duration_minutes)
    if weekday < 0 or weekday > 6:
        raise ValueError("invalid_weekday")
    if duration < MIN_DURATION or duration > MAX_DURATION:
        raise ValueError("invalid_duration")
    start_time = _clean(start_time, 8)
    datetime.strptime(start_time, "%H:%M")
    now = _now(); c = database.connect()
    cur = c.execute(
        """INSERT INTO group_schedule_slots(group_id,weekday,start_time,duration_minutes,active,created_at,updated_at)
           VALUES(?,?,?,?,1,?,?)""",
        (int(group_id), weekday, start_time, duration, now, now),
    )
    sid = int(cur.lastrowid); c.commit(); c.close()
    return {"status": "ok", "slot_id": sid}


def propose_additional_slot(group_id, weekday, start_time, duration_minutes, created_by, majority_percent=50, closes_at=None):
    _group(group_id)
    weekday = int(weekday); duration = int(duration_minutes); majority = int(majority_percent)
    if weekday < 0 or weekday > 6:
        raise ValueError("invalid_weekday")
    if duration < MIN_DURATION or duration > MAX_DURATION:
        raise ValueError("invalid_duration")
    if majority < 50 or majority > 100:
        raise ValueError("invalid_majority_percent")
    start_time = _clean(start_time, 8); datetime.strptime(start_time, "%H:%M")
    c = database.connect(); cur = c.execute(
        """INSERT INTO group_schedule_proposals(group_id,weekday,start_time,duration_minutes,majority_percent,status,closes_at,created_by,created_at)
           VALUES(?,?,?,?,?,'VOTING',?,?,?)""",
        (int(group_id), weekday, start_time, duration, majority, closes_at, int(created_by), _now()),
    ); pid = int(cur.lastrowid); c.commit(); c.close()
    return proposal_summary(pid)


def vote_schedule(user_id, proposal_id, vote):
    ensure_schema(); vote = str(vote or "").upper()
    if vote not in VALID_VOTES:
        raise ValueError("invalid_vote")
    c = database.connect()
    p = c.execute("SELECT * FROM group_schedule_proposals WHERE id=?", (int(proposal_id),)).fetchone()
    if not p or p["status"] != "VOTING":
        c.close(); raise ValueError("proposal_not_voting")
    member = c.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=? AND status='ACTIVE'", (int(p["group_id"]), int(user_id))).fetchone()
    if not member:
        c.close(); raise PermissionError("not_group_member")
    c.execute(
        """INSERT INTO group_schedule_votes(proposal_id,user_id,vote,voted_at) VALUES(?,?,?,?)
           ON CONFLICT(proposal_id,user_id) DO UPDATE SET vote=excluded.vote,voted_at=excluded.voted_at""",
        (int(proposal_id), int(user_id), vote, _now()),
    )
    c.commit(); c.close()
    return proposal_summary(proposal_id)


def proposal_summary(proposal_id):
    ensure_schema(); c = database.connect()
    p = c.execute("SELECT * FROM group_schedule_proposals WHERE id=?", (int(proposal_id),)).fetchone()
    if not p:
        c.close(); raise ValueError("proposal_not_found")
    active = int(c.execute("SELECT COUNT(*) n FROM group_members WHERE group_id=? AND status='ACTIVE'", (int(p["group_id"]),)).fetchone()["n"])
    votes = c.execute("SELECT vote,COUNT(*) n FROM group_schedule_votes WHERE proposal_id=? GROUP BY vote", (int(proposal_id),)).fetchall()
    c.close(); counts = {"YES": 0, "NO": 0}
    for r in votes: counts[str(r["vote"])] = int(r["n"])
    threshold = max(1, math.floor(active * int(p["majority_percent"]) / 100) + 1)
    return {**dict(p), "active_members": active, "yes": counts["YES"], "no": counts["NO"], "required_yes": threshold, "can_apply": counts["YES"] >= threshold}


def apply_proposal(proposal_id, teacher_id):
    summary = proposal_summary(proposal_id)
    if summary["status"] != "VOTING":
        raise ValueError("proposal_not_voting")
    if not summary["can_apply"]:
        raise ValueError("majority_not_reached")
    now = _now(); c = database.connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        cur = c.execute(
            """INSERT INTO group_schedule_slots(group_id,weekday,start_time,duration_minutes,active,proposal_id,created_at,updated_at)
               VALUES(?,?,?,?,1,?,?,?)""",
            (int(summary["group_id"]), int(summary["weekday"]), summary["start_time"], int(summary["duration_minutes"]), int(proposal_id), now, now),
        )
        slot_id = int(cur.lastrowid)
        no_rows = c.execute("SELECT user_id FROM group_schedule_votes WHERE proposal_id=? AND vote='NO'", (int(proposal_id),)).fetchall()
        for row in no_rows:
            c.execute("INSERT OR IGNORE INTO group_slot_optouts(slot_id,user_id,reason,created_at) VALUES(?,?,?,?)", (slot_id, int(row["user_id"]), "DECLINED_GROUP_PROPOSAL", now))
        c.execute("UPDATE group_schedule_proposals SET status='APPLIED',resolved_at=? WHERE id=?", (now, int(proposal_id)))
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()
    return {"status": "ok", "proposal_id": int(proposal_id), "slot_id": slot_id, "opted_out": len(no_rows), "applied_by": int(teacher_id)}


def generate_lesson(group_id, slot_id, start_time):
    g = _group(group_id); ensure_schema()
    start = datetime.fromisoformat(str(start_time))
    c = database.connect(); slot = c.execute("SELECT * FROM group_schedule_slots WHERE id=? AND group_id=? AND active=1", (int(slot_id), int(group_id))).fetchone()
    if not slot:
        c.close(); raise ValueError("group_slot_not_found")
    end = start + timedelta(minutes=int(slot["duration_minutes"])); now = _now()
    cur = c.execute(
        """INSERT OR IGNORE INTO group_lessons(group_id,slot_id,start_time,end_time,price_per_student,status,board_url,created_at,updated_at)
           VALUES(?,?,?,?,?,'SCHEDULED',?,?,?)""",
        (int(group_id), int(slot_id), start.isoformat(), end.isoformat(), int(g["price_per_lesson"]), g.get("board_url"), now, now),
    )
    row = c.execute("SELECT id FROM group_lessons WHERE group_id=? AND start_time=?", (int(group_id), start.isoformat())).fetchone()
    lesson_id = int(row["id"])
    members = c.execute(
        """SELECT gm.user_id FROM group_members gm
           WHERE gm.group_id=? AND gm.status='ACTIVE'
             AND NOT EXISTS(SELECT 1 FROM group_slot_optouts o WHERE o.slot_id=? AND o.user_id=gm.user_id)""",
        (int(group_id), int(slot_id)),
    ).fetchall()
    for m in members:
        c.execute(
            """INSERT OR IGNORE INTO group_lesson_participants(lesson_id,user_id,participation_kind,payment_status,access_granted,attendance_status,created_at,updated_at)
               VALUES(?,?,'PERMANENT','PENDING',0,'EXPECTED',?,?)""",
            (lesson_id, int(m["user_id"]), now, now),
        )
    c.commit(); c.close()
    return {"status": "ok", "lesson_id": lesson_id, "participant_count": len(members), "created": bool(cur.rowcount)}


def set_payment_status(lesson_id, user_id, payment_status):
    ensure_schema(); status = str(payment_status or "").upper()
    if status not in {"PENDING", "PAID", "COVERED", "REFUNDED", "WAIVED"}:
        raise ValueError("invalid_payment_status")
    access = 1 if status in {"PAID", "COVERED", "WAIVED"} else 0
    c = database.connect(); cur = c.execute(
        "UPDATE group_lesson_participants SET payment_status=?,access_granted=?,updated_at=? WHERE lesson_id=? AND user_id=?",
        (status, access, _now(), int(lesson_id), int(user_id)),
    ); c.commit(); c.close()
    if not cur.rowcount: raise ValueError("group_participant_not_found")
    return {"status": "ok", "lesson_id": int(lesson_id), "user_id": int(user_id), "payment_status": status, "access_granted": bool(access)}


def lesson_access(user_id, lesson_id):
    ensure_schema(); c = database.connect()
    row = c.execute(
        """SELECT p.*,l.start_time,l.end_time,l.status,l.telemost_join_url,l.board_url,g.name AS group_name
           FROM group_lesson_participants p
           JOIN group_lessons l ON l.id=p.lesson_id
           JOIN study_groups g ON g.id=l.group_id
           WHERE p.lesson_id=? AND p.user_id=?""", (int(lesson_id), int(user_id))
    ).fetchone(); c.close()
    if not row: raise PermissionError("group_lesson_not_available")
    allowed = bool(row["access_granted"]) and row["status"] not in {"CANCELLED", "QUORUM_FAILED"}
    return {
        "allowed": allowed,
        "lesson_id": int(lesson_id),
        "group_name": row["group_name"],
        "start_time": row["start_time"],
        "payment_status": row["payment_status"],
        "meeting_url": row["telemost_join_url"] if allowed else None,
        "board_url": row["board_url"] if allowed else None,
    }


def check_quorum(lesson_id):
    ensure_schema(); c = database.connect()
    lesson = c.execute("SELECT l.*,g.min_attendees FROM group_lessons l JOIN study_groups g ON g.id=l.group_id WHERE l.id=?", (int(lesson_id),)).fetchone()
    if not lesson:
        c.close(); raise ValueError("group_lesson_not_found")
    participants = int(c.execute("SELECT COUNT(*) n FROM group_lesson_participants WHERE lesson_id=?", (int(lesson_id),)).fetchone()["n"])
    now = _now(); ok = participants >= int(lesson["min_attendees"])
    if not ok:
        c.execute("UPDATE group_lessons SET status='QUORUM_FAILED',quorum_checked_at=?,cancelled_reason='NOT_ENOUGH_STUDENTS',updated_at=? WHERE id=?", (now, now, int(lesson_id)))
        c.execute("UPDATE group_lesson_participants SET access_granted=0,updated_at=? WHERE lesson_id=?", (now, int(lesson_id)))
    else:
        c.execute("UPDATE group_lessons SET quorum_checked_at=?,updated_at=? WHERE id=?", (now, now, int(lesson_id)))
    c.commit(); c.close()
    return {"status": "ok", "lesson_id": int(lesson_id), "quorum": ok, "participants": participants, "minimum": int(lesson["min_attendees"])}


def complete_lesson(lesson_id):
    ensure_schema(); now = _now(); c = database.connect()
    lesson = c.execute("SELECT * FROM group_lessons WHERE id=?", (int(lesson_id),)).fetchone()
    if not lesson:
        c.close(); raise ValueError("group_lesson_not_found")
    c.execute("UPDATE group_lessons SET status='COMPLETED',updated_at=? WHERE id=?", (now, int(lesson_id)))
    one_off = c.execute("SELECT user_id FROM group_lesson_participants WHERE lesson_id=? AND participation_kind='ONE_OFF'", (int(lesson_id),)).fetchall()
    for row in one_off:
        c.execute(
            """INSERT OR IGNORE INTO group_membership_offers(group_id,user_id,source_lesson_id,status,created_at)
               VALUES(?,?,?,'OPEN',?)""",
            (int(lesson["group_id"]), int(row["user_id"]), int(lesson_id), now),
        )
    c.commit(); c.close()
    return {"status": "ok", "lesson_id": int(lesson_id), "permanent_offers_created": len(one_off)}


def create_homework(group_id, title, description=None, due_at=None, lesson_id=None, created_by=None):
    _group(group_id); title = _clean(title, 200)
    if not title: raise ValueError("homework_title_required")
    c = database.connect(); cur = c.execute(
        """INSERT INTO group_homework(group_id,lesson_id,title,description,due_at,created_by,created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (int(group_id), int(lesson_id) if lesson_id else None, title, _clean(description, 4000) or None, due_at, int(created_by) if created_by is not None else None, _now()),
    ); hid = int(cur.lastrowid); c.commit(); c.close(); return {"status": "ok", "homework_id": hid}


def submit_homework(user_id, homework_id, text_answer=None, file_ref=None):
    ensure_schema(); c = database.connect()
    hw = c.execute("SELECT * FROM group_homework WHERE id=?", (int(homework_id),)).fetchone()
    if not hw:
        c.close(); raise ValueError("group_homework_not_found")
    member = c.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=? AND status='ACTIVE'", (int(hw["group_id"]), int(user_id))).fetchone()
    if not member:
        c.close(); raise PermissionError("not_group_member")
    now = _now(); c.execute(
        """INSERT INTO group_homework_submissions(homework_id,user_id,text_answer,file_ref,status,submitted_at)
           VALUES(?,?,?,?, 'SUBMITTED',?)
           ON CONFLICT(homework_id,user_id) DO UPDATE SET text_answer=excluded.text_answer,file_ref=excluded.file_ref,status='SUBMITTED',submitted_at=excluded.submitted_at,teacher_comment=NULL,score=NULL,reviewed_at=NULL""",
        (int(homework_id), int(user_id), str(text_answer or "")[:12000] or None, str(file_ref or "")[:1200] or None, now),
    ); c.commit(); c.close(); return {"status": "ok", "homework_id": int(homework_id), "user_id": int(user_id)}


def homework_for_teacher(homework_id):
    ensure_schema(); c = database.connect()
    hw = c.execute("SELECT * FROM group_homework WHERE id=?", (int(homework_id),)).fetchone()
    if not hw:
        c.close(); raise ValueError("group_homework_not_found")
    rows = c.execute(
        """SELECT gm.user_id,u.name,s.status,s.text_answer,s.file_ref,s.teacher_comment,s.score,s.submitted_at,s.reviewed_at
           FROM group_members gm JOIN users u ON u.id=gm.user_id
           LEFT JOIN group_homework_submissions s ON s.homework_id=? AND s.user_id=gm.user_id
           WHERE gm.group_id=? AND gm.status='ACTIVE' ORDER BY u.name COLLATE NOCASE""",
        (int(homework_id), int(hw["group_id"])),
    ).fetchall(); c.close()
    return {"homework": dict(hw), "submissions": [dict(r) for r in rows]}


def homework_for_student(user_id, homework_id):
    ensure_schema(); c = database.connect()
    hw = c.execute("SELECT * FROM group_homework WHERE id=?", (int(homework_id),)).fetchone()
    if not hw:
        c.close(); raise ValueError("group_homework_not_found")
    member = c.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=? AND status='ACTIVE'", (int(hw["group_id"]), int(user_id))).fetchone()
    if not member:
        c.close(); raise PermissionError("not_group_member")
    sub = c.execute("SELECT * FROM group_homework_submissions WHERE homework_id=? AND user_id=?", (int(homework_id), int(user_id))).fetchone(); c.close()
    return {"homework": dict(hw), "my_submission": dict(sub) if sub else None}


def review_homework(teacher_id, homework_id, user_id, teacher_comment=None, score=None):
    ensure_schema(); c = database.connect()
    cur = c.execute(
        """UPDATE group_homework_submissions SET status='REVIEWED',teacher_comment=?,score=?,reviewed_at=?
           WHERE homework_id=? AND user_id=?""",
        (str(teacher_comment or "")[:4000] or None, float(score) if score is not None else None, _now(), int(homework_id), int(user_id)),
    ); c.commit(); c.close()
    if not cur.rowcount: raise ValueError("submission_not_found")
    return {"status": "ok", "homework_id": int(homework_id), "user_id": int(user_id), "reviewed_by": int(teacher_id)}
