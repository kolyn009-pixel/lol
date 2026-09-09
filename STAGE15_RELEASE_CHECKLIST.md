# Stage 15 — Release Gate

Stage 15 starts only after Stage 14.5 feature parity is complete. Production must not be updated until the release gate passes.

## 1. Performance and speed
- Measure public landing page, student cabinet, teacher cabinet, PWA and desktop startup.
- Check first content render, navigation latency and API response times on realistic TutorBot data.
- Identify slow SQLite queries with EXPLAIN QUERY PLAN and add only justified indexes.
- Remove duplicate API requests, unnecessary polling, oversized payloads and blocking startup work.
- Verify static asset cache headers, compression and lazy loading where useful.
- Test slow/mobile connections and older/low-power computers.
- Confirm background/PWA/desktop logic stops unnecessary work while hidden or idle.
- Run load/concurrency smoke tests for login, schedule, booking, payments, receipt upload and lesson start/end.
- Establish release budgets and fail the release if critical screens regress beyond them.

## 2. Security and privacy final audit
- Re-run auth/session/CSRF/same-origin/IDOR checks for student, parent and teacher roles.
- Verify uploaded receipts/materials are private and cannot be enumerated by URL.
- Verify microphone/camera permissions are only needed by the lesson/Telemost surface and are not collected by Adelia itself.
- Verify no analytics/telemetry or hidden personal-data collection was introduced in web/PWA/desktop.
- Review logs, backups and error messages for accidental personal-data leakage.
- Verify deletion/retention behavior and least-privilege access.

## 3. Russian privacy/legal text
Before release, re-check the then-current Russian legislation and official regulator guidance. The final text must account for the service being used by minors and parent/guardian scenarios, including applicable requirements around personal data, consent, information for children, and online-service disclosures. Do not rely on an old template without re-verifying the law at Stage 15.

Deliverables:
- final Privacy Policy;
- personal-data processing consent text where required;
- parent/guardian wording for minor users where required;
- concise in-product privacy explanation in plain Russian;
- links from registration/login/footer/application surfaces;
- version/date of legal texts and change history.

## 4. Application download banner
Public site must have a clear non-intrusive application banner/card.
- Windows download when signed installer is available.
- macOS download when signed/notarized build is available.
- Mobile: install PWA instructions/action where supported.
- Do not show dead download buttons before an artifact exists.
- Detect platform only to improve the suggested primary action; always allow choosing another platform.
- Include version and release notes link.
- Existing users receive in-app auto-update prompts for desktop instead of repeatedly downloading installers.

## 5. Cross-client parity regression
Confirm these work from bot, web/PWA and desktop where applicable:
- booking and trial lesson;
- one-off reschedule;
- permanent regular-schedule change;
- swaps, overlaps and teacher-approved cascades;
- vacation/pause/sickness/cancel;
- payments, packages, promo codes and receipts;
- homework/materials/formulas/messages;
- parent access and progress;
- post-lesson student feedback;
- lesson start/end, Telemost and board;
- notifications and calendar sync.

## 6. Calendar and Telemost reliability
- Verify Google Calendar refresh credentials survive restarts and token refreshes.
- Verify event creation/update/delete after booking/reschedule/cascade/cancel.
- Verify Yandex Telemost creation flow and failure fallback once credentials/subscription are configured.
- Ensure no duplicate events/meeting links after retries.

## 7. Release smoke test
- Fresh student registration.
- Existing student login.
- Parent login/link.
- Teacher login.
- Trial booking.
- Paid booking and receipt review.
- Regular booking and regular schedule change.
- One-off reschedule and cascade proposal.
- Homework cycle.
- Start and finish lesson, post-lesson survey.
- Desktop update path and PWA install path.
- Backup/restore rehearsal before production migration.

Only after all critical checks pass: tag release, build signed installers, deploy web/API, run post-deploy smoke tests, then publish download actions on the public site.
