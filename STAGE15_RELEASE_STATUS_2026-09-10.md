# Stage 15 — Release status

Date: 2026-09-10
Branch: feat/adelia-web-portal
Decision: **NOT READY TO DEPLOY YET**

The feature branch is functionally close, but the release gate cannot be marked green from repository inspection alone. Production remains untouched.

## GREEN — implemented in source

- Student/web booking, paid booking and trial-status logic.
- Trial availability is removed after a non-trial booking starts.
- Temporary public-trial profiles with 7-day expiry/purge.
- One-time continuation code after a public trial and conversion into a canonical student.
- Student board persistence via `users.board_url` and teacher web management facade/UI.
- Short post-lesson student feedback flow.
- One-off reschedule, permanent regular-schedule change, exchanges and teacher-approved cascade foundations.
- Vacation/pause, sickness and cancellation facades using canonical DB functions.
- Student/parent/teacher scoped web authentication architecture.
- Private teacher receipt-file endpoint and bounded upload path.
- PWA/desktop shell architecture.
- Desktop auto-update prompts; no forced background downloads.
- Desktop main cabinet and board deny media permissions.
- Telemost window is allow-listed to `telemost.yandex.ru` and limited to camera/microphone/media permissions; screen-capture permission is not granted.
- Google Calendar integration persists refresh credentials, refreshes access tokens and keeps lesson event IDs.
- Yandex Telemost API module now exists and saves/reuses a lesson conference instead of creating duplicates on normal retries.
- Existing launch-readiness and security selftests are present.

## YELLOW — requires production-like runtime verification

These must be run on a copy of the real database / real service environment before deployment:

1. Python compile/import check for the entire branch, including `final_features`, `web_backend`, `integrations`, Telegram and VK adapters.
2. `launch_readiness_check.py` against a sandbox copy of the current production database.
3. `web_backend.stage12_security_selftest` with the real web-service environment.
4. Desktop `npm ci && npm run selftest` and packaged-app smoke test.
5. SQLite `PRAGMA integrity_check`, `foreign_key_check`, and EXPLAIN QUERY PLAN for high-frequency web routes.
6. API latency measurements for login, dashboard, schedule, booking, payments/receipts, parent dashboard and lesson workspace.
7. Concurrency smoke: simultaneous student logins/bookings/receipt uploads without `database is locked` failures.
8. End-to-end student/parent/teacher authorization / IDOR tests with at least two students and two unrelated parent links.
9. Browser/PWA install and offline/reconnect test on phone.
10. Windows desktop startup, autostart choice, Telemost+board tiling, microphone/camera persistence and update prompt test.
11. Real Telegram and VK callback regression for all legacy actions plus the new permanent-schedule handler.

## RED — release blockers that require real credentials/facts/artifacts

### 1. Yandex Telemost
Required before enabling `YANDEX_TELEMOST_ENABLED=1`:
- production OAuth token with the needed Telemost API permission;
- one real create/read conference test;
- confirmation of the desired waiting-room policy;
- restart test proving the token is supplied only from service environment and not committed to Git.

Expected environment:
- `YANDEX_TELEMOST_ENABLED=1`
- `YANDEX_TELEMOST_OAUTH_TOKEN=<secret>`
- optional `YANDEX_TELEMOST_WAITING_ROOM_LEVEL=PUBLIC|ORGANIZATION|ADMINS`

Never commit the token.

### 2. Google Calendar
Required:
- real `token.json` containing a refresh token;
- correct `GOOGLE_CALENDAR_ID`;
- create/update/delete event smoke test;
- service restart + token refresh test;
- ensure credential/token files are outside public web root and protected by filesystem permissions.

### 3. Privacy / Russian personal-data release facts
Before publishing the final Privacy Policy and consent UI, verify the facts listed in `STAGE15_PRIVACY_LEGAL_REVIEW_2026-09-10.md`, especially:
- operator identity/contact details;
- physical location of primary DB, backups, file storage and logs;
- Roskomnadzor notification status or confirmed exemption;
- actual processors/providers and cross-border data flows;
- separate consent evidence/versioning where consent is relied upon.

The current landing footer still must not ship with a dead `href="#"` Privacy link.

### 4. Separate consent on public trial form
The form currently explains temporary use/deletion but still needs the final versioned consent link/checkbox and server-side proof once the operator/legal facts are fixed. Do not pre-check it.

### 5. Desktop installers / update feed
The source is configured for Electron Builder and a generic update endpoint, but release requires actual artifacts:
- increment release version from development `0.1.0`;
- build Windows installer;
- sign Windows installer if a signing certificate is available;
- build/notarize macOS artifacts if macOS distribution is planned;
- generate/publish updater metadata and artifacts under the configured `desktop-updates` endpoint;
- verify update from version N to N+1 on a clean machine.

Do not expose a dead Windows/macOS download button before a corresponding artifact exists.

## Performance release budgets

Use these as practical TutorBot release targets on production-like data. They are budgets, not claims that current runtime has already achieved them.

- public static landing first response: <= 300 ms server time;
- authenticated lightweight API p95: <= 500 ms;
- schedule/dashboard p95: <= 800 ms;
- heavier teacher reports p95: <= 1500 ms;
- booking/reschedule write p95 excluding external APIs: <= 1000 ms;
- no web request should synchronously block on Telemost/Google for more than the external integration timeout/fallback path;
- idle desktop CPU should remain near background baseline with no rapid polling;
- desktop update checks no more frequently than the configured four-hour interval and skipped during lesson windows.

If a budget is missed, measure first, then add an index/cache only for a demonstrated bottleneck.

## Cross-client final smoke matrix

Run each applicable row in Telegram, VK, Web/PWA and Desktop shell:

- registration/login and continuation code;
- trial booking/public trial conversion;
- paid one-off booking;
- package/minute balance booking;
- receipt upload/teacher review;
- one-off reschedule;
- permanent regular-schedule change;
- occupied-slot exchange;
- cascade proposal and final teacher confirmation;
- vacation/pause and resume;
- sickness/cancel;
- homework/materials/formulas/messages;
- parent dashboard, payments and progress;
- lesson start, Telemost, board, lesson finish;
- short student post-lesson survey;
- notifications and Google Calendar after create/reschedule/cancel/cascade.

## Required deployment order once all RED/YELLOW gates pass

1. Make a verified production DB backup and rehearse restore.
2. Run schema migrations/index creation on a production-copy first.
3. Run all selftests and smoke matrix against the copy.
4. Configure service secrets/credentials in environment, not Git.
5. Tag a release commit.
6. Build/sign desktop artifacts and publish updater feed.
7. Deploy web/API/bot code.
8. Restart services one by one and verify health/logs.
9. Run post-deploy smoke using dedicated test student/parent accounts.
10. Only then enable public application-download actions and announce the release.

## Final Stage 15 verdict

**Code-preparation phase: substantially complete. Production release gate: still RED/YELLOW until the runtime tests, credentials, legal/operator facts and installer artifacts above are supplied and verified.**

This is intentional: repository inspection cannot truthfully certify real Telemost/Google credentials, server location, database performance, Windows signing or live-service behavior.
