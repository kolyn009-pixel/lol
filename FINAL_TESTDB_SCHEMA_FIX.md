# FINAL TEST DB SCHEMA FIX — 2026-08-29

Fixes the persistent guide/test sandbox migration.

Root cause found on production:
- production `/opt/tutorbot/tutor.db` already had `user_timezones`;
- persistent test DB `/opt/tutorbot_data/tutor_test.db` existed from an older release;
- `core/test_lab.ensure_test_db()` returned immediately when that file existed, so it never received new timezone, formula, or Stage 2 homework tables;
- entering test/guide mode switched `database.connect()` to the stale test DB and raised `sqlite3.OperationalError: no such table: user_timezones`.

Changes:
- `ensure_test_db()` now always performs idempotent schema upgrade, while preserving sandbox data;
- full base schema + learning + formula + homework + automation + final + CRM + UX schemas are initialized against TEST_DB_NAME;
- defaults are only seeded when absent;
- `stage3_testdb_upgrade_selftest.py` reproduces an old persistent sandbox and verifies repeatable migration;
- `stage3_testdb_upgrade.py` upgrades/verifies the actual persistent test sandbox before service start;
- deploy runs both checks before restarting TutorBot.
