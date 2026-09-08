"""Public catalog helpers for adeliatutor.ru.

The website must never hardcode lesson prices. Active directions and rates are
read from TutorBot's existing price_settings table so changes in admin/DB are
reflected on the public site without a frontend rebuild.
"""

from database import connect


def get_public_price_catalog():
    conn = connect()
    rows = conn.execute(
        """
        SELECT rate_key, study_goal, subject, grade_min, grade_max,
               hourly_rate, title
        FROM price_settings
        WHERE active = 1
        ORDER BY
            CASE study_goal
                WHEN 'OLYMPIAD' THEN 1
                WHEN 'EGE' THEN 2
                WHEN 'OGE' THEN 3
                WHEN 'SCHOOL' THEN 4
                ELSE 9
            END,
            title COLLATE NOCASE
        """
    ).fetchall()
    conn.close()
    return [
        {
            "key": row["rate_key"],
            "goal": row["study_goal"],
            "subject": row["subject"],
            "grade_min": row["grade_min"],
            "grade_max": row["grade_max"],
            "hourly_rate": int(row["hourly_rate"]),
            "title": row["title"],
        }
        for row in rows
    ]
