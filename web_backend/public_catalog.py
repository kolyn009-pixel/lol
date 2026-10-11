"""Public catalog helpers for adeliatutor.ru.

The website must never hardcode lesson prices. Active directions and rates are
read from the teacher price_catalog (including duration), with price_settings as
a legacy fallback, so updates appear without a frontend rebuild.
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
    items = {
        row['rate_key']:
        {
            "key": row["rate_key"],
            "goal": row["study_goal"],
            "subject": row["subject"],
            "grade_min": row["grade_min"],
            "grade_max": row["grade_max"],
            "hourly_rate": int(row["hourly_rate"]),
            "amount": int(row["hourly_rate"]),
            "duration_minutes": 60,
            "title": row["title"],
        }
        for row in rows
    }
    # The teacher editor stores amount AND duration in price_catalog. Prefer
    # that source, including deactivation and college, over legacy hourly rows.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='price_catalog'").fetchone():
        for row in conn.execute('SELECT * FROM price_catalog').fetchall():
            key = row['tariff_key']
            if not row['active']:
                items.pop(key, None)
                continue
            duration = int(row['duration_minutes'] or 60)
            old = items.get(key, {})
            items[key] = {**old, 'key': key, 'title': row['title'],
                          'goal': row['study_goal'], 'subject': row['subject'],
                          'grade_min': old.get('grade_min'), 'grade_max': old.get('grade_max'),
                          'amount': int(row['amount']), 'duration_minutes': duration,
                          'hourly_rate': round(int(row['amount']) * 60 / duration)}
    conn.close()
    return list(items.values())
