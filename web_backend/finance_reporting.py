"""Read-only Stage 8 finance reporting over existing TutorBot money tables."""
from __future__ import annotations
from datetime import datetime, timedelta
import database
from database import connect

PAID={'PAID','CONFIRMED','APPROVED'}
PENDING={'WAITING','PENDING','REVIEW'}
EXCLUDED_LESSON_STATUSES={'CANCELLED','REJECTED'}

def _lesson_earned_expr(alias='l'):
    """Revenue value of a lesson, excluding non-cash bonus/free minutes.

    If a lesson is funded by a mix of paid and bonus minutes, only the paid
    fraction counts as earned lesson value. Direct paid/legacy lessons retain
    their stored price.
    """
    a=str(alias)
    return f"""CASE
      WHEN COALESCE({a}.payment_status,'')='FREE' THEN 0
      WHEN COALESCE({a}.reserved_minutes,0)>0 THEN
        ROUND(COALESCE({a}.price,0) * CAST(COALESCE({a}.reserved_paid_minutes,0) AS REAL) / {a}.reserved_minutes)
      ELSE COALESCE({a}.price,0)
    END"""

def _lesson_funding_expr(alias='l'):
    a=str(alias)
    return f"""CASE
      WHEN COALESCE({a}.payment_status,'')='FREE' THEN 'BONUS'
      WHEN COALESCE({a}.reserved_minutes,0)>0 AND COALESCE({a}.reserved_paid_minutes,0)=0 THEN 'BONUS'
      WHEN COALESCE({a}.reserved_minutes,0)>0 AND COALESCE({a}.reserved_bonus_minutes,0)>0 THEN 'MIXED'
      ELSE 'PAID'
    END"""


def _iso_start(value,days=30):
    if value:
        try:return datetime.fromisoformat(str(value)).isoformat(timespec='seconds')
        except Exception:pass
    return (datetime.now()-timedelta(days=days)).isoformat(timespec='seconds')


def _iso_end(value):
    if value:
        try:return datetime.fromisoformat(str(value)).isoformat(timespec='seconds')
        except Exception:pass
    return datetime.now().isoformat(timespec='seconds')


def _period_bounds(period,now=None):
    now=now or datetime.now();key=str(period or '').strip().lower()
    if key=='week':
        start=datetime.combine(now.date()-timedelta(days=now.weekday()),datetime.min.time());end=start+timedelta(days=7)
    elif key=='month':
        start=datetime(now.year,now.month,1);end=datetime(now.year+1,1,1) if now.month==12 else datetime(now.year,now.month+1,1)
    elif key=='all':
        start=datetime(2000,1,1);end=now+timedelta(seconds=1)
    else:return None
    return start.isoformat(timespec='seconds'),end.isoformat(timespec='seconds')


def _period_stats(conn,start,end,now):
    earned=_lesson_earned_expr('l')
    planned=conn.execute(f"""SELECT COUNT(*) c,COALESCE(SUM({earned}),0) s FROM lessons l WHERE l.start_time>=? AND l.start_time<? AND l.lesson_status NOT IN ('CANCELLED','REJECTED')""",(start,end)).fetchone()
    worked=conn.execute(f"""SELECT COUNT(*) c,COALESCE(SUM({earned}),0) s FROM lessons l WHERE l.start_time>=? AND l.start_time<? AND l.lesson_status='COMPLETED'""",(start,end)).fetchone()
    remaining=conn.execute(f"""SELECT COUNT(*) c,COALESCE(SUM({earned}),0) s FROM lessons l WHERE l.start_time>=? AND l.start_time<? AND l.start_time>=? AND l.lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')""",(start,end,now)).fetchone()
    expected=conn.execute(f"""SELECT COUNT(*) c,COALESCE(SUM({earned}),0) s FROM lessons l WHERE l.start_time>=? AND l.start_time<? AND l.start_time>=? AND l.lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED') AND COALESCE(l.payment_status,'WAITING') NOT IN ('PAID','FREE','RESERVED_BALANCE','TRANSFERRED')""",(start,end,now)).fetchone()
    paid_future=conn.execute(f"""SELECT COUNT(*) c,COALESCE(SUM({earned}),0) s FROM lessons l WHERE l.start_time>=? AND l.start_time<? AND l.start_time>=? AND l.lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED') AND COALESCE(l.payment_status,'') IN ('PAID','FREE','RESERVED_BALANCE','TRANSFERRED')""",(start,end,now)).fetchone()
    received=conn.execute("""SELECT COUNT(*) c,COALESCE(SUM(COALESCE(total_amount,0)),0) s FROM payments WHERE status='PAID' AND confirmed_at IS NOT NULL AND confirmed_at>=? AND confirmed_at<?""",(start,end)).fetchone()
    prepaid=conn.execute("""SELECT COUNT(*) c,COALESCE(SUM(COALESCE(l.price,0)),0) s FROM lessons l LEFT JOIN lesson_packages lp ON lp.id=l.package_id LEFT JOIN payments p ON p.id=COALESCE(l.payment_id,lp.payment_id) WHERE l.start_time>=? AND l.start_time<? AND l.lesson_status NOT IN ('CANCELLED','REJECTED') AND l.payment_status='PAID' AND p.status='PAID' AND COALESCE(p.confirmed_at,p.created_at)<?""",(start,end,start)).fetchone()
    prepaid_remaining=conn.execute("""SELECT COUNT(*) c,COALESCE(SUM(COALESCE(l.price,0)),0) s FROM lessons l LEFT JOIN lesson_packages lp ON lp.id=l.package_id LEFT JOIN payments p ON p.id=COALESCE(l.payment_id,lp.payment_id) WHERE l.start_time>=? AND l.start_time<? AND l.start_time>=? AND l.lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED') AND l.payment_status='PAID' AND p.status='PAID' AND COALESCE(p.confirmed_at,p.created_at)<?""",(start,end,now,start)).fetchone()
    return {
      'planned':{'lessons':int(planned['c'] or 0),'amount':int(planned['s'] or 0)},
      'worked':{'lessons':int(worked['c'] or 0),'amount':int(worked['s'] or 0)},
      'remaining':{'lessons':int(remaining['c'] or 0),'amount':int(remaining['s'] or 0)},
      'expected_to_receive':{'lessons':int(expected['c'] or 0),'amount':int(expected['s'] or 0)},
      'future_already_paid':{'lessons':int(paid_future['c'] or 0),'amount':int(paid_future['s'] or 0)},
      'received_confirmed':{'payments':int(received['c'] or 0),'amount':int(received['s'] or 0)},
      'already_paid_before_period':{'lessons':int(prepaid['c'] or 0),'amount':int(prepaid['s'] or 0)},
      'remaining_already_prepaid':{'lessons':int(prepaid_remaining['c'] or 0),'amount':int(prepaid_remaining['s'] or 0)},
    }


def calendar_analytics(now_value=None):
    now=datetime.fromisoformat(str(now_value)) if now_value else datetime.now();now_iso=now.isoformat(timespec='seconds');conn=connect()
    ws,we=_period_bounds('week',now);ms,me=_period_bounds('month',now)
    week=_period_stats(conn,ws,we,now_iso);month=_period_stats(conn,ms,me,now_iso);conn.close()
    return {'as_of':now_iso,'week':{'start':ws,'end':we,**week},'month':{'start':ms,'end':me,**month}}


def dashboard(start=None,end=None,period=None):
    bounds=_period_bounds(period) if period else None
    if bounds:start,end=bounds
    else:start,end=_iso_start(start),_iso_end(end)
    conn=connect()
    paid=conn.execute("SELECT COUNT(*) c,COALESCE(SUM(total_amount),0) s FROM payments WHERE status='PAID' AND COALESCE(confirmed_at,created_at)>=? AND COALESCE(confirmed_at,created_at)<?",(start,end)).fetchone()
    waiting=conn.execute("SELECT COUNT(*) c,COALESCE(SUM(total_amount),0) s FROM payments WHERE status IN ('WAITING','PENDING')",()).fetchone()
    earned=_lesson_earned_expr('l');funding=_lesson_funding_expr('l')
    lessons=conn.execute(f"SELECT COUNT(*) c,COALESCE(SUM({earned}),0) s FROM lessons l WHERE l.lesson_status='COMPLETED' AND l.start_time>=? AND l.start_time<?",(start,end)).fetchone()
    balances=conn.execute("SELECT COALESCE(SUM(CASE WHEN status='ACTIVE' THEN lessons_total-lessons_used ELSE 0 END),0) lessons_left,COALESCE(SUM(CASE WHEN status='ACTIVE' THEN (lessons_total-lessons_used)*price_per_lesson ELSE 0 END),0) nominal_left FROM lesson_packages").fetchone()
    completed=[dict(r) for r in conn.execute(f"""SELECT l.id,l.user_id,u.name,l.start_time,l.subject,l.study_goal,l.duration_minutes,COALESCE(l.price,0) price,{earned} earned_value,{funding} funding_kind,l.payment_status,l.lesson_status FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.lesson_status='COMPLETED' AND l.start_time>=? AND l.start_time<? AND COALESCE(l.price,0)>0 ORDER BY l.start_time DESC,l.id DESC LIMIT 200""",(start,end)).fetchall()]
    recent=[dict(r) for r in conn.execute("""SELECT p.id,p.user_id,u.name,p.study_goal,p.subject,p.lessons_count,p.price_per_lesson,p.total_amount,p.status,p.promo_code,p.promo_discount_amount,p.created_at,p.confirmed_at FROM payments p JOIN users u ON u.id=p.user_id WHERE COALESCE(p.confirmed_at,p.created_at)>=? AND COALESCE(p.confirmed_at,p.created_at)<? AND COALESCE(p.total_amount,0)>0 ORDER BY COALESCE(p.confirmed_at,p.created_at) DESC,p.id DESC LIMIT 100""",(start,end)).fetchall()]
    conn.close()
    return {'period':{'key':period or 'custom','start':start,'end':end},'paid':{'count':int(paid['c'] or 0),'amount':int(paid['s'] or 0)},'waiting':{'count':int(waiting['c'] or 0),'amount':int(waiting['s'] or 0)},'lessons':{'completed':int(lessons['c'] or 0),'value':int(lessons['s'] or 0)},'prepaid_balance':{'lessons_left':int(balances['lessons_left'] or 0),'nominal_left':int(balances['nominal_left'] or 0)},'completed_lessons':completed,'recent_payments':recent}



def mark_lesson_paid(lesson_id,amount=None,actor_id=None):
    lesson=database.get_lesson(int(lesson_id))
    if lesson is None:raise ValueError('lesson_not_found')
    if str(lesson['lesson_status'] or '').upper() in {'CANCELLED','REJECTED'}:raise ValueError('lesson_not_payable')
    status=str(lesson['payment_status'] or '').upper()
    if status in {'PAID','FREE','RESERVED_BALANCE','TRANSFERRED'}:
        return {'status':'already_paid','lesson_id':int(lesson_id),'payment_status':status,'payment_id':lesson['payment_id']}
    existing=database.get_payment_for_lesson(int(lesson_id))
    if existing is not None:
        raise ValueError('linked_invoice_requires_review')
    payment_id,package_id=database.confirm_manual_lesson_payment(int(lesson_id),None if amount in (None,'') else int(amount),actor_id=actor_id,source='TEACHER_WEB')
    return {'status':'ok','lesson_id':int(lesson_id),'payment_status':'PAID','payment_id':int(payment_id),'package_id':int(package_id)}


def student_finance(user_id):
    uid=int(user_id);conn=connect();user=conn.execute('SELECT id,name FROM users WHERE id=?',(uid,)).fetchone()
    if not user:conn.close();raise ValueError('student_not_found')
    payments=[dict(r) for r in conn.execute("SELECT id,study_goal,subject,lessons_count,price_per_lesson,total_amount,status,promo_code,promo_discount_amount,created_at,confirmed_at FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 50",(uid,)).fetchall()]
    packages=[dict(r) for r in conn.execute("SELECT id,payment_id,study_goal,subject,lessons_total,lessons_used,price_per_lesson,discount_percent,status,source_type,created_at FROM lesson_packages WHERE user_id=? ORDER BY id DESC LIMIT 50",(uid,)).fetchall()]
    earned=_lesson_earned_expr('l');funding=_lesson_funding_expr('l')
    lessons=[dict(r) for r in conn.execute(f"SELECT l.id,l.start_time,l.duration_minutes,l.subject,l.study_goal,l.hourly_rate,l.price,{earned} earned_value,{funding} funding_kind,l.payment_status,l.lesson_status,l.payment_id,l.package_id FROM lessons l WHERE l.user_id=? ORDER BY l.start_time DESC LIMIT 50",(uid,)).fetchall()]
    totals=conn.execute("SELECT COALESCE(SUM(CASE WHEN status='PAID' THEN total_amount ELSE 0 END),0) paid,COALESCE(SUM(CASE WHEN status IN ('WAITING','PENDING') THEN total_amount ELSE 0 END),0) waiting FROM payments WHERE user_id=?",(uid,)).fetchone();conn.close()
    left=sum(max(0,int(x.get('lessons_total') or 0)-int(x.get('lessons_used') or 0)) for x in packages if str(x.get('status') or '').upper()=='ACTIVE')
    return {'student':dict(user),'totals':{'paid':int(totals['paid'] or 0),'waiting':int(totals['waiting'] or 0),'lessons_left':left},'payments':payments,'packages':packages,'lessons':lessons}
