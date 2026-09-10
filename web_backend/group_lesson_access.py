"""Teacher-controlled access lifecycle for concrete group lessons.

Payment is advisory. It never grants or revokes access by itself. The teacher
chooses ADMITTED/EXCLUDED for each expected participant. Links are returned only
after the teacher explicitly starts the lesson.
"""
from __future__ import annotations

import database
from web_backend import group_lessons, group_finance

VALID_DECISIONS={"PENDING","ADMITTED","EXCLUDED"}
FINAL_LESSON_STATES={"COMPLETED","CANCELLED","QUORUM_FAILED"}


def _now(): return database.now_iso()


def ensure_schema():
    group_finance.ensure_schema(); c=database.connect()
    # Additive migration keeps old group_lessons data readable.
    cols={r[1] for r in c.execute("PRAGMA table_info(group_lesson_participants)").fetchall()}
    if "admission_status" not in cols:
        c.execute("ALTER TABLE group_lesson_participants ADD COLUMN admission_status TEXT NOT NULL DEFAULT 'PENDING'")
    if "admission_decided_at" not in cols:
        c.execute("ALTER TABLE group_lesson_participants ADD COLUMN admission_decided_at TEXT")
    if "admission_decided_by" not in cols:
        c.execute("ALTER TABLE group_lesson_participants ADD COLUMN admission_decided_by INTEGER")
    if "financial_attention" not in cols:
        c.execute("ALTER TABLE group_lesson_participants ADD COLUMN financial_attention INTEGER NOT NULL DEFAULT 0")
    lcols={r[1] for r in c.execute("PRAGMA table_info(group_lessons)").fetchall()}
    if "started_at" not in lcols:
        c.execute("ALTER TABLE group_lessons ADD COLUMN started_at TEXT")
    if "started_by" not in lcols:
        c.execute("ALTER TABLE group_lessons ADD COLUMN started_by INTEGER")
    c.execute("CREATE INDEX IF NOT EXISTS idx_group_admission ON group_lesson_participants(lesson_id,admission_status,financial_attention)")
    c.commit(); c.close()


def refresh_financial_flags(lesson_id):
    ensure_schema(); lid=int(lesson_id); c=database.connect(); rows=c.execute(
        "SELECT user_id FROM group_lesson_participants WHERE lesson_id=? AND attendance_status='EXPECTED'",(lid,)
    ).fetchall(); c.close(); out=[]
    for row in rows:
        uid=int(row["user_id"]); state=group_finance.financial_status_for_lesson(lid,uid)
        attention=0 if state["covered"] else 1
        c=database.connect(); c.execute(
            "UPDATE group_lesson_participants SET payment_status=?,financial_attention=?,updated_at=? WHERE lesson_id=? AND user_id=?",
            (state["status"],attention,_now(),lid,uid),
        ); c.commit(); c.close(); out.append({"user_id":uid,**state,"financial_attention":bool(attention)})
    return out


def teacher_start_preview(lesson_id):
    ensure_schema(); lid=int(lesson_id); refresh_financial_flags(lid); c=database.connect()
    lesson=c.execute("SELECT gl.*,g.name AS group_name,g.min_attendees FROM group_lessons gl JOIN study_groups g ON g.id=gl.group_id WHERE gl.id=?",(lid,)).fetchone()
    if not lesson:
        c.close(); raise ValueError("group_lesson_not_found")
    rows=c.execute("""SELECT p.*,u.name FROM group_lesson_participants p JOIN users u ON u.id=p.user_id
                      WHERE p.lesson_id=? AND p.attendance_status='EXPECTED' ORDER BY u.name COLLATE NOCASE""",(lid,)).fetchall(); c.close()
    participants=[dict(r) for r in rows]
    return {"lesson":dict(lesson),"participants":participants,"unresolved":[p for p in participants if p["admission_status"]=="PENDING"],"unpaid_attention":[p for p in participants if int(p["financial_attention"] or 0)==1],"admitted_count":sum(1 for p in participants if p["admission_status"]=="ADMITTED")}


def decide_admission(lesson_id,user_id,decision,teacher_id):
    ensure_schema(); lid=int(lesson_id); uid=int(user_id); decision=str(decision or "").upper()
    if decision not in {"ADMITTED","EXCLUDED"}: raise ValueError("invalid_admission_decision")
    c=database.connect(); lesson=c.execute("SELECT status FROM group_lessons WHERE id=?",(lid,)).fetchone()
    if not lesson:
        c.close(); raise ValueError("group_lesson_not_found")
    if lesson["status"] in FINAL_LESSON_STATES or lesson["status"]=="STARTED":
        c.close(); raise ValueError("group_lesson_admission_locked")
    cur=c.execute("""UPDATE group_lesson_participants SET admission_status=?,admission_decided_at=?,admission_decided_by=?,access_granted=0,updated_at=?
                     WHERE lesson_id=? AND user_id=? AND attendance_status='EXPECTED'""",
                  (decision,_now(),int(teacher_id),_now(),lid,uid))
    c.commit(); c.close()
    if not cur.rowcount: raise ValueError("group_lesson_participant_not_found")
    return {"status":"ok","lesson_id":lid,"user_id":uid,"admission_status":decision}


def start_group_lesson(lesson_id,teacher_id):
    ensure_schema(); lid=int(lesson_id); preview=teacher_start_preview(lid); lesson=preview["lesson"]
    if lesson["status"]=="STARTED": return {"status":"already_started","lesson_id":lid,"participants":preview["participants"]}
    if lesson["status"] in FINAL_LESSON_STATES: raise ValueError("group_lesson_not_startable")
    if preview["unresolved"]: raise ValueError("group_lesson_has_unresolved_admissions")
    admitted=[p for p in preview["participants"] if p["admission_status"]=="ADMITTED"]
    minimum=max(2,int(lesson["min_attendees"] or 2))
    if len(admitted)<minimum:
        raise ValueError("group_lesson_quorum_not_met")
    now=_now(); c=database.connect()
    c.execute("UPDATE group_lessons SET status='STARTED',started_at=?,started_by=?,updated_at=? WHERE id=?",(now,int(teacher_id),now,lid))
    c.execute("UPDATE group_lesson_participants SET access_granted=CASE WHEN admission_status='ADMITTED' THEN 1 ELSE 0 END,updated_at=? WHERE lesson_id=?",(now,lid))
    c.commit(); c.close()
    # A package is consumed only for an admitted participant when the lesson actually starts.
    reservations=[]
    for p in admitted:
        uid=int(p["user_id"]); fin=group_finance.financial_status_for_lesson(lid,uid)
        if fin["status"]=="COVERED":
            try: reservations.append({"user_id":uid,**group_finance.reserve_subscription_for_lesson(lid,uid)})
            except ValueError: pass
    return {"status":"started","lesson_id":lid,"admitted_user_ids":[int(p["user_id"]) for p in admitted],"reservations":reservations}


def student_lesson_access(lesson_id,user_id):
    ensure_schema(); lid=int(lesson_id); uid=int(user_id); c=database.connect()
    row=c.execute("""SELECT gl.status,gl.board_url,gl.telemost_join_url,p.admission_status,p.access_granted,p.payment_status
                     FROM group_lessons gl JOIN group_lesson_participants p ON p.lesson_id=gl.id
                     WHERE gl.id=? AND p.user_id=?""",(lid,uid)).fetchone(); c.close()
    if not row: raise PermissionError("group_lesson_access_denied")
    visible=row["status"]=="STARTED" and row["admission_status"]=="ADMITTED" and int(row["access_granted"] or 0)==1
    return {"lesson_id":lid,"lesson_status":row["status"],"admission_status":row["admission_status"],"payment_status":row["payment_status"],"links_visible":visible,"board_url":row["board_url"] if visible else None,"telemost_join_url":row["telemost_join_url"] if visible else None}


def cancel_started_or_planned_lesson(lesson_id,reason="teacher_cancelled"):
    ensure_schema(); lid=int(lesson_id); c=database.connect(); row=c.execute("SELECT status FROM group_lessons WHERE id=?",(lid,)).fetchone()
    if not row:
        c.close(); raise ValueError("group_lesson_not_found")
    c.execute("UPDATE group_lessons SET status='CANCELLED',cancelled_reason=?,updated_at=? WHERE id=?",(str(reason)[:500],_now(),lid))
    c.execute("UPDATE group_lesson_participants SET access_granted=0,updated_at=? WHERE lesson_id=?",(_now(),lid)); c.commit(); c.close()
    # If a package place was reserved at start, cancellation returns it.
    group_finance.refund_subscription_for_lesson(lid)
    return {"status":"cancelled","lesson_id":lid}
