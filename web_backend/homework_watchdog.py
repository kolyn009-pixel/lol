"""Unified homework deadline watchdog for individual and group assignments.

The watchdog only creates durable outbox events and teacher tasks. Delivery is
performed by the existing homework delivery worker, so Telegram/VK retries and
deduplication remain centralized.
"""
from __future__ import annotations

from datetime import datetime, timedelta, date

import database
from core import teacher_tasks
from web_backend.homework_notifications import enqueue

REMIND_BEFORE_HOURS = 24


def ensure_schema():
    c = database.connect()
    c.execute("""CREATE TABLE IF NOT EXISTS homework_watchdog_events(
        event_key TEXT PRIMARY KEY,
        created_at TEXT NOT NULL
    )""")
    c.commit(); c.close()


def _once(key: str) -> bool:
    ensure_schema(); c=database.connect()
    cur=c.execute("INSERT OR IGNORE INTO homework_watchdog_events(event_key,created_at) VALUES(?,?)",(str(key),database.now_iso()))
    c.commit(); created=cur.rowcount>0; c.close(); return created


def _paused(user_id: int) -> bool:
    """Suppress reminders while the student is on vacation/sickness pause."""
    uid=int(user_id); c=database.connect(); today=date.today().isoformat()
    try:
        # Vacation/self-service pause is represented by paused regular schedules.
        try:
            row=c.execute("""SELECT 1 FROM regular_schedules
                WHERE user_id=? AND active=1 AND
                (UPPER(COALESCE(status,''))='PAUSED' OR (pause_until IS NOT NULL AND date(pause_until)>=date(?)))
                LIMIT 1""",(uid,today)).fetchone()
            if row:return True
        except Exception:
            pass
        # A sickness-marked current/upcoming lesson is the canonical sickness signal.
        try:
            row=c.execute("""SELECT 1 FROM lessons WHERE user_id=?
                AND UPPER(COALESCE(lesson_status,''))='SICKNESS'
                AND date(start_time)>=date('now','-1 day') LIMIT 1""",(uid,)).fetchone()
            if row:return True
        except Exception:
            pass
        return False
    finally:
        c.close()


def _individual_rows():
    c=database.connect()
    try:
        rows=c.execute("""SELECT h.id homework_id,h.user_id,h.title,h.deadline,h.status,u.name
            FROM homework h JOIN users u ON u.id=h.user_id
            WHERE h.deadline IS NOT NULL
              AND UPPER(COALESCE(h.status,'')) IN ('ASSIGNED','REVISION')""").fetchall()
        out=[]
        for r in rows:
            # Any real submission means the student has handed the work in; reminders stop.
            submitted=c.execute("SELECT 1 FROM homework_submissions WHERE homework_id=? AND user_id=? LIMIT 1",(r['homework_id'],r['user_id'])).fetchone()
            if not submitted:out.append(dict(r))
        return out
    except Exception:
        return []
    finally:c.close()


def _group_rows():
    c=database.connect()
    try:
        rows=c.execute("""SELECT gh.id homework_id,gh.group_id,gh.title,gh.due_at deadline,
                   gm.user_id,u.name,sg.name group_name
            FROM group_homework gh
            JOIN study_groups sg ON sg.id=gh.group_id
            JOIN group_members gm ON gm.group_id=gh.group_id AND gm.status='ACTIVE'
            JOIN users u ON u.id=gm.user_id
            WHERE gh.due_at IS NOT NULL
              AND NOT EXISTS(SELECT 1 FROM group_homework_submissions s
                             WHERE s.homework_id=gh.id AND s.user_id=gm.user_id)""").fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:c.close()


def _parse(raw):
    if not raw:return None
    try:return datetime.fromisoformat(str(raw).replace('Z','+00:00')).replace(tzinfo=None)
    except Exception:return None


def _student_url(kind, homework_id):
    return f"/app/?tab=homework&kind={kind.lower()}&homework={int(homework_id)}"


def _queue_student(kind, item, event, text):
    key=f"hw-watch:{event}:{kind}:{item['homework_id']}:{item['user_id']}"
    return enqueue(key,'STUDENT',event,text,int(item['user_id']),_student_url(kind,item['homework_id']),'Открыть ДЗ',{
        'kind':kind,'homework_id':int(item['homework_id']),'user_id':int(item['user_id'])
    })


def _teacher_task(kind, item):
    key=f"homework-missed:{kind}:{int(item['homework_id'])}:{int(item['user_id'])}"
    title=f"Не сдал ДЗ — {item['name']}"
    if kind=='GROUP':title+=f" · {item.get('group_name') or 'группа'}"
    teacher_tasks.add(title,user_id=int(item['user_id']),priority=1,source_type='HOMEWORK_WATCHDOG',source_key=key,
                      notes=f"{kind}|{int(item['homework_id'])}|{int(item['user_id'])}")


def _close_teacher_task(kind, homework_id, user_id):
    teacher_tasks.initialize(); c=database.connect(); now=database.now_iso()
    c.execute("UPDATE teacher_tasks SET status='DONE',updated_at=? WHERE source_key=? AND status IN ('OPEN','DEFERRED')",
              (now,f"homework-missed:{kind}:{int(homework_id)}:{int(user_id)}"))
    c.commit();c.close()


def reconcile_closed_tasks():
    """Close stale missed-homework tasks immediately after a submission appears."""
    teacher_tasks.initialize(); c=database.connect()
    rows=c.execute("SELECT source_key FROM teacher_tasks WHERE source_type='HOMEWORK_WATCHDOG' AND status IN ('OPEN','DEFERRED')").fetchall();c.close()
    active={(f"homework-missed:INDIVIDUAL:{r['homework_id']}:{r['user_id']}") for r in _individual_rows()}
    active.update(f"homework-missed:GROUP:{r['homework_id']}:{r['user_id']}" for r in _group_rows())
    c=database.connect();now=database.now_iso()
    for row in rows:
        if row['source_key'] not in active:c.execute("UPDATE teacher_tasks SET status='DONE',updated_at=? WHERE source_key=?",(now,row['source_key']))
    c.commit();c.close()


def tick(now=None):
    ensure_schema(); now=now or datetime.now(); queued=0; overdue=0; suppressed=0
    for kind,rows in (('INDIVIDUAL',_individual_rows()),('GROUP',_group_rows())):
        for item in rows:
            due=_parse(item.get('deadline'))
            if not due:continue
            if _paused(item['user_id']):
                suppressed+=1;continue
            hours=(due-now).total_seconds()/3600
            if 0 < hours <= REMIND_BEFORE_HOURS:
                if _once(f"due-soon:{kind}:{item['homework_id']}:{item['user_id']}"):
                    title=item.get('title') or 'Домашнее задание'
                    queued += int(_queue_student(kind,item,'HOMEWORK_DUE_SOON',f"📝 Напоминание о ДЗ\n\n«{title}» нужно сдать до {due:%d.%m %H:%M}."))
            elif hours <= 0:
                if _once(f"overdue:{kind}:{item['homework_id']}:{item['user_id']}"):
                    title=item.get('title') or 'Домашнее задание'
                    queued += int(_queue_student(kind,item,'HOMEWORK_OVERDUE',f"⏰ ДЗ просрочено\n\n«{title}» ещё не сдано. Отправь решение, как только будет готово."))
                _teacher_task(kind,item);overdue+=1
    reconcile_closed_tasks()
    return {'queued':queued,'overdue':overdue,'suppressed':suppressed}


def remind_from_task(source_key: str):
    """Manual teacher reminder for an open missed-homework task."""
    parts=str(source_key or '').split(':')
    if len(parts)!=4 or parts[0]!='homework-missed':return {'status':'invalid_task'}
    kind,hid,uid=parts[1],int(parts[2]),int(parts[3])
    rows=_individual_rows() if kind=='INDIVIDUAL' else _group_rows() if kind=='GROUP' else []
    item=next((x for x in rows if int(x['homework_id'])==hid and int(x['user_id'])==uid),None)
    if not item:
        _close_teacher_task(kind,hid,uid);return {'status':'already_submitted'}
    if _paused(uid):return {'status':'suppressed'}
    stamp=datetime.now().strftime('%Y%m%d%H')
    created=enqueue(f"hw-manual:{kind}:{hid}:{uid}:{stamp}",'STUDENT','HOMEWORK_MANUAL_REMINDER',
                    f"💜 Напоминание от преподавателя\n\nНе забудь сдать ДЗ «{item.get('title') or 'Домашнее задание'}».",uid,
                    _student_url(kind,hid),'Открыть ДЗ',{'kind':kind,'homework_id':hid,'user_id':uid})
    return {'status':'ok' if created else 'already_reminded'}
