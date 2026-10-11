"""Resolve an individual student's price before issuing an unpaid lesson invoice.

An already-created payment is immutable: a later tariff change must not silently
rewrite an amount the family has already seen.
"""
from __future__ import annotations

from web_backend import finance_price_sync

INDIVIDUAL_SOURCES = {'STUDENT_OVERRIDE', 'STUDENT_PROGRAM', 'LEGACY_USER_RATE'}


def individual_lesson_quote(lesson):
    keys = lesson.keys() if hasattr(lesson, 'keys') else lesson
    try:
        uid = int(lesson['user_id'])
        duration = int(lesson['duration_minutes'] or 60) if 'duration_minutes' in keys else 60
        quote = finance_price_sync.quote(
            uid, duration_minutes=duration,
            study_goal=lesson['study_goal'], subject=lesson['subject'],
        )
    except (ValueError, TypeError, KeyError):
        return None
    if quote.get('source') not in INDIVIDUAL_SOURCES:
        return None
    amount = int(quote.get('amount') or 0)
    if amount <= 0:
        return None
    return {'amount': amount, 'source': quote['source'], 'duration_minutes': duration}
