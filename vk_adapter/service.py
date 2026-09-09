from __future__ import annotations

from datetime import datetime

import database
import education_profile
from automation import messaging
from core import event_center
from core import homework_channel_ui
from crm_plus import service as crm_service
from formula_library import FORMULA_LIBRARY
from web_backend import unified_messaging

from . import schema

SUBJECT_NAMES = {"PHYSICS": "Физика", "CHEMISTRY": "Химия"}
GOAL_NAMES = {"SCHOOL":"Повышение успеваемости","OGE":"Подготовка к ОГЭ","EGE":"Подготовка к ЕГЭ","OLYMPIAD":"Олимпиадная подготовка"}


def linked_user(vk_user_id):
    uid=schema.get_user_id("VK",str(vk_user_id));return database.get_user(uid) if uid else None

def vk_peer_for_user(user_id):
    c=database.connect()
    try:
        r=c.execute("SELECT external_id FROM channel_identities WHERE user_id=? AND channel='VK' AND enabled=1 LIMIT 1",(int(user_id),)).fetchone();return int(r["external_id"]) if r else None
    finally:c.close()
def _row_value(row,*names,default=None):
    if row is None:return default
    keys=set(row.keys()) if hasattr(row,"keys") else set()
    for n in names:
        if n in keys and row[n] not in (None,""):return row[n]
    return default
def _fmt_dt(raw):
    if not raw:return ""
    try:return datetime.fromisoformat(str(raw)).strftime("%d.%m в %H:%M")
    except Exception:return str(raw)
def upcoming_text(user_id,limit=5):
    rows=list(database.get_upcoming_lessons(int(user_id)))[:int(limit)]
    if not rows:return "📅 Ближайших занятий пока нет."
    lines=["📅 МОИ ЗАНЯТИЯ",""]
    for r in rows:
        s=str(_row_value(r,"subject",default="") or "").upper();sn=SUBJECT_NAMES.get(s,s or "Занятие");p=str(_row_value(r,"payment_status",default="") or "")
        pl={"PAID":"✅ оплачено","FREE":"🎁 бесплатно","AWAITING_PAYMENT":"💳 ожидает оплаты","RESERVED_BALANCE":"🎟 абонемент"}.get(p,"");lines.append(f"• {_fmt_dt(_row_value(r,'start_time'))} — {sn}"+(f" · {pl}" if pl else ""))
    return "\n".join(lines)
def homework_text(user_id,limit=8):
    return homework_channel_ui.list_text(int(user_id),int(limit))
def homework_detail(user_id,homework_id):
    return homework_channel_ui.detail(int(user_id),int(homework_id))
def homework_items(user_id,limit=8):
    return homework_channel_ui.list_items(int(user_id),int(limit))
def study_text(user_id):
    u=database.get_user(int(user_id))
    if not u:return "📚 Профиль ученика не найден."
    c=database.connect()
    try:programs=c.execute("SELECT study_goal,subject,custom_hourly_rate,is_primary FROM student_programs WHERE user_id=? AND active=1 ORDER BY is_primary DESC,id",(int(user_id),)).fetchall()
    finally:c.close()
    lines=["📚 МОЯ УЧЁБА","",f"👤 {u['name']} · {education_profile.label(u)}"]
    if programs:
        lines += ["","Направления:"]
        for r in programs:lines.append(f"• {SUBJECT_NAMES.get(str(r['subject'] or ''),str(r['subject'] or ''))} · {GOAL_NAMES.get(str(r['study_goal'] or ''),str(r['study_goal'] or ''))}"+(" ⭐" if r['is_primary'] else ""))
    else:lines += ["",f"• {SUBJECT_NAMES.get(str(u['main_subject'] or ''),str(u['main_subject'] or ''))} · {GOAL_NAMES.get(str(u['study_goal'] or ''),str(u['study_goal'] or ''))}"]
    try:lines += ["",f"📝 Активных ДЗ: {len(homework_channel_ui.list_items(int(user_id),100))}"]
    except Exception:pass
    lines.append(f"📅 Ближайших занятий: {len(list(database.get_upcoming_lessons(int(user_id))))}");return "\n".join(lines)
def student_grade(user_id):
    profile=education_profile.get(int(user_id))
    if profile['type']=='COLLEGE':return None
    return profile['level']
def formula_grades(user_id):
    return education_profile.formula_grades(int(user_id),FORMULA_LIBRARY)
def formula_subjects(grade):return [(key,SUBJECT_NAMES.get(key,key)) for key in FORMULA_LIBRARY.get(int(grade),{}).keys()]
def formula_topics(grade,subject):return [(key,item.get("title",key)) for key,item in FORMULA_LIBRARY.get(int(grade),{}).get(str(subject),{}).items()]
def formula_topic(grade,subject,topic):
    item=FORMULA_LIBRARY.get(int(grade),{}).get(str(subject),{}).get(str(topic));return str(item.get("text") or item.get("title")) if item else None
def formulas_text(user_id):
    profile=education_profile.get(int(user_id))
    if profile['type']=='COLLEGE':return f"🧮 ФОРМУЛЫ И СПРАВОЧНИК\n\n🎓 {profile['label']}\nДоступны все школьные разделы. Сначала показываю старшие классы 👇"
    return "🧮 ФОРМУЛЫ И СПРАВОЧНИК\n\nВыбери класс. Твой класс показан первым 👇" if student_grade(user_id) in FORMULA_LIBRARY else "🧮 ФОРМУЛЫ И СПРАВОЧНИК\n\nВыбери класс 👇"
def formula_topic_text(user_id,query):
    q=str(query or "").strip().lower()
    if not q:return None
    current=student_grade(user_id);libs=[]
    if current in FORMULA_LIBRARY:libs.append(FORMULA_LIBRARY[current])
    libs += [lib for g,lib in FORMULA_LIBRARY.items() if g!=current]
    for lib in libs:
        for topics in lib.values():
            for item in topics.values():
                title=str(item.get("title") or "")
                if q in title.lower() or title.lower() in q:return str(item.get("text") or title)
    return None
def board_text(user_id):
    u=database.get_user(int(user_id));url=_row_value(u,"board_url")
    return f"🖥 ДОСКА\n\nОткрывай рабочую доску:\n{url}" if url else "🖥 Ссылка на доску пока не добавлена. Когда преподаватель сохранит её, она появится здесь."
def more_text(user_id):
    u=database.get_user(int(user_id))
    if not u:return "⚙️ Профиль не найден."
    c=database.connect()
    try:unpaid=c.execute("SELECT COUNT(*) AS n FROM lessons WHERE user_id=? AND lesson_status='CONFIRMED' AND payment_status='AWAITING_PAYMENT' AND cancelled_at IS NULL",(int(user_id),)).fetchone()["n"]
    finally:c.close()
    return f"⚙️ ЕЩЁ\n\n👤 {u['name']} · {education_profile.label(u)}\n💳 Занятий ожидают оплаты: {int(unpaid or 0)}\n🔗 VK подключён к общей карточке TutorBot."
def message_history_text(user_id,limit=12):
    unified_messaging.import_legacy();conv=unified_messaging.conversation(int(user_id),'STUDENT',None);rows=unified_messaging.history(conv['id'],int(limit))
    if not rows:return "💬 Переписки с преподавателем пока нет."
    lines=["💬 ПРЕПОДАВАТЕЛЬ",""]
    for r in reversed(rows):lines.append(f"{'👨‍🏫' if r['direction']=='OUT' else '👤'} {_fmt_dt(r['created_at'])}\n{r['body']}")
    return "\n\n".join(lines)[-3500:]
def submit_teacher_message(user_id,text,source_vk_id=None):
    u=database.get_user(int(user_id));body=str(text or "").strip()
    if not u or not body:return False,"Пустое сообщение не отправлено."
    accepting,deliver_at=crm_service.inbound_delivery_state();status="OPEN" if accepting else "QUEUED";iid=messaging.create_inbox(body,int(u["telegram_id"] or 0),student_id=int(user_id),subject="Сообщение от ученика из VK",status=status)
    crm_id=crm_service.log_message(int(user_id),"IN",body,None,"TEACHER","DELIVERED" if accepting else "QUEUED",None if accepting else deliver_at.isoformat(timespec="seconds"),inbox_id=iid)
    unified_messaging.record_message(int(user_id),'IN',body,participant_type='STUDENT',sender_type='STUDENT',sender_id=int(user_id),origin_channel='VK',status='DELIVERED' if accepting else 'QUEUED',legacy_source='crm_student_messages',legacy_id=crm_id)
    event_center.push("TEACHER_INBOX",f"Сообщение из VK от {u['name']}",body[:500],priority="ACTION",entity_type="teacher_inbox",entity_id=iid,dedupe_key=f"inbox:{iid}")
    try:
        from . import app as vk_app
        for peer in schema.get_admin_external_ids("VK"):vk_app.send(peer,f"💬 Новое сообщение от {u['name']}\n\n{body}",linked=True,mode="teacher")
    except Exception as exc:print("VK TEACHER MESSAGE ALERT ERROR:",repr(exc))
    return (True,"✅ Сообщение сохранено в диалоге с преподавателем.") if accepting else (True,f"🌙 Сообщение сохранено. Плановая доставка: {_fmt_dt(deliver_at.isoformat())}")
def submit_booking_request(user_id,text):
    u=database.get_user(int(user_id));body=str(text or "").strip()
    if not u or not body:return False,"Напиши желаемые день и время одним сообщением."
    iid=messaging.create_inbox(body,int(u["telegram_id"] or 0),student_id=int(user_id),subject="Запрос на запись из VK",status="OPEN")
    event_center.push("VK_BOOKING_REQUEST",f"Запрос на запись из VK · {u['name']}",body[:500],priority="ACTION",entity_type="teacher_inbox",entity_id=iid,dedupe_key=f"vk_booking:{iid}")
    try:
        from . import app as vk_app
        for peer in schema.get_admin_external_ids("VK"):vk_app.send(peer,f"➕ Запрос на запись от {u['name']}\n\n{body}",linked=True,mode="teacher")
    except Exception as exc:print("VK TEACHER BOOKING ALERT ERROR:",repr(exc))
    return True,"✅ Запрос на запись отправлен преподавателю."
def identity_status(vk_user_id):
    u=linked_user(vk_user_id);return {"user_id":int(u["id"]),"name":u["name"],"grade":u["grade"],"education":education_profile.label(u),"active":bool(u["active"])} if u else None