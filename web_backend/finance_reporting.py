"""Read-only Stage 8 finance reporting over existing TutorBot money tables."""
from __future__ import annotations
from datetime import datetime, timedelta
from database import connect

PAID={'PAID','CONFIRMED','APPROVED'}
PENDING={'WAITING','PENDING','REVIEW'}
EXCLUDED_LESSON_STATUSES={'CANCELLED','REJECTED'}


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


def _period_stats(conn,start,end,now):
    """Return planned, already worked and still-to-work value for a calendar period.

    lesson.price is an immutable snapshot, therefore changing tariffs later does
    not rewrite these historical/forecast numbers.
    """
    planned=conn.execute("""
      SELECT COUNT(*) c,COALESCE(SUM(COALESCE(price,0)),0) s
      FROM lessons
      WHERE start_time>=? AND start_time<?
        AND lesson_status NOT IN ('CANCELLED','REJECTED')
    """,(start,end)).fetchone()
    worked=conn.execute("""
      SELECT COUNT(*) c,COALESCE(SUM(COALESCE(price,0)),0) s
      FROM lessons
      WHERE start_time>=? AND start_time<? AND lesson_status='COMPLETED'
    """,(start,end)).fetchone()
    remaining=conn.execute("""
      SELECT COUNT(*) c,COALESCE(SUM(COALESCE(price,0)),0) s
      FROM lessons
      WHERE start_time>=? AND start_time<? AND start_time>=?
        AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')
    """,(start,end,now)).fetchone()
    return {
      'planned':{'lessons':int(planned['c'] or 0),'amount':int(planned['s'] or 0)},
      'worked':{'lessons':int(worked['c'] or 0),'amount':int(worked['s'] or 0)},
      'remaining':{'lessons':int(remaining['c'] or 0),'amount':int(remaining['s'] or 0)},
    }


def calendar_analytics(now_value=None):
    now=datetime.fromisoformat(str(now_value)) if now_value else datetime.now()
    monday=datetime.combine(now.date()-timedelta(days=now.weekday()),datetime.min.time())
    week_end=monday+timedelta(days=7)
    month_start=datetime(now.year,now.month,1)
    if now.month==12:month_end=datetime(now.year+1,1,1)
    else:month_end=datetime(now.year,now.month+1,1)
    now_iso=now.isoformat(timespec='seconds');conn=connect()
    week=_period_stats(conn,monday.isoformat(timespec='seconds'),week_end.isoformat(timespec='seconds'),now_iso)
    month=_period_stats(conn,month_start.isoformat(timespec='seconds'),month_end.isoformat(timespec='seconds'),now_iso)
    conn.close()
    return {
      'as_of':now_iso,
      'week':{'start':monday.isoformat(timespec='seconds'),'end':week_end.isoformat(timespec='seconds'),**week},
      'month':{'start':month_start.isoformat(timespec='seconds'),'end':month_end.isoformat(timespec='seconds'),**month},
    }


def dashboard(start=None,end=None):
    start=_iso_start(start);end=_iso_end(end);conn=connect()
    paid=conn.execute("SELECT COUNT(*) c,COALESCE(SUM(total_amount),0) s FROM payments WHERE status='PAID' AND COALESCE(confirmed_at,created_at)>=? AND COALESCE(confirmed_at,created_at)<?",(start,end)).fetchone()
    waiting=conn.execute("SELECT COUNT(*) c,COALESCE(SUM(total_amount),0) s FROM payments WHERE status IN ('WAITING','PENDING')",()).fetchone()
    lessons=conn.execute("SELECT COUNT(*) c,COALESCE(SUM(price),0) s FROM lessons WHERE lesson_status='COMPLETED' AND start_time>=? AND start_time<?",(start,end)).fetchone()
    balances=conn.execute("SELECT COALESCE(SUM(CASE WHEN status='ACTIVE' THEN lessons_total-lessons_used ELSE 0 END),0) lessons_left,COALESCE(SUM(CASE WHEN status='ACTIVE' THEN (lessons_total-lessons_used)*price_per_lesson ELSE 0 END),0) nominal_left FROM lesson_packages").fetchone()
    recent=[dict(r) for r in conn.execute("SELECT p.id,p.user_id,u.name,p.study_goal,p.subject,p.lessons_count,p.price_per_lesson,p.total_amount,p.status,p.promo_code,p.promo_discount_amount,p.created_at,p.confirmed_at FROM payments p JOIN users u ON u.id=p.user_id ORDER BY p.id DESC LIMIT 30").fetchall()]
    conn.close();return {'period':{'start':start,'end':end},'paid':{'count':int(paid['c'] or 0),'amount':int(paid['s'] or 0)},'waiting':{'count':int(waiting['c'] or 0),'amount':int(waiting['s'] or 0)},'lessons':{'completed':int(lessons['c'] or 0),'value':int(lessons['s'] or 0)},'prepaid_balance':{'lessons_left':int(balances['lessons_left'] or 0),'nominal_left':int(balances['nominal_left'] or 0)},'recent_payments':recent}


def student_finance(user_id):
    uid=int(user_id);conn=connect();user=conn.execute('SELECT id,name FROM users WHERE id=?',(uid,)).fetchone()
    if not user:conn.close();raise ValueError('student_not_found')
    payments=[dict(r) for r in conn.execute("SELECT id,study_goal,subject,lessons_count,price_per_lesson,total_amount,status,promo_code,promo_discount_amount,created_at,confirmed_at FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 50",(uid,)).fetchall()]
    packages=[dict(r) for r in conn.execute("SELECT id,payment_id,study_goal,subject,lessons_total,lessons_used,price_per_lesson,discount_percent,status,source_type,created_at FROM lesson_packages WHERE user_id=? ORDER BY id DESC LIMIT 50",(uid,)).fetchall()]
    lessons=[dict(r) for r in conn.execute("SELECT id,start_time,duration_minutes,subject,study_goal,hourly_rate,price,payment_status,lesson_status,payment_id,package_id FROM lessons WHERE user_id=? ORDER BY start_time DESC LIMIT 50",(uid,)).fetchall()]
    totals=conn.execute("SELECT COALESCE(SUM(CASE WHEN status='PAID' THEN total_amount ELSE 0 END),0) paid,COALESCE(SUM(CASE WHEN status IN ('WAITING','PENDING') THEN total_amount ELSE 0 END),0) waiting FROM payments WHERE user_id=?",(uid,)).fetchone();conn.close()
    left=sum(max(0,int(x.get('lessons_total') or 0)-int(x.get('lessons_used') or 0)) for x in packages if str(x.get('status') or '').upper()=='ACTIVE')
    return {'student':dict(user),'totals':{'paid':int(totals['paid'] or 0),'waiting':int(totals['waiting'] or 0),'lessons_left':left},'payments':payments,'packages':packages,'lessons':lessons}
