# Stage 14.5 — Student Web/App parity

Goal: the bot remains a fully supported interaction channel, while web/PWA/desktop become the clearest full-featured student cabinet. All channels must reuse the same database and canonical business rules.

## UX rule

Do not copy Telegram/VK multi-step dialogs literally. Web should expose the same actions as clear cards/forms, show current state, price and consequences before confirmation, and keep rare/destructive actions inside the relevant lesson/payment screen.

## Parity matrix

| Student capability | Canonical bot/database logic | Web/API | UX target | Status |
|---|---|---|---|---|
| Upcoming/past lessons | lessons DB | existing student API | schedule timeline | DONE |
| Join lesson | lesson join/Telemost | existing lesson API | one-tap lesson workspace | DONE |
| Board | lesson board URL | existing lesson API | desktop side-by-side / mobile link | DONE |
| Regular schedule pause / vacation | pause_regular_schedule | api_v3 self-service | vacation period, preferably all schedules at once | PARTIAL |
| Resume regular schedule | resume_regular_schedule | api_v3 self-service | one tap | DONE |
| Sick leave | request_sickness | api_v3 self-service | explain refund/decision state | PARTIAL |
| Cancel confirmed lesson | cancel_lesson_by_student | api_v3 self-service | show late-cancel consequence before confirm | DONE |
| Reschedule request | pending reschedule flow | api_v3 self-service | choose free slot or propose own time | PARTIAL |
| One-off booking | create_lesson_request + working hours/conflicts | api_v4 booking | program -> duration -> date -> time -> price | IMPLEMENTED, NEEDS RUNTIME TEST |
| Cancel pending booking | cancel_pending_request | api_v4 booking | action on pending lesson card | API DONE, UI TODO |
| Exchange occupied time | existing exchange/reschedule flow | TODO | occupied slot -> exchange proposal -> participant consent -> teacher approval | TODO |
| Homework | homework DB/API | existing web | tasks, attachments, submission | DONE/POLISH |
| Materials/files | existing attachments/materials | existing web pieces | grouped by lesson/topic | AUDIT |
| Student-teacher messages | unified messages | existing web | conversation UI | DONE/POLISH |
| Payments/history | payment DB/API | existing web | clear balance/history | DONE/POLISH |
| Receipt upload | canonical receipt/payment flow | existing backend pieces | camera/file upload directly in web/PWA/desktop | VERIFY + POLISH |
| Packages/subscriptions/discounts | package/payment logic | existing web pieces | price comparison + remaining lessons | AUDIT |
| Notifications | bot notifications | bot remains primary | web status/inbox, no forced browser notifications | AUDIT |
| Profile/timezone | user profile | existing web | simple settings | DONE/POLISH |
| Parent/linked visibility | existing parent logic if enabled | TODO audit | parent read-only progress/payment view | AUDIT |
| Progress/statistics | existing stats | existing/partial | understandable student progress cards | AUDIT |

## Cross-platform requirement

Every student web feature must work in:

- normal browser;
- installed mobile PWA where browser/OS capabilities allow it;
- Electron desktop shell.

Desktop/PWA must never require opening Telegram/VK just to upload a receipt, book/reschedule/cancel a lesson, manage absence, read homework/materials or use payments.

## Before Stage 15

1. Verify exact database signatures and business constraints used by the new self-service/booking facades against the feature branch bot implementation.
2. Finish concrete-slot reschedule and exchange using the existing canonical exchange state machine.
3. Finish vacation as a clear period-level action rather than per-schedule technical controls where canonical logic permits.
4. Verify receipt upload end-to-end in browser, PWA and desktop shell.
5. Audit packages, materials, parent view, notifications and progress against Telegram/VK capabilities.
6. Replace raw internal errors and browser alert/confirm with accessible in-app sheets/toasts.
7. Remove broad MutationObserver usage from Stage 14.5 UI after integrating hooks into the main renderer.
8. Run static/runtime tests on a non-production database before deployment.
