from __future__ import annotations

from core import payment_reminder_routing as routing


class Row(dict):
    def keys(self):
        return super().keys()


def run():
    original_get_parents = routing.database.get_student_parents
    original_get_user = routing.database.get_user
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

        print('PAYMENT_REMINDER_ROUTING_SELFTEST_PASSED')
    finally:
        routing.database.get_student_parents = original_get_parents
        routing.database.get_user = original_get_user


if __name__ == '__main__':
    run()
