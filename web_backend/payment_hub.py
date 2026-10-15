"""Unified payment hub for student and parent surfaces.

UX contract:
- Primary CTA: pay the nearest unpaid upcoming lesson.
- Secondary CTA: buy a package/subscription.
- Then show balances, existing pending payment, history and all upcoming lessons.

Parents act only on students linked through parent_student_links and reuse the
same canonical student_finance functions, so web/PWA/desktop/bot surfaces can
render one consistent payment model instead of exposing a lesson list first.
"""
from __future__ import annotations

from datetime import datetime
from core.lesson_time import schedule_datetime, lesson_timezone

import database
from web_backend import student_finance
from web_backend.invoice_pricing import individual_lesson_quote


def _linked(parent_id, student_id):
    c=database.connect()
    row=c.execute(
        """SELECT 1 FROM parent_student_links l
           JOIN parent_accounts p ON p.id=l.parent_id
           JOIN users u ON u.id=l.student_id
           WHERE l.parent_id=? AND l.student_id=? AND p.active=1 AND u.active=1 LIMIT 1""",
        (int(parent_id),int(student_id)),
    ).fetchone()
    c.close()
    if not row:
        raise PermissionError('student_not_linked')
    return int(student_id)


def _lesson_dict(row):
    if not row:return None
    keys=row.keys() if hasattr(row,'keys') else []
    amount=int(row['price'] or 0)
    source='LESSON_SNAPSHOT'
    if str(row['payment_status'] or '').upper() not in {'PAID','FREE','RESERVED_BALANCE','TRANSFERRED'}:
        existing=database.get_payment_for_lesson(int(row['id']))
        if existing:
            amount=int(existing['total_amount'] or 0);source='EXISTING_PAYMENT'
        else:
            individual=individual_lesson_quote(row)
            if individual:
                amount=int(individual['amount']);source=individual['source']
    return {
        'id':int(row['id']),
        'start_time':row['start_time'],
        'start_at':schedule_datetime(row['start_time']).isoformat(),
        'program_id':int(row['program_id']) if 'program_id' in keys and row['program_id'] else None,
        'end_time':row['end_time'] if 'end_time' in keys else None,
        'duration_minutes':int(row['duration_minutes'] or 0) if 'duration_minutes' in keys else 0,
        'subject':row['subject'],
        'study_goal':row['study_goal'],
        'lesson_status':row['lesson_status'],
        'payment_status':row['payment_status'],
        'price':amount,
        'price_source':source,
        'is_trial':bool(row['is_trial']) if 'is_trial' in keys else False,
    }


def nearest_payable_lesson(user_id):
    uid=int(user_id);now=datetime.now(lesson_timezone()).replace(tzinfo=None).isoformat(timespec='seconds');c=database.connect()
    row=c.execute(
        """SELECT * FROM lessons
           WHERE user_id=? AND start_time>=?
             AND COALESCE(is_trial,0)=0
             AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')
             AND COALESCE(payment_status,'UNPAID') NOT IN ('PAID','FREE','RESERVED_BALANCE','TRANSFERRED')
           ORDER BY start_time,id LIMIT 1""",
        (uid,now),
    ).fetchone();c.close();return _lesson_dict(row)


def upcoming_payment_lessons(user_id,limit=12):
    uid=int(user_id);now=datetime.now(lesson_timezone()).replace(tzinfo=None).isoformat(timespec='seconds');c=database.connect()
    rows=c.execute(
        """SELECT * FROM lessons
           WHERE user_id=? AND start_time>=? AND COALESCE(is_trial,0)=0
             AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')
           ORDER BY start_time,id LIMIT ?""",
        (uid,now,max(1,min(int(limit),50))),
    ).fetchall();c.close();return [_lesson_dict(r) for r in rows]


def student_hub(user_id):
    uid=int(user_id);user=database.get_user(uid)
    if not user:raise PermissionError('student_not_found')
    finance=student_finance.overview(uid)
    nearest=nearest_payable_lesson(uid)
    return {
        'student':{'id':uid,'name':user['name']},
        'schedule_timezone':str(lesson_timezone()),
        'primary_action':{
            'type':'PAY_NEAREST' if nearest else 'BUY_PACKAGE',
            'label':'Оплатить ближайшее занятие' if nearest else 'Купить абонемент',
            'lesson':nearest,
        },
        'secondary_action':{'type':'BUY_PACKAGE','label':'Купить абонемент'},
        'nearest_unpaid_lesson':nearest,
        'upcoming_lessons':upcoming_payment_lessons(uid),
        'finance':finance,
    }


def parent_hub(parent_id,student_id=None):
    pid=int(parent_id);c=database.connect()
    if student_id is None:
        rows=c.execute(
            """SELECT u.id,u.name FROM parent_student_links l
               JOIN parent_accounts p ON p.id=l.parent_id
               JOIN users u ON u.id=l.student_id
               WHERE l.parent_id=? AND p.active=1 AND u.active=1 ORDER BY u.name,u.id""",
            (pid,),
        ).fetchall();c.close()
        items=[]
        for row in rows:
            hub=student_hub(int(row['id']))
            items.append({'student':{'id':int(row['id']),'name':row['name']},'nearest_unpaid_lesson':hub['nearest_unpaid_lesson'],'primary_action':hub['primary_action']})
        return {'students':items,'choose_student':len(items)>1,'single':items[0] if len(items)==1 else None}
    c.close();uid=_linked(pid,int(student_id));return student_hub(uid)


def parent_pay_nearest(parent_id,student_id,promo_code=None):
    uid=_linked(parent_id,student_id);lesson=nearest_payable_lesson(uid)
    if not lesson:raise ValueError('no_payable_lesson')
    return student_finance.create_lesson_payment(uid,int(lesson['id']),promo_code)


def parent_create_package(parent_id,student_id,selection_key,lessons_count,promo_code=None):
    uid=_linked(parent_id,student_id)
    return student_finance.create_package_payment(uid,int(selection_key),int(lessons_count),promo_code)


def parent_quote_package(parent_id,student_id,selection_key,lessons_count,promo_code=None):
    uid=_linked(parent_id,student_id)
    return student_finance.quote(uid,int(selection_key),int(lessons_count),promo_code)


def parent_attach_receipt(parent_id,student_id,payment_id,filename,mime_type,content_b64):
    uid=_linked(parent_id,student_id)
    return student_finance.attach_receipt(uid,int(payment_id),filename,mime_type,content_b64)


def parent_claim_payment(parent_id,student_id,payment_id):
    uid=_linked(parent_id,student_id)
    return student_finance.claim_payment(uid,int(payment_id))



def parent_payment(parent_id,student_id,payment_id):
    uid=_linked(parent_id,student_id)
    return {'payment':student_finance._safe_payment(student_finance._payment_owned(uid,int(payment_id)))}
