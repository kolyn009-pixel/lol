TutorBot FINAL MEGA — final feature pack

This release is built on bottutor_MINUTES_FINAL_COMPLETE_FIXED and preserves all Stage 1/2/3 and live hotfixes.

NEW FINAL FEATURES
1. Smart student card / next actions.
2. Smart minute renewal recommendations.
3. Monthly progress report drafts for student/parent.
4. Reschedule/exchange request matching foundation.
5. Post-lesson assistant with quick topic/level/comment survey.
6. Business control center and anomaly view.
7. Exam preparation plan to a target date/score.
8. Existing full homework workflow retained and connected to business attention.
9. Exam-result trend + conservative short-horizon projection.
10. Financial forecast for current calendar month.
11. Unified student timeline.
12. Dedicated mock-test assignment/result/history section.
13. Central tariff/discount rules; minute-package purchase uses them.
14. Immutable minute ledger for purchase/reserve/refund/bonus/admin movements.
15. Automated reconciliation: money/minutes/lessons/Calendar checks.
16. Teacher week view: booked minutes, free capacity from working hours, planned revenue.
17. Recovery health screen using existing backups/safe_update/rollback.
18. Quick post-lesson curriculum survey by class/exam track.

EXISTING FEATURES PRESERVED
- Minute-based subscriptions and individual base lesson duration.
- Student may choose a longer lesson but never shorter than their base duration.
- Overtime by tutor is not charged; underworked tutor time credits bonus minutes.
- Finance: received / earned / prepaid.
- 24h / 2h / 30m / 10m reminder chain.
- Tutor delay flow including "I don't know, tell later".
- Parents (up to two), booking/reschedule/cancel, finances and notification preferences.
- Google Calendar create/update/delete with 404/410 delete treated as already deleted.
- Formula libraries for Physics 7–11, Chemistry 8–11, EGE physics and reference tables.
- Unified admin inbox and separate student messages.
- Multi-admin roles, audit, backups, diagnostics, maintenance mode, exports.

ADMIN ENTRY POINTS
- /final — final control center
- /student360 USER_ID — smart student card
- /mockassign USER_ID PROGRAM_ID YYYY-MM-DD TITLE
- /mockresult MOCK_ID TEST_SCORE [PRIMARY_SCORE] [MINUTES]
- /mocks USER_ID — mock tests
- /examplan USER_ID PROGRAM_ID YYYY-MM-DD TARGET_SCORE MINUTES_PER_WEEK
- /lessonreview LESSON_ID — quick post-lesson survey
- /swaprequest USER_ID LESSON_ID YYYY-MM-DD HH:MM HH:MM MINUTES
- /discount GOAL BASE_MINUTES EQUIVALENT_LESSONS PERCENT
- /week — teacher week summary

SAFE SERVER UPDATE
Use the SERVER archive. It intentionally excludes tutor.db, token.json, credentials.json and venv.
Make a backup before updating. Run final_features_selftest.py on a copy/local package, and on the server run compileall + existing post_update/calendar checks before restart.
