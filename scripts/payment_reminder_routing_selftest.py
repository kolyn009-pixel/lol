from __future__ import annotations

import asyncio
import inspect

import database
from core import payment_reminder_routing as routing
from core import payment_wait_control
from web_backend import push_events


class Row(dict):
    def keys(self):
        return super().keys()


class Job:
    def __init__(self, data):
        self.data = data


class Context:
    def __init__(self, data):
        self.job = Job(data)
        self.bot = object()


legacy_deadline_calls = 0


async def payment_reminder_job(context):
    return None


async def payment_deadline_job(context):
    global legacy_deadline_calls
    legacy_deadline_calls += 1


def run():
    global legacy_deadline_calls, payment_deadline_job

    original_get_parents = routing.database.get_student_parents
    original_get_user = routing.database.get_user
    original_get_lesson = routing.database.get_lesson
    original_wait_get = payment_wait_control.get
    original_mark_risk = payment_wait_control.mark_risk
    original_notify_teacher = routing._notify_teacher
    original_teacher_push = push_events.teachers
    original_installed = routing._INSTALLED
    original_deadline = payment_deadline_job

    state = {}

    try:
        routing.database.get_student_parents = lambda student_id: [
            Row(id=1, telegram_id=111, active=1),
            Row(id=2, telegram_id=222, active=1),
        ]
        routing.database.get_user = lambda student_id: Row(id=student_id, parent_telegram_id=999)
        assert routing.parent_telegram_ids(10) == [111, 222]
        assert routing.has_parent_recipient(10) is True

        routing.database.get_student_parents = lambda student_id: []
        routing.database.get_user = lambda student_id: Row(id=student_id, parent_telegram_id=333)
        assert routing.parent_telegram_ids(10) == [333]
        assert routing.has_parent_recipient(10) is True

        routing.database.get_student_parents = lambda student_id: []
        routing.database.get_user = lambda student_id: Row(id=student_id, parent_telegram_id=None)
        assert routing.parent_telegram_ids(10) == []
        assert routing.has_parent_recipient(10) is False

        routing.database.get_student_parents = lambda student_id: [
            Row(id=1, telegram_id=444, active=1),
            Row(id=2, telegram_id=444, active=1),
            Row(id=3, telegram_id=None, active=1),
        ]
        assert routing.parent_telegram_ids(10) == [444]

        lesson = Row(
            id=77,
            user_id=10,
            lesson_status='CONFIRMED',
            payment_status='AWAITING_PAYMENT',
        )
        routing.database.get_lesson = lambda lesson_id: lesson if int(lesson_id) == 77 else None
        payment_wait_control.get = lambda lesson_id: dict(state) if state else None

        def mark_risk(lesson_id):
            state.setdefault('risk_notified_at', '2026-09-17T10:00:00')
            return dict(state)

        payment_wait_control.mark_risk = mark_risk

        async def no_notify(context, lesson_id, current_lesson):
            return None

        routing._notify_teacher = no_notify
        push_events.teachers = lambda *args, **kwargs: {'status': 'ok', 'targets': 0, 'sent': 0, 'failed': 0}

        routing._INSTALLED = False
        legacy_deadline_calls = 0
        routing.install()

        assert getattr(payment_deadline_job, '_adelia_teacher_payment_decision', False) is True
        asyncio.run(payment_deadline_job(Context({'lesson_id': 77})))
        assert legacy_deadline_calls == 0, 'T-2h must not auto-cancel before teacher decision'
        assert state.get('risk_notified_at'), 'T-2h must persist payment risk state'

        state['teacher_wait_confirmed_at'] = '2026-09-17T10:01:00'
        asyncio.run(payment_deadline_job(Context({'lesson_id': 77})))
        assert legacy_deadline_calls == 0, 'teacher wait override must suppress legacy auto-cancel'

        start_source = inspect.getsource(database.start_lesson)
        assert 'AWAITING_PAYMENT' in start_source
        assert 'Занятие ещё не оплачено.' in start_source

        print('PAYMENT_REMINDER_ROUTING_SELFTEST_PASSED')
    finally:
        routing.database.get_student_parents = original_get_parents
        routing.database.get_user = original_get_user
        routing.database.get_lesson = original_get_lesson
        payment_wait_control.get = original_wait_get
        payment_wait_control.mark_risk = original_mark_risk
        routing._notify_teacher = original_notify_teacher
        push_events.teachers = original_teacher_push
        routing._INSTALLED = original_installed
        payment_deadline_job = original_deadline


if __name__ == '__main__':
    run()
