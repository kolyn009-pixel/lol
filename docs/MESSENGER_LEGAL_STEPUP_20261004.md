# Messenger and legal editor follow-up

Base deployed release: 5f603c64756558f87b049c62086ac5ffec4b3417.

- Messenger fits remaining viewport height; history and conversation list scroll independently. Mobile shows a list or an active thread with a back button.
- Unread headline and filter badge refresh together. Draft text and selected attachments survive conversation/filter changes in page memory (not persistent browser storage). Stale history responses cannot replace another conversation.
- Homework details include a Files tab with photo thumbnails, PDF/file links, size and a server-copy indicator. Existing homework persistence stores attachment bytes and checksum in SQLite before confirming save; this change does not migrate archives or turn ordinary chat attachments into homework assignments.
- Legal editor GET, draft save and publication require owner authentication plus a Telegram step-up bound to the current web session. Code expires in 5 minutes, grants 10 minutes, has 5 attempts; requests limited to one/minute and five/hour across sessions. Telegram recipient comes from authenticated owner identity, never request input. HMAC digest uses ADELIA_OTP_SECRET; no plain OTP/session tokens stored in the step-up table. Failures never expose Telegram URLs/tokens. Public legal pages and parent acceptance are unchanged.

## Deployment prerequisites

The web process must have BOT_TOKEN and an ADELIA_OTP_SECRET of at least 32 UTF-8 bytes in its environment. Never paste secret values into chat or commit them. Missing configuration fails closed: the private legal editor remains locked. Verify real Telegram delivery and owner reauthentication after deployment.

Keep both production databases and persistent attachments. The current release tutor.db symlink points to the learning database under the older 5ce93fd release; retain that target until a separately verified data relocation. Do not replace it with the main /opt/tutorbot/tutor.db.

## Validation

- 11 isolated real-SQLite step-up tests (session binding, expiry, one-time use, concurrent consumption, rate limits, brute-force lockout, delivery failure, missing secret, API role/origin/read/write gates).
- 8 existing legal-document tests.
- Homework PDF/photo persistence and authorization tests; VK source can be unavailable after save.
- Messenger draft/count/viewport calculation/stale-history tests and JS/Python syntax checks.
- Added checks to desktop CI preflight; asset URL versions and teacher service-worker cache revision updated.

Browser visual verification is still required: local Playwright has no Chromium binary. Test desktop and narrow mobile viewport, keyboard/composer visibility, file selection, PDF opening, and actual OTP delivery on the deployed app. Native installer build success does not replace this check.
