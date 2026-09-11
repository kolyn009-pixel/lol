"""Unified teacher request center for lesson, public-trial and onboarding requests."""
from __future__ import annotations

import json
from datetime import datetime

import database
from web_backend import public_trial, student_onboarding


def _lesson_requests(limit=100):
    c = database.connect()
    try:
        rows = c.execute(
            """
            SELECT l.id,l.user_id,l.program_id,l.study_goal,l.subject,l.start_time,l.end_time,
                   l.duration_minutes,l.price,l.is_trial,l.lesson_status,l.request_source,l.created_at,
                   u.name,u.grade,u.telegram_username
            FROM lessons l
            JOIN users u ON u.id=l.user_id
            WHERE l.lesson_status='PENDING' AND l.request_source='STUDENT'
            ORDER BY l.start_time ASC
            LIMIT ?
            """,
            (max(1,min(int(limit),200)),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def _onboarding_requests(limit=100):
    student_onboarding.ensure_schema()
    c = database.connect()
    try:
        rows = c.execute(
            """
            SELECT id,token,name,grade,subject,study_goal,preferred_channel,external_username,
                   region,timezone,schedule_json,status,linked_user_id,provisional_user_created,
                   created_at,updated_at,completed_at
            FROM student_onboarding_sessions
            WHERE status IN ('SCHEDULE_SET','COMPLETED') AND schedule_json IS NOT NULL
            ORDER BY updated_at DESC LIMIT ?
            """,
            (max(1,min(int(limit),200)),),
        ).fetchall()
        out=[]
        for r in rows:
            x=dict(r)
            try:x['schedule']=json.loads(x.pop('schedule_json') or '[]')
            except Exception:x['schedule']=[];x.pop('schedule_json',None)
            out.append(x)
        return out
    finally:
        c.close()


def list_all(limit=100):
    trials=public_trial.list_for_teacher(limit=limit)
    lessons=_lesson_requests(limit)
    onboarding=_onboarding_requests(limit)
    return {
        'counts':{
            'trial':sum(1 for x in trials if x.get('status') in {'NEW','CONTACTED'}),
            'lesson':len(lessons),
            'schedule':sum(1 for x in onboarding if x.get('status') in {'SCHEDULE_SET','COMPLETED'}),
        },
        'trials':trials,
        'lesson_requests':lessons,
        'schedule_requests':onboarding,
    }


def approve_lesson(lesson_id):
    lesson=database.get_lesson(int(lesson_id))
    if not lesson:raise ValueError('lesson_not_found')
    if lesson['lesson_status']!='PENDING':raise ValueError('lesson_not_pending')
    database.approve_lesson_request(int(lesson_id))
    return {'status':'ok','lesson_id':int(lesson_id),'lesson_status':'CONFIRMED'}


def reject_lesson(lesson_id,reason=None):
    lesson=database.get_lesson(int(lesson_id))
    if not lesson:raise ValueError('lesson_not_found')
    if lesson['lesson_status']!='PENDING':raise ValueError('lesson_not_pending')
    database.reject_lesson_request(int(lesson_id),str(reason or '').strip()[:500] or None)
    return {'status':'ok','lesson_id':int(lesson_id),'lesson_status':'REJECTED'}
