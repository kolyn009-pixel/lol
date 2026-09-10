"""Audience, invitations, seat holds and announcement delivery for learning events."""
from __future__ import annotations

from datetime import datetime,timedelta
import database
from vk_adapter import channel_delivery
from web_backend import message_delivery,open_event_policy

RULES={'SUBJECT','GOAL','GRADE','GROUP','ALL_ACTIVE'}
INVITE_ACTIVE={'HELD','ACCEPTED'}


def _now(): return database.now_iso()
def _dt(v): return datetime.fromisoformat(str(v))


def ensure_schema():
    open_event_policy.ensure_schema();c=database.connect();c.executescript("""
    CREATE TABLE IF NOT EXISTS open_event_audience_rules(
      event_id INTEGER NOT NULL,rule_type TEXT NOT NULL,rule_value TEXT NOT NULL,created_at TEXT NOT NULL,
      PRIMARY KEY(event_id,rule_type,rule_value),FOREIGN KEY(event_id) REFERENCES open_learning_events(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS open_event_invites(
      event_id INTEGER NOT NULL,user_id INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'HELD',hold_until TEXT,reason TEXT,invited_by INTEGER,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
      PRIMARY KEY(event_id,user_id),FOREIGN KEY(event_id) REFERENCES open_learning_events(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS open_event_publications(
      id INTEGER PRIMARY KEY AUTOINCREMENT,event_id INTEGER NOT NULL,target_type TEXT NOT NULL,target_id TEXT,kind TEXT NOT NULL,status TEXT NOT NULL,error TEXT,created_at TEXT NOT NULL,
      FOREIGN KEY(event_id) REFERENCES open_learning_events(id) ON DELETE CASCADE);
    CREATE INDEX IF NOT EXISTS idx_event_invites_hold ON open_event_invites(event_id,status,hold_until);
    CREATE INDEX IF NOT EXISTS idx_event_audience ON open_event_audience_rules(rule_type,rule_value,event_id);
    """);c.commit();c.close()


def set_audience(event_id,rules):
    ensure_schema();eid=int(event_id);clean=[]
    for item in rules or []:
        kind=str((item or {}).get('type') or '').upper();value=str((item or {}).get('value') or '').strip().upper()
        if kind in RULES and value:clean.append((kind,value))
    if not clean:clean=[('ALL_ACTIVE','1')]
    c=database.connect();c.execute('DELETE FROM open_event_audience_rules WHERE event_id=?',(eid,));now=_now()
    for kind,value in sorted(set(clean)):c.execute('INSERT INTO open_event_audience_rules(event_id,rule_type,rule_value,created_at) VALUES(?,?,?,?)',(eid,kind,value,now))
    c.commit();c.close();return [{'type':a,'value':b} for a,b in sorted(set(clean))]


def audience_rules(event_id):
    ensure_schema();c=database.connect();rows=c.execute('SELECT rule_type,rule_value FROM open_event_audience_rules WHERE event_id=? ORDER BY rule_type,rule_value',(int(event_id),)).fetchall();c.close();return [{'type':r['rule_type'],'value':r['rule_value']} for r in rows]


def _student_matches(uid,rules):
    if any(r['type']=='ALL_ACTIVE' for r in rules):return True
    u=database.get_user(int(uid))
    if not u or not u['active']:return False
    # Rules of the same type are OR; different types are AND.
    grouped={}
    for r in rules:grouped.setdefault(r['type'],set()).add(r['value'])
    for kind,vals in grouped.items():
        if kind=='SUBJECT' and str(u['main_subject'] or '').upper() not in vals:return False
        if kind=='GOAL' and str(u['study_goal'] or '').upper() not in vals:return False
        if kind=='GRADE' and str(u['grade'] or '').upper() not in vals:return False
        if kind=='GROUP':
            c=database.connect();rows=c.execute("SELECT group_id FROM group_members WHERE user_id=? AND status IN ('ACTIVE','PAUSED')",(int(uid),)).fetchall();c.close()
            if not ({str(r['group_id']) for r in rows}&vals):return False
    return True


def audience_student_ids(event_id):
    rules=audience_rules(event_id);c=database.connect();ids=[int(r['id']) for r in c.execute('SELECT id FROM users WHERE active=1').fetchall()];c.close();return [uid for uid in ids if _student_matches(uid,rules)]


def _capacity(event_id,exclude_user_id=None):
    ensure_schema();eid=int(event_id);now=_now();c=database.connect();e=c.execute('SELECT max_participants FROM open_learning_events WHERE id=?',(eid,)).fetchone()
    if not e:c.close();raise ValueError('event_not_found')
    registered=int(c.execute("SELECT COUNT(*) n FROM open_event_participants WHERE event_id=? AND status='REGISTERED'"+(" AND user_id<>?" if exclude_user_id else ''),(eid,int(exclude_user_id)) if exclude_user_id else (eid,)).fetchone()['n'])
    holds=int(c.execute("SELECT COUNT(*) n FROM open_event_invites WHERE event_id=? AND status='HELD' AND hold_until>?"+(" AND user_id<>?" if exclude_user_id else ''),(eid,now,int(exclude_user_id)) if exclude_user_id else (eid,now)).fetchone()['n']);c.close()
    maximum=int(e['max_participants']) if e['max_participants'] else None
    return {'max':maximum,'used':registered+holds,'remaining':None if maximum is None else max(0,maximum-registered-holds)}


def invite_student(event_id,user_id,teacher_id,reason=None,hold_hours=24):
    ensure_schema();eid=int(event_id);uid=int(user_id);cap=_capacity(eid,uid)
    if cap['remaining'] is not None and cap['remaining']<=0:raise ValueError('event_full')
    c=database.connect();e=c.execute('SELECT title,event_type,starts_at,price_per_student FROM open_learning_events WHERE id=?',(eid,)).fetchone()
    if not e:c.close();raise ValueError('event_not_found')
    until=(datetime.now()+timedelta(hours=max(1,min(int(hold_hours or 24),168)))).isoformat(timespec='seconds');now=_now()
    c.execute("""INSERT INTO open_event_invites(event_id,user_id,status,hold_until,reason,invited_by,created_at,updated_at)
      VALUES(?,?,'HELD',?,?,?,?,?) ON CONFLICT(event_id,user_id) DO UPDATE SET status='HELD',hold_until=excluded.hold_until,reason=excluded.reason,invited_by=excluded.invited_by,updated_at=excluded.updated_at""",(eid,uid,until,str(reason or '').strip()[:500] or None,int(teacher_id),now,now));c.commit();c.close()
    kind='пробник' if e['event_type']=='MOCK_EXAM' else 'семинар';extra=f"\nПричина рекомендации: {reason}" if reason else ''
    text=f"💜 Персональное приглашение\n\nЯ рекомендую тебе {kind} «{e['title']}».\nДата: {e['starts_at']}\nСтоимость: {int(e['price_per_student'] or 0)} ₽.{extra}\n\nПока ты думаешь, место придержано до {until}. Открой Аделию — там можно принять или отказаться."
    try:message_delivery.send_teacher_reply(uid,text,teacher_id=teacher_id);status='SENT';err=None
    except Exception as exc:status='FAILED';err=type(exc).__name__
    _log(eid,'STUDENT',uid,'PERSONAL_INVITE',status,err);return {'status':'ok','event_id':eid,'user_id':uid,'hold_until':until,'delivery_status':status}


def respond_invite(event_id,user_id,accepted):
    ensure_schema();eid=int(event_id);uid=int(user_id);c=database.connect();inv=c.execute('SELECT * FROM open_event_invites WHERE event_id=? AND user_id=?',(eid,uid)).fetchone()
    if not inv:c.close();raise ValueError('invite_not_found')
    if accepted and inv['hold_until'] and _now()>inv['hold_until']:c.close();raise ValueError('invite_hold_expired')
    c.execute('UPDATE open_event_invites SET status=?,updated_at=? WHERE event_id=? AND user_id=?',('ACCEPTED' if accepted else 'DECLINED',_now(),eid,uid));c.commit();c.close()
    if accepted:return register(event_id,user_id,allow_invite=True)
    return {'status':'declined','event_id':eid}


def register(event_id,user_id,allow_invite=False):
    ensure_schema();eid=int(event_id);uid=int(user_id);rules=audience_rules(eid);c=database.connect();inv=c.execute('SELECT status,hold_until FROM open_event_invites WHERE event_id=? AND user_id=?',(eid,uid)).fetchone();c.close()
    invited=bool(inv and inv['status'] in INVITE_ACTIVE and (not inv['hold_until'] or inv['hold_until']>=_now()))
    if not invited and not _student_matches(uid,rules):raise PermissionError('event_not_for_student_category')
    cap=_capacity(eid,uid)
    if cap['remaining'] is not None and cap['remaining']<=0:raise ValueError('event_full')
    c=database.connect();e=c.execute('SELECT price_per_student,status,registration_deadline FROM open_learning_events WHERE id=?',(eid,)).fetchone()
    if not e:c.close();raise ValueError('event_not_found')
    if e['status']!='OPEN':c.close();raise ValueError('event_registration_closed')
    if e['registration_deadline'] and _now()>e['registration_deadline']:c.close();raise ValueError('event_registration_closed')
    pay='WAIVED' if int(e['price_per_student'] or 0)==0 else 'UNPAID';now=_now();c.execute("""INSERT INTO open_event_participants(event_id,user_id,status,payment_status,teacher_decision,access_granted,registered_at,updated_at)
      VALUES(?,?,'REGISTERED',?,'APPROVED',0,?,?) ON CONFLICT(event_id,user_id) DO UPDATE SET status='REGISTERED',teacher_decision='APPROVED',updated_at=excluded.updated_at""",(eid,uid,pay,now,now));c.execute("UPDATE open_event_invites SET status='ACCEPTED',updated_at=? WHERE event_id=? AND user_id=?",(now,eid,uid));c.commit();c.close();return {'status':'registered','event_id':eid,'payment_status':pay}


def feed(user_id):
    ensure_schema();uid=int(user_id);c=database.connect();events=c.execute("SELECT * FROM open_learning_events WHERE status='OPEN' AND starts_at>=? ORDER BY starts_at",(_now(),)).fetchall();c.close();out=[]
    for row in events:
        eid=int(row['id']);rules=audience_rules(eid);c=database.connect();inv=c.execute('SELECT * FROM open_event_invites WHERE event_id=? AND user_id=?',(eid,uid)).fetchone();reg=c.execute('SELECT * FROM open_event_participants WHERE event_id=? AND user_id=?',(eid,uid)).fetchone();c.close();invited=bool(inv and inv['status'] in INVITE_ACTIVE and (not inv['hold_until'] or inv['hold_until']>=_now()))
        if _student_matches(uid,rules) or invited or reg:
            item=dict(row);item['invite']=dict(inv) if inv else None;item['registration']=dict(reg) if reg else None;item['capacity']=_capacity(eid,uid);out.append(item)
    return out


def _log(eid,target_type,target_id,kind,status,error=None):
    c=database.connect();c.execute('INSERT INTO open_event_publications(event_id,target_type,target_id,kind,status,error,created_at) VALUES(?,?,?,?,?,?,?)',(int(eid),target_type,str(target_id) if target_id is not None else None,kind,status,error,_now()));c.commit();c.close()


def announcement_text(event_id):
    c=database.connect();e=c.execute('SELECT * FROM open_learning_events WHERE id=?',(int(event_id),)).fetchone();c.close()
    if not e:raise ValueError('event_not_found')
    kind='📝 ПРОБНИК' if e['event_type']=='MOCK_EXAM' else '🎓 СЕМИНАР';topic=f"\nТема: {e['topic']}" if 'topic' in e.keys() and e['topic'] else ''
    return f"{kind}\n\n{e['title']}{topic}\n📅 {e['starts_at']}\n⏱ До {e['ends_at']}\n💳 {int(e['price_per_student'] or 0)} ₽\n\nЗапись открыта в Аделии. Количество мест может быть ограничено."


def publish_event(event_id,teacher_id=None):
    ensure_schema();eid=int(event_id);text=announcement_text(eid);channel_id=database.get_setting('free_slots_channel_id');channel_ok=False
    if channel_id:
        try:channel_ok=channel_delivery.send_telegram_chat(int(channel_id),text)
        except Exception:channel_ok=False
    _log(eid,'CHANNEL',channel_id,'EVENT_ANNOUNCEMENT','SENT' if channel_ok else 'FAILED' if channel_id else 'SKIPPED',None if channel_ok else 'channel_unavailable')
    sent=failed=0
    for uid in audience_student_ids(eid):
        try:r=message_delivery.send_teacher_reply(uid,"📣 Новое событие в Аделии\n\n"+text+"\n\nОткрой личный кабинет, чтобы записаться.",teacher_id=teacher_id);ok=r.get('status')=='ok'
        except Exception:ok=False
        sent+=1 if ok else 0;failed+=0 if ok else 1;_log(eid,'STUDENT',uid,'AUDIENCE_ANNOUNCEMENT','SENT' if ok else 'FAILED')
    return {'channel':'SENT' if channel_ok else 'SKIPPED_OR_FAILED','students_sent':sent,'students_failed':failed}
