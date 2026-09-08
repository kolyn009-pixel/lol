"""Student-facing homework service shared by the web cabinet.

Keeps teacher-only answer keys out of student responses and combines ordinary,
interactive, and tracked external homework in one feed.
"""
from database import connect
from web_backend.assessment import student_homework_payload, submit_structured
from web_backend.external_homework import get_external_link, mark_opened, set_student_status


def list_homework(user_id,limit=100):
    conn=connect();rows=conn.execute("""SELECT id,title,description,homework_type,source_type,source_reference,source_url,deadline,status,assigned_at,submitted_at,reviewed_at,subject,study_goal,lesson_id FROM homework WHERE user_id=? ORDER BY CASE WHEN status IN ('ASSIGNED','UNDER_REVIEW','REVISION') THEN 0 ELSE 1 END, COALESCE(deadline,assigned_at) DESC LIMIT ?""",(int(user_id),int(limit))).fetchall();conn.close()
    out=[]
    for row in rows:
        item=dict(row);ext=get_external_link(item['id']);item['external']=ext
        # Never expose task_bank.answer or task_bank.solution.
        try:
            payload=student_homework_payload(item['id'],user_id)
            item['interactive_task_count']=len(payload['tasks']) if payload else 0
            item['material_count']=len(payload['materials']) if payload else 0
        except Exception:
            item['interactive_task_count']=0;item['material_count']=0
        out.append(item)
    return out


def detail(homework_id,user_id):
    payload=student_homework_payload(homework_id,user_id)
    if not payload:return None
    payload['external']=get_external_link(homework_id)
    return payload


def submit_answers(homework_id,user_id,responses,attempt_number=1):
    return submit_structured(homework_id,user_id,responses,attempt_number)


def open_external(homework_id,user_id,reminder_due_at=None):
    link=get_external_link(homework_id)
    if not link:raise ValueError('external_link_not_found')
    mark_opened(homework_id,user_id,reminder_due_at=reminder_due_at,source_channel='WEB')
    return {'status':'ok','url':link['external_url'],'provider':link['provider']}


def external_status(homework_id,user_id,status):
    return set_student_status(homework_id,user_id,status,source_channel='WEB')
