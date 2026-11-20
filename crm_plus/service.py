from __future__ import annotations
import json
from datetime import datetime,timedelta,time
from zoneinfo import ZoneInfo
import database
from core import minute_balance
from automation import messaging, student_history
from final_features import renewals, reports
from . import schema

GOAL_RU={'EGE':'ЕГЭ','OGE':'ОГЭ','OLYMPIAD':'Олимпиада','SCHOOL':'Школьная программа'}
SUBJ_RU={'PHYSICS':'Физика','CHEMISTRY':'Химия'}

STORAGE_TZ=ZoneInfo('Europe/Moscow')

def now():
    """Current moment as naive Moscow wall-clock.

    This is the storage convention of crm_* timestamps (created_at,
    scheduled_for, ...). It is NOT the teacher's local time: use
    teacher_tz()/to_local() for any time-of-day policy (quiet hours,
    reception hours).
    """
    return datetime.now(STORAGE_TZ).replace(tzinfo=None)

def teacher_tz():
    from core.lesson_time import teacher_timezone
    return teacher_timezone()

def to_local(dt):
    """Storage-naive (MSK) or aware datetime -> aware teacher-local datetime."""
    if dt.tzinfo is None: dt=dt.replace(tzinfo=STORAGE_TZ)
    return dt.astimezone(teacher_tz())

def to_storage(dt):
    """Aware datetime -> naive MSK storage value (naive input is returned as is)."""
    if dt is None or dt.tzinfo is None: return dt
    return dt.astimezone(STORAGE_TZ).replace(tzinfo=None)

def get_setting(key,default=None):
    schema.initialize(); c=database.connect(); r=c.execute('SELECT value FROM crm_settings WHERE key=?',(key,)).fetchone(); c.close(); return r['value'] if r else default

def set_setting(key,value,actor=None):
    schema.initialize(); c=database.connect(); c.execute('INSERT INTO crm_settings(key,value,updated_by,updated_at) VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(key,str(value),actor,now().isoformat(timespec='seconds'))); c.commit(); c.close()

def quiet_state(dt=None):
    # Quiet hours are configured in the teacher's local time (bot_timezone);
    # the returned target stays in the caller's convention (naive MSK storage).
    dt=dt or now(); naive=dt.tzinfo is None; local=to_local(dt)
    if get_setting('quiet_enabled','1')!='1': return False,None
    s=datetime.strptime(get_setting('quiet_start','22:00'),'%H:%M').time(); e=datetime.strptime(get_setting('quiet_end','09:00'),'%H:%M').time(); t=local.time()
    quiet=(t>=s or t<e) if s>e else (s<=t<e)
    if not quiet:return False,None
    target=datetime.combine(local.date(),e).replace(tzinfo=local.tzinfo)
    if s>e and t>=s: target+=timedelta(days=1)
    return True,(to_storage(target) if naive else target)



def reception_state(dt=None):
    """Return (accepting_now, next_delivery_datetime).

    Reception hours are independent from outgoing quiet hours. Messages are always
    stored immediately; outside reception hours only the admin notification waits.
    """
    dt=dt or now(); naive=dt.tzinfo is None; orig=dt
    if get_setting('reception_enabled','1')!='1':
        return True,orig
    dt=to_local(dt)
    back=(lambda x: to_storage(x) if naive else x)
    start=datetime.strptime(get_setting('reception_start','09:00'),'%H:%M').time()
    end=datetime.strptime(get_setting('reception_end','21:00'),'%H:%M').time()
    days={int(x) for x in (get_setting('reception_days','0,1,2,3,4,5,6') or '').split(',') if x.strip().isdigit()}
    if not days:
        days=set(range(7))
    def inside(day,t):
        if day not in days:return False
        if start<=end:return start<=t<end
        return t>=start or t<end
    if inside(dt.weekday(),dt.time()):
        return True,orig
    # Find the nearest next start of an enabled reception day (teacher-local).
    for offset in range(0,15):
        cand=datetime.combine(dt.date()+timedelta(days=offset),start).replace(tzinfo=dt.tzinfo)
        if cand.weekday() not in days:continue
        if cand>dt:return False,back(cand)
    return False,back(dt+timedelta(days=1))

def teacher_busy_until(dt=None):
    """Return end of the current/contiguous lesson block, or None.

    Lesson timestamps may be naive (schedule timezone) or carry an offset, so
    the comparison is done on aware datetimes in Python instead of SQLite
    datetime(), which silently converts offset values to UTC. The result is in
    the caller's convention: naive MSK storage for naive input.
    """
    from core.lesson_time import schedule_datetime
    dt=dt or now(); naive=dt.tzinfo is None
    moment=dt.replace(tzinfo=STORAGE_TZ) if naive else dt
    c=database.connect()
    try:
        # Prefilter by a generous textual window; exact check below.
        lo=(moment-timedelta(days=2)).astimezone(STORAGE_TZ).date().isoformat()
        rows=c.execute("SELECT start_time,end_time FROM lessons WHERE lesson_status='CONFIRMED' AND cancelled_at IS NULL AND end_time IS NOT NULL AND substr(end_time,1,10)>=?",(lo,)).fetchall()
    finally:c.close()
    spans=[]
    for r in rows:
        try:spans.append((schedule_datetime(r['start_time']),schedule_datetime(r['end_time'])))
        except Exception:continue
    spans.sort(key=lambda x:x[0])
    current=[e for st,e in spans if st<=moment<e]
    if not current:return None
    end=max(current)
    while True:
        nxt=[e for st,e in spans if st<=end<e and e>end]
        if not nxt:break
        end=max(nxt)
    return to_storage(end) if naive else end

def inbound_delivery_state(dt=None):
    dt=dt or now(); accepting,next_at=reception_state(dt)
    busy=teacher_busy_until(dt) if get_setting('lesson_dnd_enabled','1')=='1' else None
    if busy:
        accepting=False; next_at=max(next_at,busy) if next_at else busy
    return accepting,next_at

def reception_label():
    enabled=get_setting('reception_enabled','1')=='1'
    s=get_setting('reception_start','09:00'); e=get_setting('reception_end','21:00')
    days={int(x) for x in (get_setting('reception_days','0,1,2,3,4,5,6') or '').split(',') if x.strip().isdigit()}
    names=['Пн','Вт','Ср','Чт','Пт','Сб','Вс']
    day_text=' '.join(names[i] for i in range(7) if i in days) or '—'
    return enabled,s,e,day_text

def message_counts():
    schema.initialize(); c=database.connect()
    try:
        unread=c.execute("SELECT COUNT(*) n FROM crm_student_messages WHERE direction='IN' AND status='DELIVERED' AND read_at IS NULL").fetchone()['n']
        queued=c.execute("SELECT COUNT(*) n FROM crm_student_messages WHERE direction='IN' AND status='QUEUED'").fetchone()['n']
        dialogs=c.execute("SELECT COUNT(DISTINCT student_id) n FROM crm_student_messages").fetchone()['n']
        return {'unread':int(unread or 0),'queued':int(queued or 0),'dialogs':int(dialogs or 0)}
    finally:c.close()

def dialog_students(limit=100):
    schema.initialize(); c=database.connect()
    try:
        return c.execute("""
            SELECT u.id,u.name,
                   MAX(m.created_at) last_at,
                   SUM(CASE WHEN m.direction='IN' AND m.status='DELIVERED' AND m.read_at IS NULL THEN 1 ELSE 0 END) unread
            FROM crm_student_messages m JOIN users u ON u.id=m.student_id
            GROUP BY u.id,u.name ORDER BY datetime(last_at) DESC LIMIT ?
        """,(int(limit),)).fetchall()
    finally:c.close()

def mark_dialog_read(student_id):
    schema.initialize(); c=database.connect(); stamp=now().isoformat(timespec='seconds')
    try:
        c.execute("UPDATE crm_student_messages SET status='READ', read_at=? WHERE student_id=? AND direction='IN' AND status='DELIVERED' AND read_at IS NULL",(stamp,int(student_id)))
        c.execute("UPDATE teacher_inbox SET status='CLOSED',closed_at=? WHERE student_id=? AND status='OPEN' AND subject IN ('Сообщение от ученика','Ответ ученика')",(stamp,int(student_id)))
        c.commit()
    finally:c.close()

def parent_ids(student_id):
    try:return [int(r['telegram_id']) for r in database.get_student_parents(int(student_id), schedule_only=False) if r['telegram_id']]
    except Exception:return []

def log_message(student_id,direction,body,admin_id=None,target='STUDENT',status='SENT',scheduled_for=None,inbox_id=None):
    schema.initialize(); c=database.connect(); cur=c.cursor(); stamp=now().isoformat(timespec='seconds'); cur.execute('INSERT INTO crm_student_messages(student_id,direction,sender_admin_id,target,body,status,scheduled_for,created_at,sent_at,inbox_id,delivered_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(int(student_id),direction,admin_id,target,body,status,scheduled_for,stamp,stamp if status=='SENT' else None,inbox_id,stamp if status in ('SENT','DELIVERED') else None)); c.commit(); rid=cur.lastrowid; c.close(); return rid

def message_history(student_id,limit=30):
    schema.initialize(); c=database.connect(); rows=c.execute('SELECT * FROM crm_student_messages WHERE student_id=? ORDER BY created_at DESC LIMIT ?',(int(student_id),int(limit))).fetchall(); c.close(); return rows

def set_pinned_note(student_id,text,actor=None):
    schema.initialize(); c=database.connect(); c.execute('INSERT INTO student_pinned_notes(student_id,note,updated_by,updated_at) VALUES(?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET note=excluded.note,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(int(student_id),text,actor,now().isoformat(timespec='seconds'))); c.commit(); c.close()

def get_pinned_note(student_id):
    schema.initialize(); c=database.connect(); r=c.execute('SELECT note FROM student_pinned_notes WHERE student_id=?',(int(student_id),)).fetchone(); c.close(); return r['note'] if r else None

def add_agreement(student_id,text,valid_until=None,actor=None):
    schema.initialize(); c=database.connect(); cur=c.cursor(); cur.execute('INSERT INTO student_agreements(student_id,text,valid_until,created_by,created_at) VALUES(?,?,?,?,?)',(int(student_id),text,valid_until,actor,now().isoformat(timespec='seconds'))); c.commit(); rid=cur.lastrowid; c.close(); return rid

def agreements(student_id,limit=10):
    schema.initialize(); c=database.connect(); rows=c.execute("SELECT * FROM student_agreements WHERE student_id=? AND active=1 AND (valid_until IS NULL OR date(valid_until)>=date('now')) ORDER BY id DESC LIMIT ?",(int(student_id),int(limit))).fetchall(); c.close(); return rows

def attention_reasons(student_id):
    reasons=[]; c=database.connect()
    try:
        upcoming=c.execute("SELECT COUNT(*) n FROM lessons WHERE user_id=? AND cancelled_at IS NULL AND finished_at IS NULL AND datetime(start_time)>=datetime('now')",(int(student_id),)).fetchone()['n']
        if not upcoming:reasons.append('Нет следующего занятия')
        hw=c.execute("SELECT COUNT(*) n FROM homework WHERE user_id=? AND status IN ('ASSIGNED','REVISION') AND deadline IS NOT NULL AND datetime(deadline)<datetime('now')",(int(student_id),)).fetchone()['n']
        if hw:reasons.append(f'Просрочено ДЗ: {hw}')
    except Exception: pass
    finally:c.close()
    try:
        by=minute_balance.get_balance_by_rate(student_id); total=sum(v['total'] for v in by.values())
        if total<=180: reasons.append(f'Низкий баланс: {total} мин')
    except Exception: pass
    return reasons

def today_dashboard():
    schema.initialize(); c=database.connect();
    try:
        from core.lesson_time import lessons_on_local_day
        lessons=lessons_on_local_day(c,datetime.now(teacher_tz()).date(),teacher_tz(),"SELECT l.id,l.user_id,l.start_time,l.duration_minutes,u.name FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.cancelled_at IS NULL")
        open_msgs=c.execute("SELECT COUNT(*) n FROM teacher_inbox WHERE status='OPEN'").fetchone()['n']
        unpaid=c.execute("SELECT COUNT(*) n FROM lessons WHERE lesson_status='CONFIRMED' AND payment_status='AWAITING_PAYMENT'").fetchone()['n']
        students=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall()
    finally:c.close()
    attention=[]
    for u in students:
        rs=attention_reasons(u['id'])
        if rs: attention.append((u['id'],u['name'],rs))
    return {'lessons':lessons,'open_messages':open_msgs,'unpaid':unpaid,'attention':attention}

def program_label(p):return f"{GOAL_RU.get(str(p['study_goal']),p['study_goal'])} • {SUBJ_RU.get(str(p['subject']),p['subject'])}"

def billing_quote(student_id,program_id,lesson_count=10):
    q=renewals.recommendation(int(student_id),int(program_id))['quote']
    # quote uses current tariff rules and minute model
    return q

def save_billing_offer(student_id,program_id,quote,actor=None):
    schema.initialize(); c=database.connect(); cur=c.cursor(); cur.execute('INSERT INTO billing_offers(student_id,program_id,minutes,amount,discount_percent,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(int(student_id),int(program_id),int(quote['minutes']),int(quote['total']),float(quote.get('discount_percent',0)),'DRAFT',actor,now().isoformat(timespec='seconds'))); c.commit(); rid=cur.lastrowid;c.close();return rid

def choose_billing_payment_method(offer_id, method_id):
    schema.initialize(); c=database.connect()
    method=c.execute('SELECT * FROM payment_methods WHERE id=? AND active=1',(int(method_id),)).fetchone()
    if not method:
        c.close(); return None
    c.execute('UPDATE billing_offers SET payment_method_id=? WHERE id=?',(int(method_id),int(offer_id)))
    c.commit(); c.close(); return method

def active_payment_methods():
    return database.get_payment_methods(active_only=True)

def billing_payment_method(offer):
    mid=offer['payment_method_id'] if hasattr(offer,'keys') and 'payment_method_id' in offer.keys() else None
    method=database.get_payment_method(mid) if mid else database.get_default_payment_method()
    if method and int(method['active'] or 0): return method
    return database.get_default_payment_method()

def payment_method_message(method):
    if not method:return ''
    title=str(method['title'] or 'Способ оплаты').strip()
    details=str(method['details'] or '').strip()
    if details.startswith('💳 Реквизиты для оплаты'):
        return details
    return f"💳 {title}\n\n{details}"

def quick_month_report(student_id):
    try:return reports.build(int(student_id))
    except Exception:return 'Не удалось сформировать отчёт.'

def pause_student(student_id,date_to,reason,actor=None):
    from automation import schedule_tools
    return schedule_tools.add_pause(int(student_id),now().date().isoformat(),date_to,reason,actor)
