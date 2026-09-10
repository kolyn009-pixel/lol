"""Automatic lesson-link delivery for Telemost-backed lessons.

Teacher action is only 'start lesson'. This module sends the generated Telemost
link (and board link when available) to the student's linked Telegram/VK
channels, while the web cabinet reads the same persisted access state.

Delivery is idempotent per lesson/event and user, so repeated start clicks do
not spam students.
"""
from __future__ import annotations

import database
from web_backend import message_delivery


def ensure_schema():
    c=database.connect()
    c.execute("""CREATE TABLE IF NOT EXISTS lesson_link_deliveries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_type TEXT NOT NULL,
        object_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        sent_at TEXT NOT NULL,
        message_id INTEGER,
        UNIQUE(object_type,object_id,user_id)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_lesson_link_delivery_user ON lesson_link_deliveries(user_id,sent_at)")
    c.commit();c.close()


def _already_sent(object_type,object_id,user_id):
    ensure_schema();c=database.connect();row=c.execute(
        "SELECT id FROM lesson_link_deliveries WHERE object_type=? AND object_id=? AND user_id=?",
        (str(object_type),int(object_id),int(user_id)),
    ).fetchone();c.close();return bool(row)


def _mark_sent(object_type,object_id,user_id,message_id=None):
    ensure_schema();c=database.connect();c.execute(
        "INSERT OR IGNORE INTO lesson_link_deliveries(object_type,object_id,user_id,sent_at,message_id) VALUES(?,?,?,?,?)",
        (str(object_type),int(object_id),int(user_id),database.now_iso(),int(message_id) if message_id else None),
    );c.commit();c.close()


def _text(title,meeting_url,board_url=None):
    parts=[
        "🎥 Занятие началось",
        "",
        str(title or "Занятие"),
        "",
        "Подключиться к Телемосту:",
        str(meeting_url).strip(),
    ]
    if board_url:
        parts += ["", "📝 Доска занятия:", str(board_url).strip()]
    parts += ["", "Ссылки доступны, пока занятие открыто преподавателем."]
    return "\n".join(parts)


def send_individual(lesson_id):
    lid=int(lesson_id);c=database.connect();row=c.execute(
        """SELECT l.id,l.user_id,l.subject,l.meeting_url,u.board_url
           FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?""",(lid,)
    ).fetchone();c.close()
    if not row or not row["meeting_url"]:return {"status":"skipped","reason":"meeting_url_missing"}
    uid=int(row["user_id"])
    if _already_sent("INDIVIDUAL",lid,uid):return {"status":"already_sent","user_id":uid}
    title={"PHYSICS":"Физика","CHEMISTRY":"Химия"}.get(str(row["subject"] or "").upper(),str(row["subject"] or "Занятие"))
    result=message_delivery.send_teacher_reply(uid,_text(title,row["meeting_url"],row["board_url"]))
    if result.get("status")=="ok":_mark_sent("INDIVIDUAL",lid,uid,result.get("message_id"))
    return {"user_id":uid,**result}


def send_group(lesson_id):
    lid=int(lesson_id);c=database.connect();lesson=c.execute(
        """SELECT gl.id,gl.telemost_join_url,gl.board_url,g.name
           FROM group_lessons gl JOIN study_groups g ON g.id=gl.group_id WHERE gl.id=?""",(lid,)
    ).fetchone()
    if not lesson or not lesson["telemost_join_url"]:c.close();return {"status":"skipped","reason":"meeting_url_missing"}
    rows=c.execute("""SELECT p.user_id FROM group_lesson_participants p
                      WHERE p.lesson_id=? AND p.admission_status='ADMITTED' AND p.access_granted=1""",(lid,)).fetchall();c.close()
    out=[]
    for r in rows:
        uid=int(r["user_id"])
        if _already_sent("GROUP",lid,uid):
            out.append({"user_id":uid,"status":"already_sent"});continue
        result=message_delivery.send_teacher_reply(uid,_text(f"Группа: {lesson['name']}",lesson["telemost_join_url"],lesson["board_url"]))
        if result.get("status")=="ok":_mark_sent("GROUP",lid,uid,result.get("message_id"))
        out.append({"user_id":uid,**result})
    return {"status":"ok","deliveries":out}


def send_open_event(event_id):
    eid=int(event_id);c=database.connect();event=c.execute(
        "SELECT id,title,telemost_join_url,board_url FROM open_learning_events WHERE id=?",(eid,)
    ).fetchone()
    if not event or not event["telemost_join_url"]:c.close();return {"status":"skipped","reason":"meeting_url_missing"}
    rows=c.execute("""SELECT user_id FROM open_event_participants
                      WHERE event_id=? AND teacher_decision='APPROVED' AND access_granted=1 AND status='REGISTERED'""",(eid,)).fetchall();c.close()
    out=[]
    for r in rows:
        uid=int(r["user_id"])
        if _already_sent("OPEN_EVENT",eid,uid):
            out.append({"user_id":uid,"status":"already_sent"});continue
        result=message_delivery.send_teacher_reply(uid,_text(event["title"],event["telemost_join_url"],event["board_url"]))
        if result.get("status")=="ok":_mark_sent("OPEN_EVENT",eid,uid,result.get("message_id"))
        out.append({"user_id":uid,**result})
    return {"status":"ok","deliveries":out}
