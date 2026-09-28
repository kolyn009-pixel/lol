"""Teacher-side invoice helpers for upcoming individual lessons.

Invoices reuse the canonical lesson-payment model. Creating an invoice is
idempotent because student_finance.create_lesson_payment reuses an existing
payment linked to the same lesson. A successful issue also attempts a PWA push
notification; notification failures never block invoice creation.
"""
from __future__ import annotations

from datetime import datetime

import database
from web_backend import web_push
from web_backend.student_finance import create_lesson_payment
from web_backend.invoice_pricing import individual_lesson_quote


def _payment_summary(row):
    if not row:
        return None
    keys=row.keys() if hasattr(row,'keys') else []
    return {
        'id':int(row['id']),
        'status':row['status'],
        'total_amount':int(row['total_amount'] or 0),
        'created_at':row['created_at'] if 'created_at' in keys else None,
    }


def _lesson_price(row):
    keys=row.keys() if hasattr(row,'keys') else []
    price=int(row['price'] or 0) if 'price' in keys else 0
    if price>0:
        return price
    hourly=int(row['hourly_rate'] or 0) if 'hourly_rate' in keys else 0
    duration=int(row['duration_minutes'] or 60) if 'duration_minutes' in keys else 60
    return round(hourly*duration/60) if hourly>0 else 0


def _notify_invoice(user_id,lesson_id,result,row):
    payment=result.get('payment') or {}
    amount=int(payment.get('total_amount') or result.get('total_amount') or result.get('amount') or _lesson_price(row) or 0)
    subject={'PHYSICS':'Физика','CHEMISTRY':'Химия'}.get(str(row['subject'] or '').upper(),str(row['subject'] or 'занятие'))
    try:
        start=datetime.fromisoformat(str(row['start_time']))
        when=start.strftime('%d.%m в %H:%M')
    except Exception:
        when='ближайшее занятие'
    body=f'{subject} · {when}'
    if amount>0:
        body+=f' · к оплате {amount:,} ₽'.replace(',', ' ')
    try:
        return web_push.send('student',int(user_id),'Новый счёт в Аделии',body,'/app/',f'invoice-{int(lesson_id)}',{'lesson_id':int(lesson_id),'type':'invoice'})
    except Exception as exc:
        return {'status':'failed','sent':0,'failed':1,'error':type(exc).__name__}


def candidates(limit=100):
    """Return the nearest unpaid future lesson for each active student."""
    lim=max(1,min(int(limit or 100),300))
    now=datetime.now().isoformat(timespec='seconds')
    conn=database.connect()
    rows=conn.execute(
        """SELECT l.*,u.name AS student_name
           FROM lessons l
           JOIN users u ON u.id=l.user_id
           WHERE u.active=1
             AND l.start_time>=?
             AND COALESCE(l.is_trial,0)=0
             AND l.lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')
             AND COALESCE(l.payment_status,'UNPAID') NOT IN ('PAID','FREE','RESERVED_BALANCE','TRANSFERRED')
           ORDER BY l.start_time,l.id
           LIMIT ?""",
        (now,max(lim*6,lim)),
    ).fetchall()
    conn.close()
    out=[];seen=set()
    for row in rows:
        uid=int(row['user_id'])
        if uid in seen:
            continue
        seen.add(uid)
        payment=database.get_payment_for_lesson(int(row['id']))
        individual=individual_lesson_quote(row) if payment is None else None
        out.append({
            'lesson_id':int(row['id']),
            'user_id':uid,
            'student_name':row['student_name'],
            'start_time':row['start_time'],
            'end_time':row['end_time'] if 'end_time' in row.keys() else None,
            'duration_minutes':int(row['duration_minutes'] or 0) if 'duration_minutes' in row.keys() else 0,
            'subject':row['subject'],
            'study_goal':row['study_goal'],
            'price':int(individual['amount']) if individual else _lesson_price(row),
            'price_source':individual['source'] if individual else 'LESSON_SNAPSHOT',
            'lesson_payment_status':row['payment_status'],
            'payment':_payment_summary(payment),
        })
        if len(out)>=lim:
            break
    return {'items':out,'count':len(out)}


def issue(lesson_id):
    lid=int(lesson_id)
    conn=database.connect()
    row=conn.execute('SELECT * FROM lessons WHERE id=?',(lid,)).fetchone()
    conn.close()
    if not row:
        raise ValueError('lesson_not_found')
    if bool(row['is_trial']) if 'is_trial' in row.keys() else False:
        raise ValueError('trial_lesson_not_payable')
    if str(row['lesson_status'] or '').upper() in {'CANCELLED','REJECTED','COMPLETED'}:
        raise ValueError('lesson_not_payable')
    if str(row['payment_status'] or 'UNPAID').upper() in {'PAID','FREE','RESERVED_BALANCE','TRANSFERRED'}:
        raise ValueError('lesson_already_paid')
    try:
        start=datetime.fromisoformat(str(row['start_time']))
        if start<datetime.now():
            raise ValueError('lesson_already_started')
    except ValueError as exc:
        if str(exc)=='lesson_already_started':
            raise
    uid=int(row['user_id'])
    result=create_lesson_payment(uid,lid)
    result['lesson_id']=lid
    result['user_id']=uid
    result['notification']=_notify_invoice(uid,lid,result,row)
    return result
