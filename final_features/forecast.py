from __future__ import annotations

from datetime import date, datetime, timedelta

import database
from core import effective_pricing, minute_balance


def finance(month=None):
    d = date.today() if month is None else datetime.strptime(month + '-01', '%Y-%m-%d').date()
    start = d.replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)

    start_iso = start.isoformat()
    end_iso = end.isoformat()
    now_iso = datetime.now().isoformat(timespec='seconds')

    c = database.connect()
    try:
        received = c.execute(
            """
            SELECT COALESCE(SUM(total_amount),0) s
            FROM payments
            WHERE status IN ('PAID','CONFIRMED')
              AND confirmed_at>=?
              AND confirmed_at<?
            """,
            (start_iso, end_iso),
        ).fetchone()['s'] or 0

        # Fact: effective individual rate x actual worked duration where known.
        earned = effective_pricing.earned_amount(start_iso, end_iso)

        # Forecast: current effective individual rate x planned future duration.
        future_rows = effective_pricing.future_lesson_rows(now_iso, end_iso)
        future_earned = effective_pricing.sum_effective_prices(future_rows)
        future_minutes = sum(int(r['duration_minutes'] or 0) for r in future_rows)

        students = c.execute(
            "SELECT COUNT(*) n FROM users WHERE active=1"
        ).fetchone()['n']

        return {
            'received': int(received),
            'earned': int(earned),
            'future_earned': int(future_earned),
            'future_minutes': int(future_minutes),
            'projected_earned': int(earned) + int(future_earned),
            'prepaid': minute_balance.prepaid_value_rubles(),
            'active_students': int(students or 0),
        }
    finally:
        c.close()
