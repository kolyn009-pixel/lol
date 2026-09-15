"""Teacher-controlled access lifecycle for concrete group lessons.

Telemost access is teacher-controlled. The group board is a persistent learning
resource and remains available to group members independently from lesson start.
Payment is advisory and never grants or revokes access by itself.

`started_at` is the factual lesson timer start. Opening entry does not set it;
the first admitted student who presses "Join" does.
"""
from __future__ import annotations

import database
from web_backend import group_lessons, group_finance

VALID_DECISIONS={"PENDING","ADMITTED","EXCLUDED"}
VALID_RSVP={"UNKNOWN","GOING","MAYBE","NOT_GOING"}
FINAL_LESSON_STATES={"COMPLETED","CANCELLED","QUORUM_FAILED"}


def _now(): return database.now_iso()


def ensure_schema():
    group_finance.ensure_schema(); c=database.connect()
    cols={r[1] for r in c.execute("PRAGMA table_info(group_lesson_participants)").fetchall()}
    if "admission_status" not in cols:c.execute("ALTER TABLE group_lesson_participants ADD COLUMN admission_status TEXT NOT NULL DEFAULT 'PENDING'")
    if "admission_decided_at" not in cols:c.execute("ALTER TABLE group_lesson_participants ADD COLUMN admission_decided_at TEXT")
    if "admission_decided_by" not in cols:c.execute("ALTER TABLE group_lesson_participants ADD COLUMN admission_decided_by INTEGER")
    if "financial_attention" not in cols:c.execute("ALTER TABLE group_lesson_participants ADD COLUMN financial_attention INTEGER NOT NULL DEFAULT 0")
    if "rsvp_status" not in cols:c.execute("ALTER TABLE group_lesson_participants ADD COLUMN rsvp_status TEXT NOT NULL DEFAULT 'UNKNOWN'")
    if "rsvp_at" not in cols:c.execute("ALTER TABLE group_lesson_participants ADD COLUMN rsvp_at TEXT")
    lcols={r[1] for r in c.execute("PRAGMA table_info(group_lessons)").fetchall()}
    if "started_at" not in lcols:c.execute("ALTER TABLE group_lessons ADD COLUMN started_at TEXT")
    if "started_by" not in lcols:c.execute("ALTER TABLE group_lessons ADD COLUMN started_by INTEGER")
    c.execute("CREATE INDEX IF NOT EXISTS idx_group_admission ON group_lesson_participants(lesson_id,admission_status,financial_attention)");c.execute("CREATE INDEX IF NOT EXISTS idx_group_rsvp ON group_lesson_participants(lesson_id,rsvp_status,rsvp_at)");c.commit();c.close()


def refresh_financial_flags(lesson_id):
    ensure_schema(); lid=int(lesson_id); c=database.connect(); rows=c.execute("SELECT user_id,rsvp_status FROM group_lesson_participants WHERE lesson_id=? AND attendance_status='EXPECTED'",(lid,)).fetchall(); c.close(); out=[]
    for row in rows:
        uid=int(row["user_id"])
        if str(row["rsvp_status"] or "UNKNOWN").upper()=="NOT_GOING":
            state={"status":"NOT_CHARGED","covered":True,"reason":"student_not_going"};attention=0
        else:
            state=group_finance.financial_status_for_lesson(lid,uid);attention=0 if state["covered"] else 1
        c=database.connect(); c.execute("UPDATE group_lesson_participants SET payment_status=?,financial_attention=?,updated_at=? WHERE lesson_id=? AND user_id=?",(state["status"],attention,_now(),lid,uid)); c.commit(); c.close(); out.append({"user_id":uid,**state,"financial_attention":bool(attention)})
    return out


def teacher_start_preview(lesson_id):
    ensure_schema(); lid=int(lesson_id); refresh_financial_flags(lid); c=database.connect(); lesson=c.execute("SELECT gl.*,g.name AS group_name,g.min_attendees FROM group_lessons gl JOIN study_groups g ON g.id=gl.group_id WHERE gl.id=?",(lid,)).fetchone()
    if not lesson:c.close(); raise ValueError("group_lesson_not_found")
    rows=c.execute("""SELECT p.*,u.name FROM group_lesson_participants p JOIN users u ON u.id=p.user_id WHERE p.lesson_id=? AND p.attendance_status='EXPECTED' ORDER BY CASE p.rsvp_status WHEN 'GOING' THEN 0 WHEN 'MAYBE' THEN 1 WHEN 'UNKNOWN' THEN 2 ELSE 3 END,u.name COLLATE NOCASE""",(lid,)).fetchall(); c.close(); participants=[dict(r) for r in rows]
    chargeable=[p for p in participants if str(p.get("rsvp_status") or "UNKNOWN").upper()!="NOT_GOING"]
    return {"lesson":dict(lesson),"participants":participants,"unresolved":[p for p in chargeable if p["admission_status"]=="PENDING"],"unpaid_attention":[p for p in chargeable if int(p["financial_attention"] or 0)==1],"admitted_count":sum(1 for p in chargeable if p["admission_status"]=="ADMITTED"),"not_charged_user_ids":[int(p["user_id"]) for p in participants if str(p.get("rsvp_status") or "").upper()=="NOT_GOING"],"rsvp":{"going":sum(1 for p in participants if p.get("rsvp_status")=="GOING"),"maybe":sum(1 for p in participants if p.get("rsvp_status")=="MAYBE"),"not_going":sum(1 for p in participants if p.get("rsvp_status")=="NOT_GOING"),"unknown":sum(1 for p in participants if p.get("rsvp_status") in {None,"UNKNOWN"})}}


def set_student_rsvp(lesson_id,user_id,status):
    ensure_schema();lid=int(lesson_id);uid=int(user_id);status=str(status or "").upper()
    if status not in VALID_RSVP:raise ValueError("invalid_rsvp_status")
    c=database.connect();lesson=c.execute("SELECT status FROM group_lessons WHERE id=?",(lid,)).fetchone()
    if not lesson:c.close();raise ValueError("group_lesson_not_found")
    current=str(lesson["status"] or "").upper()
    if current in FINAL_LESSON_STATES or current=="STARTED":c.close();raise ValueError("group_lesson_rsvp_closed")
    now=_now();cur=c.execute("UPDATE group_lesson_participants SET rsvp_status=?,rsvp_at=?,payment_status=CASE WHEN ?='NOT_GOING' THEN 'NOT_CHARGED' ELSE payment_status END,financial_attention=CASE WHEN ?='NOT_GOING' THEN 0 ELSE financial_attention END,updated_at=? WHERE lesson_id=? AND user_id=?",(status,now,status,status,now,lid,uid));c.commit();c.close()
    if not cur.rowcount:raise PermissionError("group_lesson_access_denied")
    return {"status":"ok","lesson_id":lid,"user_id":uid,"rsvp_status":status,"rsvp_at":now,"will_be_charged":status!="NOT_GOING"}


def decide_admission(lesson_id,user_id,decision,teacher_id):
    ensure_schema(); lid=int(lesson_id); uid=int(user_id); decision=str(decision or "").upper()
    if decision not in {"ADMITTED","EXCLUDED"}: raise ValueError("invalid_admission_decision")
    c=database.connect(); lesson=c.execute("SELECT status FROM group_lessons WHERE id=?",(lid,)).fetchone()
    if not lesson:c.close(); raise ValueError("group_lesson_not_found")
    if lesson["status"] in FINAL_LESSON_STATES or lesson["status"]=="STARTED":c.close(); raise ValueError("group_lesson_admission_locked")
    cur=c.execute("""UPDATE group_lesson_participants SET admission_status=?,admission_decided_at=?,admission_decided_by=?,access_granted=0,updated_at=? WHERE lesson_id=? AND user_id=? AND attendance_status='EXPECTED'""",(decision,_now(),int(teacher_id),_now(),lid,uid)); c.commit(); c.close()
    if not cur.rowcount: raise ValueError("group_lesson_participant_not_found")
    return {"status":"ok","lesson_id":lid,"user_id":uid,"admission_status":decision}


def start_group_lesson(lesson_id,teacher_id):
    ensure_schema(); lid=int(lesson_id); preview=teacher_start_preview(lid); lesson=preview["lesson"]
    if lesson["status"]=="STARTED": return {"status":"already_open","lesson_id":lid,"participants":preview["participants"],"started_at":lesson.get("started_at")}
    if lesson["status"] in FINAL_LESSON_STATES: raise ValueError("group_lesson_not_startable")
    if preview["unresolved"]: raise ValueError("group_lesson_has_unresolved_admissions")
    admitted=[p for p in preview["participants"] if p["admission_status"]=="ADMITTED" and str(p.get("rsvp_status") or "UNKNOWN").upper()!="NOT_GOING"]; minimum=max(2,int(lesson["min_attendees"] or 2))
    if len(admitted)<minimum: raise ValueError("group_lesson_quorum_not_met")
    admitted_ids=[int(p["user_id"]) for p in admitted];now=_now(); c=database.connect(); c.execute("UPDATE group_lessons SET status='STARTED',started_by=?,updated_at=? WHERE id=?",(int(teacher_id),now,lid)); c.execute("UPDATE group_lesson_participants SET access_granted=CASE WHEN admission_status='ADMITTED' AND COALESCE(rsvp_status,'UNKNOWN')<>'NOT_GOING' THEN 1 ELSE 0 END,updated_at=? WHERE lesson_id=?",(now,lid)); c.commit(); c.close()
    reservations=[]
    for p in admitted:
        uid=int(p["user_id"]); fin=group_finance.financial_status_for_lesson(lid,uid)
        if fin["status"]=="COVERED":
            try:reservations.append({"user_id":uid,**group_finance.reserve_subscription_for_lesson(lid,uid)})
            except ValueError:pass
    return {"status":"opened","lesson_id":lid,"started_at":None,"admitted_user_ids":admitted_ids,"not_charged_user_ids":preview.get("not_charged_user_ids",[]),"reservations":reservations}


def mark_actual_start(lesson_id,user_id):
    ensure_schema();lid=int(lesson_id);uid=int(user_id);now=_now();c=database.connect()
    row=c.execute("SELECT gl.status,gl.started_at,p.admission_status,p.access_granted FROM group_lessons gl JOIN group_lesson_participants p ON p.lesson_id=gl.id WHERE gl.id=? AND p.user_id=?",(lid,uid)).fetchone()
    if not row:c.close();raise PermissionError("group_lesson_access_denied")
    if row["status"]!="STARTED" or row["admission_status"]!="ADMITTED" or int(row["access_granted"] or 0)!=1:c.close();raise PermissionError("group_lesson_not_open")
    started=row["started_at"]
    if not started:
        c.execute("UPDATE group_lessons SET started_at=?,updated_at=? WHERE id=? AND started_at IS NULL",(now,now,lid));c.commit();fresh=c.execute("SELECT started_at FROM group_lessons WHERE id=?",(lid,)).fetchone();started=fresh["started_at"] if fresh else now
    c.close();return started


def student_lesson_access(lesson_id,user_id):
    ensure_schema(); lid=int(lesson_id); uid=int(user_id); c=database.connect()
    row=c.execute("""SELECT gl.status,gl.started_at,gl.board_url,gl.telemost_join_url,p.admission_status,p.access_granted,p.payment_status,p.rsvp_status,p.rsvp_at,m.status AS membership_status FROM group_lessons gl JOIN group_lesson_participants p ON p.lesson_id=gl.id LEFT JOIN group_members m ON m.group_id=gl.group_id AND m.user_id=p.user_id WHERE gl.id=? AND p.user_id=?""",(lid,uid)).fetchone(); c.close()
    if not row: raise PermissionError("group_lesson_access_denied")
    member=str(row["membership_status"] or "").upper() in {"ACTIVE","PAUSED"}
    telemost_visible=row["status"]=="STARTED" and row["admission_status"]=="ADMITTED" and str(row["rsvp_status"] or "UNKNOWN").upper()!="NOT_GOING" and int(row["access_granted"] or 0)==1
    return {"lesson_id":lid,"lesson_status":row["status"],"started_at":row["started_at"],"admission_status":row["admission_status"],"payment_status":row["payment_status"],"rsvp_status":row["rsvp_status"],"rsvp_at":row["rsvp_at"],"links_visible":telemost_visible,"board_visible":member,"board_url":row["board_url"] if member else None,"telemost_join_url":row["telemost_join_url"] if telemost_visible else None}


def cancel_started_or_planned_lesson(lesson_id,reason="teacher_cancelled"):
    ensure_schema(); lid=int(lesson_id); c=database.connect(); row=c.execute("SELECT status FROM group_lessons WHERE id=?",(lid,)).fetchone()
    if not row:c.close(); raise ValueError("group_lesson_not_found")
    c.execute("UPDATE group_lessons SET status='CANCELLED',cancelled_reason=?,updated_at=? WHERE id=?",(str(reason)[:500],_now(),lid)); c.execute("UPDATE group_lesson_participants SET access_granted=0,updated_at=? WHERE lesson_id=?",(_now(),lid)); c.commit(); c.close(); group_finance.refund_subscription_for_lesson(lid); return {"status":"cancelled","lesson_id":lid}
