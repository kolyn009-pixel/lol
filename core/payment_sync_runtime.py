from __future__ import annotations

"""Runtime hooks that reconcile lesson integrations after successful payments.

Payment mutations live in legacy database helpers used by Telegram, web and VK.
Wrapping those helpers in one place means every channel gets identical behavior:
local payment state commits first, then Calendar/Telemost reconciliation runs as a
best-effort side effect. Provider outages never roll back a confirmed payment.
"""

import database
from core import schedule_sync

_INSTALLED = False


def _sync(ids):
    lesson_ids = [int(x) for x in ids if x]
    if not lesson_ids:
        return
    try:
        result = schedule_sync.sync_lessons_blocking(lesson_ids)
        if result.get("failed"):
            print("PAYMENT LESSON SYNC WARN:", result["failed"], flush=True)
    except Exception as exc:
        print("PAYMENT LESSON SYNC ERROR:", type(exc).__name__, flush=True)


def install():
    global _INSTALLED
    if _INSTALLED:
        return

    original_approve_payment = database.approve_payment
    original_approve_draft = database.approve_paid_booking_draft_payment
    original_charge_reserved = database.charge_reserved_lesson

    def approve_payment(payment_id, *args, **kwargs):
        result = original_approve_payment(payment_id, *args, **kwargs)
        try:
            payment = database.get_payment(int(payment_id))
            lesson_id = payment["lesson_id"] if payment and "lesson_id" in payment.keys() else None
            _sync([lesson_id])
        except Exception as exc:
            print("PAYMENT DIRECT LESSON SYNC ERROR:", int(payment_id), type(exc).__name__, flush=True)
        return result

    def approve_paid_booking_draft_payment(payment_id, *args, **kwargs):
        result = original_approve_draft(payment_id, *args, **kwargs)
        try:
            if result is not None:
                _package_id, lesson_id = result
                _sync([lesson_id])
        except Exception as exc:
            print("PAYMENT DRAFT LESSON SYNC ERROR:", int(payment_id), type(exc).__name__, flush=True)
        return result

    def charge_reserved_lesson(lesson_id, *args, **kwargs):
        result = original_charge_reserved(lesson_id, *args, **kwargs)
        _sync([lesson_id])
        return result

    approve_payment._adelia_payment_sync = True
    approve_paid_booking_draft_payment._adelia_payment_sync = True
    charge_reserved_lesson._adelia_payment_sync = True

    database.approve_payment = approve_payment
    database.approve_paid_booking_draft_payment = approve_paid_booking_draft_payment
    database.charge_reserved_lesson = charge_reserved_lesson
    _INSTALLED = True
