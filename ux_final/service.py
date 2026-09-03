from __future__ import annotations
from datetime import datetime
import database
from . import schema

ACTIONS = {
 'inbox': ('📥 Входящие','admin_inbox_all'),
 'messages': ('💬 Сообщения','admin_student_messages'),
 'today': ('🌅 Что важно сегодня','crm_today'),
 'search': ('🔎 Поиск','crm_search'),
 'students': ('👥 Ученики','admin_students'),
 'book': ('➕ Записать','admin_manual_lesson'),
 'lessons': ('📚 Занятия','admin_lessons'),
 'schedule': ('⚙️ Расписание','admin_schedule'),
 'windows': ('📢 Свободные окна','admin_free_windows'),
 'stats': ('📊 Статистика','admin_statistics'),
 'prices': ('💰 Цены','admin_prices'),
 'broadcast': ('📣 Рассылка','crm_broadcast'),
 'final': ('🚀 Центр управления','ff_main'),
 'system': ('🛡 Система','core_main'),
 'contact': ('👨‍🏫 Моя информация','admin_contact'),
 'parents': ('👨‍👩‍👧 Родители','admin_parents'),
 'paymethods': ('💳 Способы оплаты','admin_payment_methods'),
 'swaps': ('🔄 Переносы / обмены','ff_swap_admin'),
 'adelia_broadcast': ('📣 Рассылка с Аделией','ac_broadcast_start'),
 'adelia_post': ('💜 Пост с Аделией','ac_channel_start'),
}

def favorites(admin_id:int):
    schema.ensure_defaults(admin_id); c=database.connect()
    try:
        rows=c.execute('SELECT action_code FROM admin_favorites WHERE admin_id=? ORDER BY position,action_code',(int(admin_id),)).fetchall()
        return [r['action_code'] for r in rows if r['action_code'] in ACTIONS]
    finally:c.close()

def toggle(admin_id:int,code:str):
    if code not in ACTIONS:return False
    schema.initialize(); c=database.connect()
    try:
        r=c.execute('SELECT 1 FROM admin_favorites WHERE admin_id=? AND action_code=?',(int(admin_id),code)).fetchone()
        if r:
            c.execute('DELETE FROM admin_favorites WHERE admin_id=? AND action_code=?',(int(admin_id),code)); state=False
        else:
            pos=c.execute('SELECT COALESCE(MAX(position),-1)+1 FROM admin_favorites WHERE admin_id=?',(int(admin_id),)).fetchone()[0]
            c.execute('INSERT INTO admin_favorites(admin_id,action_code,position,created_at) VALUES(?,?,?,?)',(int(admin_id),code,int(pos),datetime.now().isoformat(timespec='seconds'))); state=True
        c.commit(); return state
    finally:c.close()

def learning_chain(user_id:int):
    c=database.connect(); uid=int(user_id)
    try:
        user=c.execute('SELECT name FROM users WHERE id=?',(uid,)).fetchone()
        upcoming=c.execute("SELECT id,start_time,study_goal,subject,duration_minutes FROM lessons WHERE user_id=? AND cancelled_at IS NULL AND finished_at IS NULL AND datetime(start_time)>=datetime('now') ORDER BY datetime(start_time) LIMIT 1",(uid,)).fetchone()
        hw=None
        try: hw=c.execute("SELECT id,title,status,deadline FROM homework WHERE user_id=? AND status IN ('ASSIGNED','REVISION','SUBMITTED','WAITING_REVIEW') ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
        except Exception: pass
        mock=None
        try: mock=c.execute("SELECT id,title,test_score,status,subject,exam_type FROM mock_tests WHERE user_id=? ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
        except Exception: pass
        topics=[]
        try:
            topics=c.execute("""SELECT t.topic,p.status,p.mastery,p.note FROM student_topic_progress p JOIN learning_topics t ON t.id=p.topic_id WHERE p.user_id=? ORDER BY CASE p.status WHEN 'REVIEW' THEN 0 WHEN 'LEARNING' THEN 1 ELSE 2 END, p.mastery ASC, p.updated_at DESC LIMIT 5""",(uid,)).fetchall()
        except Exception: pass
        return {'name':user['name'] if user else str(uid),'upcoming':upcoming,'homework':hw,'mock':mock,'topics':topics}
    finally:c.close()


def mark_recent_student(admin_id:int, student_id:int):
    schema.initialize(); c=database.connect()
    try:
        c.execute("INSERT INTO admin_recent_students(admin_id,student_id,opened_at) VALUES(?,?,?) ON CONFLICT(admin_id,student_id) DO UPDATE SET opened_at=excluded.opened_at",(int(admin_id),int(student_id),datetime.now().isoformat(timespec='seconds')))
        c.commit()
    finally:c.close()

def recent_students(admin_id:int, limit:int=5):
    schema.initialize(); c=database.connect()
    try:return c.execute("SELECT u.id,u.name,u.grade,u.active FROM admin_recent_students r JOIN users u ON u.id=r.student_id WHERE r.admin_id=? ORDER BY r.opened_at DESC LIMIT ?",(int(admin_id),int(limit))).fetchall()
    finally:c.close()

def pinned_students(admin_id:int, limit:int=10):
    schema.initialize(); c=database.connect()
    try:return c.execute("SELECT u.id,u.name,u.grade,u.active FROM admin_pinned_students p JOIN users u ON u.id=p.student_id WHERE p.admin_id=? ORDER BY p.created_at DESC LIMIT ?",(int(admin_id),int(limit))).fetchall()
    finally:c.close()

def is_student_pinned(admin_id:int, student_id:int):
    schema.initialize(); c=database.connect()
    try:return bool(c.execute('SELECT 1 FROM admin_pinned_students WHERE admin_id=? AND student_id=?',(int(admin_id),int(student_id))).fetchone())
    finally:c.close()

def toggle_student_pin(admin_id:int, student_id:int):
    schema.initialize(); c=database.connect()
    try:
        row=c.execute('SELECT 1 FROM admin_pinned_students WHERE admin_id=? AND student_id=?',(int(admin_id),int(student_id))).fetchone()
        if row:c.execute('DELETE FROM admin_pinned_students WHERE admin_id=? AND student_id=?',(int(admin_id),int(student_id))); state=False
        else:c.execute('INSERT INTO admin_pinned_students(admin_id,student_id,created_at) VALUES(?,?,?)',(int(admin_id),int(student_id),datetime.now().isoformat(timespec='seconds'))); state=True
        c.commit(); return state
    finally:c.close()
