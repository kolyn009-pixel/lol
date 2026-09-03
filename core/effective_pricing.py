from __future__ import annotations

from datetime import datetime

import database


def _row_value(row, key, default=None):
    try:
        return row[key]
    except Exception:
        return default


def effective_hourly_rate(row):
    """Return the current effective rate for a lesson/program.

    Individual program price has priority over the common tariff. Legacy
    student-level individual rates are used only when the lesson is not linked
    to a student_program yet.
    """
    program_id = _row_value(row, "program_id")
    if program_id:
        return int(database.get_program_rate_info(int(program_id))["effective_rate"])

    return int(
        database.get_student_rate_info(
            int(_row_value(row, "user_id")),
            _row_value(row, "study_goal"),
            _row_value(row, "subject"),
        )["effective_rate"]
    )


def effective_lesson_price(row, use_actual_duration=False):
    """Calculate a lesson value from the effective individual rate.

    For completed lessons use_actual_duration=True makes earned revenue follow
    the actual worked minutes when they are recorded. For planned lessons the
    scheduled duration is used.
    """
    stored = int(_row_value(row, "price", 0) or 0)
    try:
        duration = int(_row_value(row, "duration_minutes", 60) or 60)
        if use_actual_duration:
            actual = int(_row_value(row, "actual_duration_minutes", 0) or 0)
            if actual > 0:
                duration = actual
        hourly = effective_hourly_rate(row)
        return int(database.calculate_lesson_price(hourly, duration))
    except Exception:
        return stored


def sum_effective_prices(rows, use_actual_duration=False):
    return sum(
        effective_lesson_price(row, use_actual_duration=use_actual_duration)
        for row in rows
    )


def completed_lesson_rows(start=None, end=None):
    c = database.connect()
    try:
        sql = """
            SELECT
                l.id,
                l.user_id,
                l.program_id,
                l.study_goal,
                l.subject,
                l.price,
                l.duration_minutes,
                l.actual_duration_minutes,
                l.finished_at
            FROM lessons l
            WHERE l.lesson_status='COMPLETED'
              AND l.finished_at IS NOT NULL
              AND l.cancelled_at IS NULL
        """
        params = []
        if start:
            sql += " AND l.finished_at>=?"
            params.append(start)
        if end:
            sql += " AND l.finished_at<?"
            params.append(end)
        sql += " ORDER BY l.finished_at"
        return c.execute(sql, tuple(params)).fetchall()
    finally:
        c.close()


def future_lesson_rows(start=None, end=None):
    c = database.connect()
    try:
        sql = """
            SELECT
                l.id,
                l.user_id,
                l.program_id,
                l.study_goal,
                l.subject,
                l.price,
                l.duration_minutes,
                l.actual_duration_minutes,
                l.start_time
            FROM lessons l
            JOIN users u ON u.id=l.user_id
            WHERE u.active=1
              AND l.cancelled_at IS NULL
              AND l.finished_at IS NULL
              AND l.lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS')
        """
        params = []
        if start:
            sql += " AND l.start_time>=?"
            params.append(start)
        if end:
            sql += " AND l.start_time<?"
            params.append(end)
        sql += " ORDER BY l.start_time"
        return c.execute(sql, tuple(params)).fetchall()
    finally:
        c.close()


def earned_amount(start=None, end=None):
    return int(sum_effective_prices(
        completed_lesson_rows(start, end),
        use_actual_duration=True,
    ))


def projected_amount(start=None, end=None):
    return int(sum_effective_prices(
        future_lesson_rows(start, end),
        use_actual_duration=False,
    ))
