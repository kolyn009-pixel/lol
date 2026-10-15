# Mobile and payment reliability — 2026-10-15

The parent home offers a two-lesson payment calculated through the existing individual tariff rules. The payment screen shows upcoming dates in the schedule timezone, balance, one receipt upload and the review stage. Dates describe the current timetable; this is a minute-balance purchase, not a new promise to reserve those dates. Existing review notifications to the student and linked parents remain in the canonical finance review flow.

Checkout runs an optional self-service guard under SQLite BEGIN IMMEDIATE. Identical pending invoices are reused; a receipt under review blocks creation even when newer unpaid invoices exist. Existing admin checkout behavior remains available. A parent can read one payment's current state only after checking the parent/student link and payment ownership. The browser polls this endpoint while a receipt is under review.

The parent chat button remains visible on mobile. Chat drafts survive navigation and reload in the same tab, scoped by parent and student, with a 24-hour expiry. Manual homework comments survive navigation and failed sends. Student chat input is disabled while sending to avoid erasing new text. Existing homework answer drafts and group chat recovery remain in place.

The shared request wrapper applies deadlines and preserves caller cancellation. It does not retry writes. The optional support report contains technical error categories, endpoint paths without query values, status codes, timings, viewport and UI version. It excludes response/request bodies, error messages and form contents. The user chooses whether to copy or download it; it is not automatically transmitted.

Validation:
- Real Chromium with production HTML/JS/CSS and isolated fixture APIs: parent code login failure/retry; two-lesson quote/dates; one receipt; automatic status refresh after approval; balance; chat failure, reopen and reload recovery; student homework comment failure/navigation recovery; lesson waiting room and join; teacher payment queue and refresh; support dialogs at 320px and 390px; no uncaught page errors.
- Production checkout function against isolated SQLite: individual price, invoice reuse, simultaneous requests, review precedence, separation by user/amount/duration/lesson, paid invoice separation. Production link/ownership checks reject another parent or another student's payment.
- Support/runtime checks: deadlines, caller abort, preserved POST body/headers, no automatic retry, no private body/query/error-message values in the report.
- Existing weekly payment, onboarding, student draft and group chat tests pass.

The browser tests use fixtures rather than live accounts. Native Safari, live bank transfers, live push delivery and newly packaged desktop binaries were not verified here. Desktop source assets are synchronized for the next build; the currently downloaded installers are unchanged. Server installation and nginx upload size still require the guarded deployment preflight.
