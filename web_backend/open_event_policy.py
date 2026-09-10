"""Business rules for standalone paid learning events.

Events are independent from recurring study groups. A group may be selected as
an audience rule by event_campaign, but group membership never auto-registers a
student and never consumes a group or individual package.
"""
from __future__ import annotations
import database
from web_backend import group_portal

VALID_EVENT_TYPES={"MOCK_EXAM","SEMINAR"}

def ensure_schema():
    group_portal.ensure_schema();c=database.connect();cols={r[1] for r in c.execute("PRAGMA table_info(open_learning_events)").fetchall()}
    if "topic" not in cols:c.execute("ALTER TABLE open_learning_events ADD COLUMN topic TEXT")
    if "payment_mode" not in cols:c.execute("ALTER TABLE open_learning_events ADD COLUMN payment_mode TEXT NOT NULL DEFAULT 'SEPARATE'")
    if "allow_package_coverage" not in cols:c.execute("ALTER TABLE open_learning_events ADD COLUMN allow_package_coverage INTEGER NOT NULL DEFAULT 0")
    if "assignment_mode" not in cols:c.execute("ALTER TABLE open_learning_events ADD COLUMN assignment_mode TEXT NOT NULL DEFAULT 'AUDIENCE'")
    c.execute("""CREATE TABLE IF NOT EXISTS open_event_student_targets(event_id INTEGER NOT NULL,user_id INTEGER NOT NULL,assigned_at TEXT NOT NULL,assigned_by INTEGER,PRIMARY KEY(event_id,user_id),FOREIGN KEY(event_id) REFERENCES open_learning_events(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_open_event_targets_user ON open_event_student_targets(user_id,event_id)");c.commit();c.close()

def create_event(title,starts_at,duration_minutes,*,event_type,price_per_student,subject=None,topic=None,grade_min=None,grade_max=None,max_participants=None,registration_deadline=None,group_ids=None,student_ids=None,board_url=None,created_by=None):
    ensure_schema();kind=str(event_type or "").upper()
    if kind not in VALID_EVENT_TYPES:raise ValueError("invalid_open_event_type")
    price=int(price_per_student or 0)
    if price<0:raise ValueError("invalid_event_price")
    if kind=="MOCK_EXAM" and price<=0:raise ValueError("mock_exam_separate_price_required")
    clean_topic=str(topic or "").strip()[:300] or None
    if kind=="SEMINAR" and not clean_topic:raise ValueError("seminar_topic_required")
    result=group_portal.create_open_event(title,starts_at,duration_minutes,event_type=kind,subject=subject,grade_min=grade_min,grade_max=grade_max,price_per_student=price,max_participants=max_participants,registration_deadline=registration_deadline,group_ids=[],board_url=board_url,created_by=created_by)
    eid=int(result["event_id"]);c=database.connect();c.execute("UPDATE open_learning_events SET topic=?,payment_mode='SEPARATE',allow_package_coverage=0,assignment_mode='AUDIENCE',updated_at=? WHERE id=?",(clean_topic,database.now_iso(),eid))
    for uid in student_ids or []:c.execute("INSERT OR IGNORE INTO open_event_student_targets(event_id,user_id,assigned_at,assigned_by) VALUES(?,?,?,?)",(eid,int(uid),database.now_iso(),int(created_by) if created_by is not None else None))
    c.commit();c.close();return {**result,"event_type":kind,"payment_mode":"SEPARATE","price_per_student":price,"topic":clean_topic}

def assign_students(event_id,user_ids,teacher_id=None):
    ensure_schema();eid=int(event_id);ids=sorted({int(x) for x in (user_ids or [])});c=database.connect()
    if not c.execute("SELECT 1 FROM open_learning_events WHERE id=?",(eid,)).fetchone():c.close();raise ValueError("event_not_found")
    for uid in ids:
        if c.execute("SELECT 1 FROM users WHERE id=? AND active=1",(uid,)).fetchone():c.execute("INSERT OR IGNORE INTO open_event_student_targets(event_id,user_id,assigned_at,assigned_by) VALUES(?,?,?,?)",(eid,uid,database.now_iso(),int(teacher_id) if teacher_id is not None else None))
    c.commit();c.close();return {"status":"ok","event_id":eid,"target_user_ids":ids}

def assign_groups(event_id,group_ids):
    """Compatibility shim: groups are audience selectors, not event members."""
    ensure_schema();eid=int(event_id);c=database.connect()
    if not c.execute("SELECT 1 FROM open_learning_events WHERE id=?",(eid,)).fetchone():c.close();raise ValueError("event_not_found")
    c.close();return {"status":"ok","event_id":eid,"audience_group_ids":sorted({int(x) for x in (group_ids or [])}),"deprecated":True}

def eligible_student_ids(event_id):
    """Return explicit direct targets only; never materialize group membership."""
    ensure_schema();c=database.connect();rows=c.execute("SELECT user_id FROM open_event_student_targets WHERE event_id=?",(int(event_id),)).fetchall();c.close();return sorted({int(r["user_id"]) for r in rows})

def registration_payment_state(event_id):
    ensure_schema();c=database.connect();event=c.execute("SELECT event_type,price_per_student FROM open_learning_events WHERE id=?",(int(event_id),)).fetchone();c.close()
    if not event:raise ValueError("event_not_found")
    return {"event_type":event["event_type"],"price_per_student":int(event["price_per_student"] or 0),"payment_mode":"SEPARATE","allow_package_coverage":False,"must_pay_separately":int(event["price_per_student"] or 0)>0}
