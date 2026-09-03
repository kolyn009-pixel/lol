from __future__ import annotations

import os
import tempfile
from datetime import date

fd, path = tempfile.mkstemp(prefix="tutorbot_schedule_", suffix=".db")
os.close(fd)
os.unlink(path)
os.environ["TUTORBOT_TEST_DB"] = path

import database  # noqa: E402


def main():
    database.set_test_mode(True)
    database.create_tables()

    assert database.teacher_week_kind(date(2026, 9, 1)) == "ODD"
    assert database.teacher_week_kind(date(2026, 9, 7)) == "EVEN"
    assert database.teacher_week_kind(date(2026, 9, 14)) == "ODD"

    database.set_setting("teacher_week_mode", "ALTERNATING")
    database.add_working_hours(0, "10:00", "12:00", "ALL")
    assert len(database.get_effective_working_hours(date(2026, 9, 7))) == 1

    database.add_working_hours(0, "14:00", "18:00", "ODD")
    rows = database.get_effective_working_hours(date(2026, 9, 14))
    assert [(r["start_time"], r["end_time"]) for r in rows] == [("14:00", "18:00")]

    database.set_teacher_week_day_off("ODD", 0, True)
    assert database.get_effective_working_hours(date(2026, 9, 14)) == []
    database.set_teacher_week_day_off("ODD", 0, False)

    copied = database.replace_week_schedule("ODD", "EVEN")
    assert copied >= 1
    rows = database.get_working_hours(0, "EVEN")
    assert [(r["start_time"], r["end_time"]) for r in rows] == [("14:00", "18:00")]

    database.set_setting("teacher_even_week_enabled", "0")
    assert database.get_effective_working_hours(date(2026, 9, 7)) == []
    assert len(database.get_working_hours(0, "EVEN")) == 1

    print("SCHEDULE PARITY SELFTEST: OK")


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
