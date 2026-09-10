"""Group trial attendance and individual-coaching recommendations for Adelia.

This module keeps trial participation separate from permanent group membership.
It also stores explainable recommendations when a student is persistently
behind the pace of a group and may benefit from individual lessons.
"""
from __future__ import annotations

from datetime import datetime
import json

import database
from web_backend import group_lessons

TRIAL_PENDING = "PENDING"
TRIAL_APPROVED = "APPROVED"
TRIAL_ATTENDED = "ATTENDED"
TRIAL_DECLINED = "DECLINED"
TRIAL_CANCELLED = "CANCELLED"

REC_OPEN = "OPEN"
REC_DISMISSED = "DISMISSED"
REC_ACCEPTED = "ACCEPTED"
REC_RESOLVED = "RESOLVED"


def _now():
    return database.now_iso()


def ensure_schema():
    group_lessons.ensure_schema()
    c = database.connect()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS group_trial_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            target_lesson_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            price_override INTEGER,
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by INTEGER,
            completed_at TEXT,
            note TEXT,
            UNIQUE(group_id,user_id,target_lesson_id),
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(target_lesson_id) REFERENCES group_lessons(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS group_student_risk_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            captured_at TEXT NOT NULL,
            homework_completion REAL,
            homework_quality REAL,
            attendance_rate REAL,
            assessment_score REAL,
            pace_score REAL,
            teacher_signal REAL,
            risk_score REAL NOT NULL,
            reasons_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS individual_coaching_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            risk_snapshot_id INTEGER,
            status TEXT NOT NULL DEFAULT 'OPEN',
            reason TEXT NOT NULL,
            suggested_topics_json TEXT NOT NULL DEFAULT '[]',
            suggested_frequency TEXT,
            suggested_duration_minutes INTEGER,
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            reviewed_by INTEGER,
            resolved_at TEXT,
            UNIQUE(group_id,user_id,status),
            FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(risk_snapshot_id) REFERENCES group_student_risk_snapshots(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_group_trial_user
            ON group_trial_requests(user_id,status,created_at);
        CREATE INDEX IF NOT EXISTS idx_group_trial_group
            ON group_trial_requests(group_id,status,target_lesson_id);
        CREATE INDEX IF NOT EXISTS idx_group_risk_latest
            ON group_student_risk_snapshots(group_id,user_id,captured_at DESC);
        CREATE INDEX IF NOT EXISTS idx_group_coaching_open
            ON individual_coaching_recommendations(group_id,status,user_id);
        """
    )
    c.commit(); c.close()


def request_group_trial(user_id, group_id, target_lesson_id, note=None):
    ensure_schema()
    uid = int(user_id); gid = int(group_id); lid = int(target_lesson_id)
    if not database.get_user(uid):
        raise PermissionError("student_not_found")
    g = group_lessons.get_group(gid, uid)
    if g.get("recruitment_status") == "CLOSED":
        raise ValueError("group_recruitment_closed")
    c = database.connect()
    lesson = c.execute("SELECT id,status FROM group_lessons WHERE id=? AND group_id=?", (lid,gid)).fetchone()
    if not lesson:
        c.close(); raise ValueError("group_lesson_not_found")
    if lesson["status"] in {"CANCELLED","COMPLETED","QUORUM_FAILED"}:
        c.close(); raise ValueError("group_lesson_unavailable")
    existing_member = c.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=? AND status='ACTIVE'", (gid,uid)).fetchone()
    if existing_member:
        c.close(); raise ValueError("already_group_member")
    try:
        cur = c.execute(
            """INSERT INTO group_trial_requests(group_id,user_id,target_lesson_id,status,created_at,note)
               VALUES(?,?,?,'PENDING',?,?)""",
            (gid,uid,lid,_now(),str(note or "")[:1000] or None),
        )
        rid = int(cur.lastrowid)
        c.commit()
    except Exception:
        c.rollback(); c.close(); raise
    c.close()
    return {"status":"ok","trial_request_id":rid,"group_id":gid,"lesson_id":lid}


def approve_group_trial(request_id, teacher_id, price_override=0):
    ensure_schema(); rid=int(request_id)
    c=database.connect(); req=c.execute("SELECT * FROM group_trial_requests WHERE id=?",(rid,)).fetchone()
    if not req:
        c.close(); raise ValueError("group_trial_not_found")
    if req["status"] != TRIAL_PENDING:
        c.close(); raise ValueError("group_trial_not_pending")
    price=int(price_override or 0)
    if price < 0:
        c.close(); raise ValueError("invalid_trial_price")
    now=_now()
    c.execute(
        """INSERT INTO group_lesson_participants(
             lesson_id,user_id,participation_kind,payment_status,access_granted,attendance_status,created_at,updated_at)
           VALUES(?,?,'TRIAL',?,0,'EXPECTED',?,?)
           ON CONFLICT(lesson_id,user_id) DO UPDATE SET
             participation_kind='TRIAL',payment_status=excluded.payment_status,
             access_granted=0,attendance_status='EXPECTED',updated_at=excluded.updated_at""",
        (int(req["target_lesson_id"]),int(req["user_id"]),'WAIVED' if price==0 else 'PENDING',now,now),
    )
    c.execute(
        "UPDATE group_trial_requests SET status='APPROVED',price_override=?,reviewed_at=?,reviewed_by=? WHERE id=?",
        (price,now,int(teacher_id),rid),
    )
    c.commit(); c.close()
    return {"status":"ok","trial_request_id":rid,"price":price}


def finish_group_trial(request_id, attended=True):
    ensure_schema(); rid=int(request_id); now=_now(); c=database.connect()
    req=c.execute("SELECT * FROM group_trial_requests WHERE id=?",(rid,)).fetchone()
    if not req:
        c.close(); raise ValueError("group_trial_not_found")
    if req["status"] not in {TRIAL_APPROVED,TRIAL_ATTENDED}:
        c.close(); raise ValueError("group_trial_not_active")
    status=TRIAL_ATTENDED if attended else TRIAL_CANCELLED
    c.execute("UPDATE group_trial_requests SET status=?,completed_at=? WHERE id=?",(status,now,rid))
    if attended:
        c.execute(
            """INSERT OR IGNORE INTO group_membership_offers(group_id,user_id,source_lesson_id,status,created_at)
               VALUES(?,?,?,'OPEN',?)""",
            (int(req["group_id"]),int(req["user_id"]),int(req["target_lesson_id"]),now),
        )
    c.commit(); c.close()
    return {"status":"ok","trial_request_id":rid,"attended":bool(attended),"membership_offer_created":bool(attended)}


def trial_status_for_student(user_id, group_id=None):
    ensure_schema(); c=database.connect(); params=[int(user_id)]; where="user_id=?"
    if group_id is not None:
        where += " AND group_id=?"; params.append(int(group_id))
    rows=c.execute(f"SELECT * FROM group_trial_requests WHERE {where} ORDER BY created_at DESC",tuple(params)).fetchall(); c.close()
    return [dict(r) for r in rows]


def _clamp01(value):
    if value is None:
        return None
    return max(0.0,min(1.0,float(value)))


def record_risk_snapshot(group_id,user_id,*,homework_completion=None,homework_quality=None,
                         attendance_rate=None,assessment_score=None,pace_score=None,
                         teacher_signal=None,reasons=None):
    """Store an explainable lag-risk snapshot.

    Inputs are normalized 0..1 where 1 is good, except teacher_signal where 1
    means strong concern. Missing metrics are ignored. The result is a risk
    score 0..1 where larger means the student is further behind.
    """
    ensure_schema(); gid=int(group_id); uid=int(user_id)
    group_lessons.get_group(gid,uid)
    metrics={
        "homework_completion":_clamp01(homework_completion),
        "homework_quality":_clamp01(homework_quality),
        "attendance_rate":_clamp01(attendance_rate),
        "assessment_score":_clamp01(assessment_score),
        "pace_score":_clamp01(pace_score),
    }
    concern=_clamp01(teacher_signal)
    weighted=[]
    weights={"homework_completion":0.18,"homework_quality":0.18,"attendance_rate":0.12,"assessment_score":0.25,"pace_score":0.27}
    for key,val in metrics.items():
        if val is not None:
            weighted.append((1.0-val,weights[key]))
    if concern is not None:
        weighted.append((concern,0.20))
    if not weighted:
        raise ValueError("risk_metrics_required")
    total_w=sum(w for _,w in weighted); risk=sum(v*w for v,w in weighted)/total_w
    reason_list=[str(x)[:300] for x in (reasons or []) if str(x).strip()][:12]
    c=database.connect(); cur=c.execute(
        """INSERT INTO group_student_risk_snapshots(
             group_id,user_id,captured_at,homework_completion,homework_quality,attendance_rate,
             assessment_score,pace_score,teacher_signal,risk_score,reasons_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (gid,uid,_now(),metrics["homework_completion"],metrics["homework_quality"],metrics["attendance_rate"],metrics["assessment_score"],metrics["pace_score"],concern,float(risk),json.dumps(reason_list,ensure_ascii=False)),
    ); sid=int(cur.lastrowid); c.commit(); c.close()
    return {"status":"ok","snapshot_id":sid,"risk_score":round(risk,4),"reasons":reason_list}


def maybe_recommend_individual(group_id,user_id,*,threshold=0.62,min_snapshots=2,suggested_topics=None,
                               suggested_frequency="1 занятие раз в 1–2 недели",suggested_duration_minutes=60):
    """Create a recommendation only for persistent, not one-off, lag.

    The student is never auto-booked. The teacher can review/dismiss/accept the
    recommendation before it is surfaced as an offer to the student.
    """
    ensure_schema(); gid=int(group_id); uid=int(user_id); threshold=float(threshold)
    c=database.connect(); rows=c.execute(
        """SELECT * FROM group_student_risk_snapshots
           WHERE group_id=? AND user_id=? ORDER BY captured_at DESC LIMIT ?""",
        (gid,uid,max(2,int(min_snapshots))),
    ).fetchall()
    if len(rows) < int(min_snapshots):
        c.close(); return {"status":"insufficient_history","needed":int(min_snapshots),"have":len(rows)}
    recent=rows[:int(min_snapshots)]
    if not all(float(r["risk_score"]) >= threshold for r in recent):
        c.close(); return {"status":"no_recommendation","risk_scores":[float(r["risk_score"]) for r in recent]}
    existing=c.execute(
        "SELECT id FROM individual_coaching_recommendations WHERE group_id=? AND user_id=? AND status='OPEN' LIMIT 1",
        (gid,uid),
    ).fetchone()
    if existing:
        c.close(); return {"status":"already_open","recommendation_id":int(existing["id"])}
    latest=recent[0]
    reasons=json.loads(latest["reasons_json"] or "[]")
    reason="Устойчивое отставание от темпа группы"
    if reasons:
        reason += ": " + "; ".join(reasons[:3])
    cur=c.execute(
        """INSERT INTO individual_coaching_recommendations(
             group_id,user_id,risk_snapshot_id,status,reason,suggested_topics_json,
             suggested_frequency,suggested_duration_minutes,created_at)
           VALUES(?,?,?,'OPEN',?,?,?,?,?)""",
        (gid,uid,int(latest["id"]),reason,json.dumps([str(x)[:200] for x in (suggested_topics or [])][:10],ensure_ascii=False),str(suggested_frequency or "")[:200] or None,int(suggested_duration_minutes or 60),_now()),
    ); rec_id=int(cur.lastrowid); c.commit(); c.close()
    return {"status":"recommended","recommendation_id":rec_id,"reason":reason,"suggested_topics":suggested_topics or [],"suggested_frequency":suggested_frequency,"suggested_duration_minutes":int(suggested_duration_minutes or 60)}


def review_recommendation(recommendation_id,teacher_id,decision):
    ensure_schema(); decision=str(decision or "").upper()
    if decision not in {REC_ACCEPTED,REC_DISMISSED}:
        raise ValueError("invalid_recommendation_decision")
    c=database.connect(); row=c.execute("SELECT * FROM individual_coaching_recommendations WHERE id=?",(int(recommendation_id),)).fetchone()
    if not row:
        c.close(); raise ValueError("recommendation_not_found")
    if row["status"] != REC_OPEN:
        c.close(); raise ValueError("recommendation_not_open")
    c.execute("UPDATE individual_coaching_recommendations SET status=?,reviewed_at=?,reviewed_by=? WHERE id=?",(decision,_now(),int(teacher_id),int(recommendation_id)))
    c.commit(); c.close()
    return {"status":"ok","recommendation_id":int(recommendation_id),"decision":decision}


def open_recommendations_for_teacher(group_id=None):
    ensure_schema(); c=database.connect(); params=[]; where="r.status='OPEN'"
    if group_id is not None:
        where += " AND r.group_id=?"; params.append(int(group_id))
    rows=c.execute(
        f"""SELECT r.*,u.name AS student_name,g.name AS group_name
            FROM individual_coaching_recommendations r
            JOIN users u ON u.id=r.user_id
            JOIN study_groups g ON g.id=r.group_id
            WHERE {where} ORDER BY r.created_at DESC""",tuple(params)
    ).fetchall(); c.close()
    return [dict(r) for r in rows]
