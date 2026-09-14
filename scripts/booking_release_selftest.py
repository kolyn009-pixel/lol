from __future__ import annotations

import inspect

from web_backend import api_v6, student_regular_booking, teacher_request_center, trial_approval_atomic


def run():
    # Recurring booking contract.
    assert student_regular_booking.MAX_WEEKLY == 7
    source = inspect.getsource(student_regular_booking.create_group)
    assert "BEGIN IMMEDIATE" in source
    assert "request_group" in source
    assert "slot_unavailable" in source
    assert "duplicate_weekly_slot" in source

    # Grouping shown to the teacher must keep all slots from one request together.
    rows = [
        {"id": 1, "request_group": "RS-TEST", "user_id": 10, "name": "Иван", "grade": 9,
         "subject": "PHYSICS", "study_goal": "OGE", "region": None, "timezone": None,
         "created_at": "2026-09-14T09:00:00", "weekday": 1, "start_time": "17:00",
         "duration_minutes": 60},
        {"id": 2, "request_group": "RS-TEST", "user_id": 10, "name": "Иван", "grade": 9,
         "subject": "PHYSICS", "study_goal": "OGE", "region": None, "timezone": None,
         "created_at": "2026-09-14T09:00:00", "weekday": 3, "start_time": "18:00",
         "duration_minutes": 60},
        {"id": 3, "request_group": None, "user_id": 11, "name": "Анна", "grade": 10,
         "subject": "PHYSICS", "study_goal": "EGE", "region": None, "timezone": None,
         "created_at": "2026-09-14T09:01:00", "weekday": 5, "start_time": "12:00",
         "duration_minutes": 90},
    ]
    groups = teacher_request_center._schedule_groups(rows)
    assert len(groups) == 2
    assert groups[0]["request_group"] == "RS-TEST"
    assert groups[0]["weekly_count"] == 2
    assert [x["id"] for x in groups[0]["items"]] == [1, 2]
    assert groups[1]["weekly_count"] == 1

    # The real API must expose recurring booking and override inherited trial approval.
    api_source = inspect.getsource(api_v6.Handler.do_POST)
    assert "/api/student/booking/regular" in api_source
    assert "student_regular_booking.create_group" in api_source
    assert "/api/teacher/trial/approve" in api_source
    assert "trial_approval_atomic.approve" in api_source

    # Trial approval must re-check availability while holding the write reservation.
    trial_source = inspect.getsource(trial_approval_atomic.approve)
    assert "BEGIN IMMEDIATE" in trial_source
    assert "availability_guard.conflicts" in trial_source
    assert "ignore_trial_id=rid" in trial_source
    assert "trial_slot_taken" in trial_source

    print("BOOKING_RELEASE_SELFTEST_PASSED")


if __name__ == "__main__":
    run()
