"""Adelia lesson start/access integration with Yandex Telemost.

No meeting link is visible to a student before the teacher starts/opens the
lesson. Finishing/cancelling inside Adelia immediately hides the saved link;
Telemost itself is not claimed to be remotely terminated because its public
API does not expose that operation in our integration contract.
"""
from __future__ import annotations

import database
from integrations.telemost_lifecycle import ensure_individual_conference, create_conference
from web_backend import lesson_workspace, group_lesson_access, group_portal


def _now():
    return database.now_iso()


def start_individual(lesson_id):
    """Teacher start: create/reuse Telemost, start canonical lesson, open access."""
    lid=int(lesson_id)
    meeting=ensure_individual_conference(lid)
    if meeting.get("status") not in {"ok","disabled"}:
        raise RuntimeError("telemost_create_failed")
    started=lesson_workspace.start_lesson(lid)
    if started.get("status") != "ok":
        return {"status":started.get("status"),"lesson":started,"telemost":meeting}
    c=database.connect()
    c.execute("UPDATE lessons SET meeting_link_sent_at=COALESCE(meeting_link_sent_at,?),updated_at=? WHERE id=?",(_now(),_now(),lid))
    c.commit();c.close()
    return {"status":"started","lesson_id":lid,"lesson":started,"telemost":meeting}


def finish_individual(lesson_id,attendance_status="PRESENT",tutor_comment=None,mode="NOW"):
    lid=int(lesson_id)
    result=lesson_workspace.finish_lesson(lid,attendance_status,tutor_comment,mode)
    if result.get("status")=="ok":
        # Keep provider id/url for audit/reuse history, but close Adelia access.
        c=database.connect();c.execute("UPDATE lessons SET meeting_link_sent_at=NULL,updated_at=? WHERE id=?",(_now(),lid));c.commit();c.close()
    return result


def individual_student_access(lesson_id,user_id):
    lid=int(lesson_id);uid=int(user_id);c=database.connect()
    row=c.execute("""SELECT l.id,l.user_id,l.lesson_status,l.started_at,l.finished_at,l.meeting_link_sent_at,l.meeting_url,u.board_url
                     FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?""",(lid,)).fetchone();c.close()
    if not row or int(row["user_id"])!=uid:
        raise PermissionError("lesson_access_denied")
    visible=bool(row["started_at"] and row["meeting_link_sent_at"] and not row["finished_at"] and str(row["lesson_status"] or "").upper()=="IN_PROGRESS")
    return {"lesson_id":lid,"links_visible":visible,"meeting_url":row["meeting_url"] if visible else None,"board_url":row["board_url"] if visible else None,"lesson_status":row["lesson_status"]}


def start_group(lesson_id,teacher_id):
    """Resolve admissions first, then create one meeting for the whole group."""
    lid=int(lesson_id);preview=group_lesson_access.teacher_start_preview(lid)
    if preview["unresolved"]:
        raise ValueError("group_lesson_has_unresolved_admissions")
    admitted=[p for p in preview["participants"] if p["admission_status"]=="ADMITTED"]
    minimum=max(2,int(preview["lesson"]["min_attendees"] or 2))
    if len(admitted)<minimum:
        raise ValueError("group_lesson_quorum_not_met")
    c=database.connect();row=c.execute("SELECT telemost_conference_id,telemost_join_url FROM group_lessons WHERE id=?",(lid,)).fetchone();c.close()
    if row and row["telemost_conference_id"] and row["telemost_join_url"]:
        meeting={"status":"ok","conference_id":row["telemost_conference_id"],"join_url":row["telemost_join_url"],"reused":True}
    else:
        meeting=create_conference()
        if meeting.get("status")=="ok":
            c=database.connect();c.execute("UPDATE group_lessons SET telemost_conference_id=?,telemost_join_url=?,updated_at=? WHERE id=?",(meeting["conference_id"],meeting["join_url"],_now(),lid));c.commit();c.close()
            meeting["reused"]=False
    result=group_lesson_access.start_group_lesson(lid,int(teacher_id))
    return {**result,"telemost":meeting}


def finish_group(lesson_id):
    """Close Adelia access after the group lesson is completed."""
    lid=int(lesson_id);c=database.connect();row=c.execute("SELECT status FROM group_lessons WHERE id=?",(lid,)).fetchone()
    if not row:
        c.close();raise ValueError("group_lesson_not_found")
    now=_now();c.execute("UPDATE group_lessons SET status='COMPLETED',updated_at=? WHERE id=?",(now,lid));c.execute("UPDATE group_lesson_participants SET access_granted=0,updated_at=? WHERE lesson_id=?",(now,lid));c.commit();c.close()
    return {"status":"completed","lesson_id":lid}


def start_open_event(event_id):
    """Create/reuse one meeting for an open mock exam/intensive."""
    eid=int(event_id);c=database.connect();row=c.execute("SELECT telemost_conference_id,telemost_join_url,board_url FROM open_learning_events WHERE id=?",(eid,)).fetchone();c.close()
    if not row:
        raise ValueError("event_not_found")
    if row["telemost_conference_id"] and row["telemost_join_url"]:
        meeting={"status":"ok","conference_id":row["telemost_conference_id"],"join_url":row["telemost_join_url"],"reused":True}
    else:
        meeting=create_conference()
        if meeting.get("status")=="ok":
            c=database.connect();c.execute("UPDATE open_learning_events SET telemost_conference_id=?,telemost_join_url=?,updated_at=? WHERE id=?",(meeting["conference_id"],meeting["join_url"],_now(),eid));c.commit();c.close();meeting["reused"]=False
    result=group_portal.start_open_event(eid,meeting.get("join_url"),row["board_url"])
    return {**result,"telemost":meeting}


def finish_open_event(event_id):
    eid=int(event_id);c=database.connect();row=c.execute("SELECT id FROM open_learning_events WHERE id=?",(eid,)).fetchone()
    if not row:
        c.close();raise ValueError("event_not_found")
    now=_now();c.execute("UPDATE open_learning_events SET status='COMPLETED',updated_at=? WHERE id=?",(now,eid));c.execute("UPDATE open_event_participants SET access_granted=0,updated_at=? WHERE event_id=?",(now,eid));c.commit();c.close();return {"status":"completed","event_id":eid}
