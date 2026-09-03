from datetime import datetime, timedelta

import database
from core import effective_pricing


def period_bounds(period):
    now = datetime.now()
    if period == 'day':
        start = datetime.combine(now.date(), datetime.min.time())
        end = start + timedelta(days=1)
    elif period == 'week':
        start = datetime.combine(now.date() - timedelta(days=now.weekday()), datetime.min.time())
        end = start + timedelta(days=7)
    elif period == 'month':
        start = datetime(now.year, now.month, 1)
        end = datetime(now.year + (now.month == 12), 1 if now.month == 12 else now.month + 1, 1)
    else:
        return None, None
    return start, end


def financial_stats(start=None, end=None):
    conn = database.connect()
    params = []
    payment_where = "status IN ('PAID','CONFIRMED')"
    lesson_where = "lesson_status='COMPLETED' AND finished_at IS NOT NULL AND cancelled_at IS NULL"

    if start:
        payment_where += " AND COALESCE(confirmed_at,created_at)>=?"
        lesson_where += " AND finished_at>=?"
        params.append(start)
    if end:
        payment_where += " AND COALESCE(confirmed_at,created_at)<?"
        lesson_where += " AND finished_at<?"

    pay_params = list(params)
    lesson_params = list(params)
    if end:
        pay_params.append(end)
        lesson_params.append(end)

    received = conn.execute(
        f"SELECT COALESCE(SUM(total_amount),0) v FROM payments WHERE {payment_where}",
        pay_params,
    ).fetchone()['v']

    # Earned revenue is based on each student's effective individual rate.
    # Actual worked minutes are used when they were recorded.
    earned = effective_pricing.earned_amount(start, end)

    completed = conn.execute(
        f"SELECT COUNT(*) v FROM lessons WHERE {lesson_where}", lesson_params
    ).fetchone()['v']
    minutes = conn.execute(
        f"SELECT COALESCE(SUM(CASE WHEN actual_duration_minutes>0 THEN actual_duration_minutes ELSE duration_minutes END),0) v FROM lessons WHERE {lesson_where}",
        lesson_params,
    ).fetchone()['v']

    try:
        from core.minute_balance import prepaid_value_rubles
        prepaid = prepaid_value_rubles()
    except Exception:
        prepaid = conn.execute("""
            SELECT COALESCE(SUM(
                CASE
                    WHEN lessons_total>lessons_used
                    THEN (lessons_total-lessons_used)*price_per_lesson
                    ELSE 0
                END
            ),0) v
            FROM lesson_packages
            WHERE status='ACTIVE'
        """).fetchone()['v']

    active = conn.execute("SELECT COUNT(*) v FROM users WHERE active=1").fetchone()['v']
    conn.close()

    return {
        'received': int(received or 0),
        'earned': int(earned or 0),
        'prepaid': int(prepaid or 0),
        'completed': int(completed or 0),
        'minutes': int(minutes or 0),
        'active_users': int(active or 0),
    }
