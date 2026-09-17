"""High-level notification fanout helpers for Adelia events."""
from __future__ import annotations

import database
from web_backend import web_push


def _teacher_ids():
    web_push.ensure_schema();conn=database.connect()
    try:
        rows=conn.execute("SELECT DISTINCT entity_id FROM web_push_subscriptions WHERE role='teacher' AND enabled=1").fetchall()
        return [int(r['entity_id']) for r in rows]
    finally:conn.close()


def _parent_ids(student_id):
    conn=database.connect()
    try:
        rows=conn.execute("""SELECT DISTINCT l.parent_id FROM parent_student_links l JOIN parent_accounts p ON p.id=l.parent_id WHERE l.student_id=? AND p.active=1""",(int(student_id),)).fetchall()
        return [int(r['parent_id']) for r in rows]
    except Exception:
        return []
    finally:conn.close()


def _messengers(student_id,title,body,telegram=True,vk=True):
    """Best-effort duplicate to linked Telegram/VK accounts.

    Kept optional so existing Web Push callers preserve their current behavior.
    """
    text=f"{str(title).strip()}\n\n{str(body).strip()}".strip()
    try:
        from vk_adapter.channel_delivery import send_student
        return send_student(int(student_id),text,telegram=bool(telegram),vk=bool(vk))
    except Exception as exc:
        return {'telegram':False,'vk':False,'error':type(exc).__name__}


def _persist_teacher_day_off_marker(data):
    if not isinstance(data,dict) or str(data.get('reason') or '')!='teacher_day_off' or not data.get('lesson_id'):
        return
    from web_backend import teacher_day_off_state
    teacher_day_off_state.mark_lesson(int(data['lesson_id']))


def teachers(title,body,url='/teacher/',tag=None,data=None):
    sent=failed=0;targets=0
    for tid in _teacher_ids():
        targets+=1
        try:
            r=web_push.send('teacher',tid,title,body,url,tag,data);sent+=int(r.get('sent') or 0);failed+=int(r.get('failed') or 0)
        except Exception:failed+=1
    return {'status':'ok','targets':targets,'sent':sent,'failed':failed}


def student(student_id,title,body,url='/app/',tag=None,data=None):
    try:return web_push.send('student',int(student_id),title,body,url,tag,data)
    except Exception:return {'status':'failed','sent':0,'failed':1}


def parents(student_id,title,body,url='/app/parent/',tag=None,data=None):
    sent=failed=0;targets=0
    for pid in _parent_ids(student_id):
        targets+=1
        try:
            r=web_push.send('parent',pid,title,body,url,tag,data);sent+=int(r.get('sent') or 0);failed+=int(r.get('failed') or 0)
        except Exception:failed+=1
    return {'status':'ok','targets':targets,'sent':sent,'failed':failed}


def student_and_parents(student_id,title,body,url='/app/',parent_url='/app/parent/',tag=None,data=None,mirror_messengers=False,telegram=True,vk=True):
    _persist_teacher_day_off_marker(data)
    result={'student':student(student_id,title,body,url,tag,data),'parents':parents(student_id,title,body,parent_url,tag,data)}
    if mirror_messengers:
        result['messengers']=_messengers(student_id,title,body,telegram=telegram,vk=vk)
    return result
