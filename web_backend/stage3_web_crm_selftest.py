"""One-shot Stage 3 web CRM smoke test.

Run against a COPY of tutor.db by setting TUTORBOT_TEST_DB and enabling
`database.set_test_mode(True)` before importing this module, or invoke through
the same isolated runtime used by the web preview. No production mutations are
performed by this script.
"""
from __future__ import annotations

from web_backend import api_v2
from web_backend.teacher_crm import schedule, students, student
from web_backend.teacher_portal import dashboard


def run():
    print("=== ADELIA STAGE 3 WEB CRM SELFTEST ===")
    assert issubclass(api_v2.Handler, api_v2.v1.Handler)
    dash = dashboard()
    assert isinstance(dash, dict) and "stats" in dash and "next_lessons" in dash
    week = schedule()
    assert isinstance(week, dict) and isinstance(week.get("items"), list)
    roster = students(limit=500)
    assert isinstance(roster, dict) and isinstance(roster.get("items"), list)
    if roster["items"]:
        uid = int(roster["items"][0]["id"])
        card = student(uid)
        assert card and int(card["student"]["id"]) == uid
        assert "stats" in card and "recent_lessons" in card
    print("dashboard: OK")
    print("schedule: OK", len(week["items"]))
    print("students: OK", roster.get("total", 0))
    print("student card: OK" if roster["items"] else "student card: SKIP (no active students)")
    print("API v2 inheritance: OK")
    print("STAGE 3 CRM: OK")
    return True


if __name__ == "__main__":
    run()
