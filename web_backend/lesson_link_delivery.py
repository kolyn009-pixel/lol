"""Automatic lesson-link delivery for Telemost-backed lessons.

Teacher action opens entry. Paid/admitted students receive Telemost; an
individual student without payment receives a payment reminder instead. Board
access remains independent from payment. Delivery is idempotent per object and
user so repeated teacher actions do not spam students.
"""
from __future__ import annotations

import database
from web_backend import message_delivery

_PAID_ACCESS={"PAID","FREE","WAIVED","COVERED"}

def ensure_schema():
    c=database.connect();c.execute("""CREATE TABLE IF NOT EXISTS lesson_link_deliveries(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        object_type TEXT NOT NULL,
        object_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        sent_at TEXT NOT NULL,
        message_id INTEGER,
        UNIQUE(object_type,object_id,user_id)
    )""");c.execute("CREATE INDEX IF NOT EXISTS idx_lesson_link_delivery_user ON lesson_link_deliveries(user_id,sent_at)");c.commit();c.close()
def _already_sent(object_type,object_id,user_id):
    ensure_schema();c=database.connect();row=c.execute("SELECT id FROM lesson_link_deliveries WHERE object_type=? AND object_id=? AND user_id=?",(str(object_type),int(object_id),int(user_id))).fetchone();c.close();return bool(row)
def _mark_sent(object_type,object_id,user_id,message_id=None):
    ensure_schema();c=database.connect();c.execute("INSERT OR IGNORE INTO lesson_link_deliveries(object_type,object_id,user_id,sent_at,message_id) VALUES(?,?,?,?,?)",(str(object_type),int(object_id),int(user_id),database.now_iso(),int(message_id) if message_id else None));c.commit();c.close()
def _text(title,meeting_url,board_url=None):
    parts=["🎥 Преподаватель открыл занятие","",str(title or "Занятие"),"","Можно подключаться к Телемосту:",str(meeting_url).strip()]
    if board_url:parts += ["","📝 Доска занятия:",str(board_url).strip()]
    parts += ["","Ссылки доступны, пока занятие открыто преподавателем."];return "\n".join(parts)
def _payment_text(title,board_url=None):
    parts=["💳 Преподаватель открыл занятие","",str(title or "Занятие"),"","Чтобы получить ссылку на Телемост, сначала оплатите занятие в личном кабинете Аделия."]
    if board_url:parts += ["","📝 Доска доступна независимо от оплаты:",str(board_url).strip()]
    parts += ["","После подтверждения оплаты доступ к занятию откроется автоматически."];return "\n".join(parts)

def _delivery_ok(result, channel):
    item=(result.get("deliveries") or {}).get(str(channel).lower()) or {}
    return str(item.get("status") or "").upper() in {"SENT","DELIVERED","READ"}

def _notify_teacher_vk(lesson_id,user_id,student_text,result,paid):
    """Confirm website lesson-link fanout to the teacher's linked VK account."""
    try:
        from vk_adapter.channel_delivery import send_teacher_vk
        user=database.get_user(int(user_id))
        name=str(user["name"] or "Ученик") if user else "Ученик"
        tg=_delivery_ok(result,"telegram");vk=_delivery_ok(result,"vk")
        headline="✅ ССЫЛКИ НА ЗАНЯТИЕ ОТПРАВЛЕНЫ" if paid else "💳 УЧЕНИКУ ОТПРАВЛЕНО НАПОМИНАНИЕ ОБ ОПЛАТЕ"
        parts=[headline,"",f"👤 {name}",f"Telegram: {'✅' if tg else '—'}",f"VK: {'✅' if vk else '—'}"]
        lesson=database.get_lesson(int(lesson_id))
        if paid and lesson and lesson["meeting_url"]:parts += ["","🎥 Телемост:",str(lesson["meeting_url"]).strip()]
        if user and user["board_url"]:parts += ["","📝 Доска:",str(user["board_url"]).strip()]
        send_teacher_vk("\n".join(parts))
    except Exception as exc:
        print("TEACHER VK LESSON DELIVERY CONFIRM ERROR:",repr(exc),flush=True)
def send_individual(lesson_id):
    lid=int(lesson_id);c=database.connect();row=c.execute("""SELECT l.id,l.user_id,l.subject,l.meeting_url,l.payment_status,l.is_trial,u.board_url FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?""",(lid,)).fetchone();c.close()
    if not row:return {"status":"skipped","reason":"lesson_missing"}
    uid=int(row["user_id"])
    if _already_sent("INDIVIDUAL",lid,uid):return {"status":"already_sent","user_id":uid}
    title={"PHYSICS":"Физика","CHEMISTRY":"Химия"}.get(str(row["subject"] or "").upper(),str(row["subject"] or "Занятие"));paid=str(row["payment_status"] or "").upper() in _PAID_ACCESS or bool(row["is_trial"])
    if paid:
        if not row["meeting_url"]:return {"status":"skipped","reason":"meeting_url_missing"}
        text=_text(title,row["meeting_url"],row["board_url"])
    else:text=_payment_text(title,row["board_url"])
    result=message_delivery.send_teacher_reply(uid,text,channels=['TELEGRAM','VK'])
    if result.get("status")=="ok":
        _mark_sent("INDIVIDUAL",lid,uid,result.get("message_id"))
        _notify_teacher_vk(lid, uid, text, result, paid)
    return {"user_id":uid,"access":"telemost" if paid else "payment_required",**result}
def send_group(lesson_id):
    lid=int(lesson_id);c=database.connect();lesson=c.execute("""SELECT gl.id,gl.telemost_join_url,gl.board_url,g.name FROM group_lessons gl JOIN study_groups g ON g.id=gl.group_id WHERE gl.id=?""",(lid,)).fetchone()
    if not lesson or not lesson["telemost_join_url"]:c.close();return {"status":"skipped","reason":"meeting_url_missing"}
    rows=c.execute("""SELECT p.user_id FROM group_lesson_participants p WHERE p.lesson_id=? AND p.admission_status='ADMITTED' AND p.access_granted=1""",(lid,)).fetchall();c.close();out=[]
    for r in rows:
        uid=int(r["user_id"])
        if _already_sent("GROUP",lid,uid):out.append({"user_id":uid,"status":"already_sent"});continue
        result=message_delivery.send_teacher_reply(uid,_text(f"Группа: {lesson['name']}",lesson["telemost_join_url"],lesson["board_url"]))
        if result.get("status")=="ok":_mark_sent("GROUP",lid,uid,result.get("message_id"));out.append({"user_id":uid,**result})
    return {"status":"ok","deliveries":out}
def send_open_event(event_id):
    eid=int(event_id);c=database.connect();event=c.execute("SELECT id,title,telemost_join_url,board_url FROM open_learning_events WHERE id=?",(eid,)).fetchone()
    if not event or not event["telemost_join_url"]:c.close();return {"status":"skipped","reason":"meeting_url_missing"}
    rows=c.execute("""SELECT user_id FROM open_event_participants WHERE event_id=? AND teacher_decision='APPROVED' AND access_granted=1 AND status='REGISTERED'""",(eid,)).fetchall();c.close();out=[]
    for r in rows:
        uid=int(r["user_id"])
        if _already_sent("OPEN_EVENT",eid,uid):out.append({"user_id":uid,"status":"already_sent"});continue
        result=message_delivery.send_teacher_reply(uid,_text(event["title"],event["telemost_join_url"],event["board_url"]))
        if result.get("status")=="ok":_mark_sent("OPEN_EVENT",eid,uid,result.get("message_id"));out.append({"user_id":uid,**result})
    return {"status":"ok","deliveries":out}
