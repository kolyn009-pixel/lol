# FINAL Stage 3 migration hotfix — 2026-08-29

This build fixes the production startup failure `sqlite3.OperationalError: no such column: draft_id` seen after the first Stage 3 deployment attempt.

Changes:
- Stage 2 homework schema migration is now additive and ordered: missing columns are added before indexes are created.
- Existing homework attachment rows are preserved.
- Migration is idempotent and safe to run more than once.
- Added `stage2_upgrade_selftest.py`, which reproduces the legacy table shape that failed in production.
- Added `stage2_upgrade_probe.py`; deploy now copies the live `tutor.db` and tests the new migration on that copy before starting the new service.
- Service startup waits up to 15 seconds instead of treating a short `activating` state as failure.
- If the new service still fails to start, deploy automatically restores the project backup and restarts the previous version.

No secrets or production database are included in the release archive.
