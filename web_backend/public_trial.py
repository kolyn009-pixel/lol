"""Public trial-lesson request intake.

Creates a lightweight lead, not a full student account. A real student profile is
created only after the teacher accepts the request and completes normal onboarding.
"""
from __future__ import annotations

from datetime import datetime
import re

import database
from core import event_center

MAX_NAME=80
MAX_CONTACT=160
MAX_NOTE=600
MAX_SUBJECT=80


def ensure_schema():
    c=database.connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS public_trial_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      contact TEXT NOT NULL,
      subject TEXT,
      study_goal TEXT,
      preferred_time TEXT,
      note TEXT,
      status TEXT NOT NULL DEFAULT 'NEW',
      source TEXT NOT NULL DEFAULT 'WEB',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      reviewed_at TEXT,
      reviewer_id INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_public_trial_status_created
      ON public_trial_requests(status,created_at DESC);
    """)
    c.commit();c.close()


def _clean(value,limit):
    return re.sub(r'\s+',' ',str(value or '').strip())[:limit]


def create(name,contact,subject=None,study_goal=None,preferred_time=None,note=None,source='WEB'):
    ensure_schema()
    name=_clean(name,MAX_NAME);contact=_clean(contact,MAX_CONTACT)
    subject=_clean(subject,MAX_SUBJECT) or None;study_goal=_clean(study_goal,MAX_SUBJECT) or None
    preferred_time=_clean(preferred_time,80) or None;note=_clean(note,MAX_NOTE) or None
    if len(name)<2:raise ValueError('name_required')
    if len(contact)<3:raise ValueError('contact_required')
    now=datetime.now().isoformat(timespec='seconds')
    c=database.connect();cur=c.execute("""INSERT INTO public_trial_requests(name,contact,subject,study_goal,preferred_time,note,status,source,created_at,updated_at)
      VALUES(?,?,?,?,?,?,'NEW',?,?,?)""",(name,contact,subject,study_goal,preferred_time,note,str(source or 'WEB')[:20],now,now));rid=cur.lastrowid;c.commit();c.close()
    try:
        parts=[f'Контакт: {contact}']
        if subject:parts.append(f'Предмет: {subject}')
        if study_goal:parts.append(f'Цель: {study_goal}')
        if preferred_time:parts.append(f'Желаемое время: {preferred_time}')
        if note:parts.append(note)
        event_center.push('PUBLIC_TRIAL_REQUEST',f'Пробное занятие: {name}',' · '.join(parts),'ACTION','public_trial',int(rid),f'public_trial:{int(rid)}')
    except Exception:pass
    return {'status':'ok','request_id':int(rid)}


def list_for_teacher(status=None,limit=100):
    ensure_schema();c=database.connect();sql='SELECT * FROM public_trial_requests';p=[]
    if status:
        sql+=' WHERE status=?';p.append(str(status).upper())
    sql+=' ORDER BY created_at DESC LIMIT ?';p.append(max(1,min(int(limit),200)))
    rows=c.execute(sql,p).fetchall();c.close();return [dict(r) for r in rows]


def set_status(request_id,status,reviewer_id=None):
    ensure_schema();status=str(status or '').upper()
    if status not in {'NEW','CONTACTED','ACCEPTED','DECLINED','CLOSED'}:raise ValueError('invalid_status')
    now=datetime.now().isoformat(timespec='seconds');c=database.connect();cur=c.execute("UPDATE public_trial_requests SET status=?,updated_at=?,reviewed_at=?,reviewer_id=? WHERE id=?",(status,now,now,int(reviewer_id) if reviewer_id else None,int(request_id)));c.commit();c.close()
    if cur.rowcount!=1:raise ValueError('request_not_found')
    return {'status':'ok','request_id':int(request_id),'request_status':status}
