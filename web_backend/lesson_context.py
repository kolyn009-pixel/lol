"""Context services used by Adelia lesson workspaces.

Keeps lesson notes, granted study materials, attendance intent, factual join
signals and the unified conversation in one small API surface so teacher/student
lesson UIs do not need to load whole CRM screens while a lesson is running.
"""
from __future__ import annotations

from database import connect, now_iso
from web_backend.library import ensure_tables as ensure_library_tables, list_materials
from web_backend.unified_messages import conversation, queue_teacher_reply
from web_backend.teacher_crm import student as crm_student
from web_backend.homework_status import payload as homework_status_payload
from web_backend import lesson_join


def _lesson(lesson_id):
    lesson_join.ensure_schema()
    conn=connect()
    row=conn.execute("""SELECT id,user_id,subject,study_goal,start_time,end_time,
                              lesson_status,payment_status,started_at,finished_at,
                              attendance_intent_status,attendance_intent_at,
                              meeting_link_sent_at
                         FROM lessons WHERE id=?""",(int(lesson_id),)).fetchone()
    conn.close();return row


def context(lesson_id):
    row=_lesson(lesson_id)
    if not row:return None
    ensure_library_tables()
    conn=connect()
    notes=conn.execute("SELECT id,text,created_at FROM lesson_notes WHERE lesson_id=? ORDER BY created_at,id",(int(lesson_id),)).fetchall()
    homework=conn.execute("SELECT id,title,status,deadline,homework_type,source_type,source_url,assigned_at FROM homework WHERE user_id=? ORDER BY assigned_at DESC,id DESC LIMIT 8",(int(row['user_id']),)).fetchall()
    conn.close()
    hw=[]
    for item in homework:
        d=dict(item);d['status_ui']=homework_status_payload(d.get('status'));hw.append(d)
    crm=crm_student(int(row['user_id']))
    timeline=lesson_join.join_events(int(row['id']),limit=30)
    first_student_join=next((x for x in reversed(timeline) if x.get('actor_role')=='STUDENT' and x.get('event_type')=='JOIN_CLICKED'),None)
    return {
        'lesson_id':int(row['id']),
        'user_id':int(row['user_id']),
        'lesson':dict(row),
        'attendance_intent':{
            'status':row['attendance_intent_status'] or 'UNKNOWN',
            'updated_at':row['attendance_intent_at'],
        },
        'actual_join':{
            'joined':bool(first_student_join),
            'joined_at':first_student_join.get('created_at') if first_student_join else None,
            'started_at':row['started_at'],
        },
        'join_events':timeline,
        'student':crm.get('student') if crm else None,
        'student_stats':crm.get('stats') if crm else {},
        'next_lesson':crm.get('next_lesson') if crm else None,
        'recent_lessons':crm.get('recent_lessons') if crm else [],
        'notes':[dict(x) for x in notes],
        'materials':list_materials(user_id=int(row['user_id']),subject=row['subject'],limit=30),
        'homework':hw,
        'messages':conversation(int(row['user_id']),limit=40),
    }


def add_note(lesson_id,text):
    row=_lesson(lesson_id)
    if not row:return {'status':'not_found'}
    text=str(text or '').strip()
    if not text:return {'status':'text_required'}
    if len(text)>10000:return {'status':'text_too_long'}
    conn=connect();cur=conn.execute("INSERT INTO lesson_notes(lesson_id,user_id,text,created_at) VALUES(?,?,?,?)",(int(lesson_id),int(row['user_id']),text,now_iso()));conn.commit();nid=int(cur.lastrowid);conn.close()
    return {'status':'ok','note_id':nid}


def send_teacher_message(lesson_id,text):
    row=_lesson(lesson_id)
    if not row:return {'status':'not_found'}
    text=str(text or '').strip()
    if not text:return {'status':'text_required'}
    if len(text)>4000:return {'status':'text_too_long'}
    mid=queue_teacher_reply(int(row['user_id']),text)
    return {'status':'ok','message_id':mid,'delivery':'queued'}
