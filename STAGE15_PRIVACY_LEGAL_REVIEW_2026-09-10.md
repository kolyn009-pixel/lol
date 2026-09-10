# Stage 15 — Privacy / legal release review

Review date: 2026-09-10
Status: PRE-RELEASE GATE — do not label the public policy final until the operator facts below are verified.

This checklist is an engineering/compliance aid, not individual legal advice.

## Current rules accounted for

1. Federal Law No. 152-FZ applies to automated personal-data processing by individuals and organizations.
2. Processing must be limited to specific, pre-defined and lawful purposes; excessive data collection must be avoided.
3. A consent, when used as the legal basis, must be specific, informed, conscious and unambiguous. Since the 2025 amendments, consent to personal-data processing must be оформлено отдельно from other information/documents the subject confirms.
4. The operator bears the burden of proving that consent or another lawful basis exists.
5. For collection of Russian citizens' personal data via the Internet, the July 1, 2025 localization rule requires recording/systematization/accumulation/storage/update/extraction using databases located in the Russian Federation, except statutory exceptions. Subsequent cross-border transfers have a separate Article 12 regime.
6. The operator must implement sufficient organizational/technical measures, publish an applicable processing policy, respond to subject/representative requests, and support correction/blocking/deletion where legally required.
7. Minors require special care. A legal representative may act for the child; the service must verify representative authority where consent is obtained from a representative. Do not collect special-category or biometric data from a minor merely because a parent clicked a generic website checkbox.

## TutorBot / Adelia data-minimization decisions

- Public trial requests are temporary and kept outside canonical users until conversion.
- Public trial PII expires after 7 days if onboarding is not completed; the existing cleanup routine purges name/contact/class/subject/goal/note/meeting/board/code data.
- Trial form should collect only a contact channel needed to organize the lesson; Telegram OR phone is sufficient.
- Do not collect passport data, exact home address, health details, biometrics, microphone/camera recordings, or screen captures for normal tutoring workflows.
- Desktop main cabinet and board receive no media permissions. Telemost gets only media/microphone/camera permissions and only for the allow-listed Telemost origin.
- Receipts and educational materials must remain authenticated/private and must not be exposed by guessable public URLs.
- Application analytics/telemetry must remain opt-out-by-default/no hidden tracking unless a separate future privacy review approves it.

## Mandatory facts to verify before publishing FINAL policy

These cannot be safely invented in source code:

- [ ] Operator full legal identity exactly as used for contracts/tax/self-employed activity.
- [ ] Operator contact email or other durable address for personal-data requests.
- [ ] Operator postal/contact address where legally required in the chosen policy/consent form.
- [ ] Exact physical country/location of the production database, backups, object/file storage and logs. The primary collection/storage path for Russian citizens must satisfy Article 18(5).
- [ ] Whether any provider receives personal data cross-border (including backup, analytics, error tracking, AI APIs, email, CDN, or storage); if yes, complete the Article 12 analysis/notification before enabling that transfer.
- [ ] Roskomnadzor operator-notification status and the categories/purposes/systems actually declared, unless a statutory exemption clearly applies.
- [ ] Actual processors/third parties used in production: hosting, Telegram, VK, Yandex Telemost, Google Calendar, board provider, payment/receipt storage, email/SMS if enabled.
- [ ] Retention periods for canonical student/parent/payment/accounting records based on the real contractual/tax purpose; do not reuse the 7-day trial TTL for accounting records.

## Required public documents / UI

Before production launch publish versioned documents with an effective date:

### Privacy policy
Must describe at minimum:
- operator and contact channel;
- categories of subjects (student, parent/legal representative, trial applicant, teacher/admin);
- concrete data categories actually collected;
- purposes and legal bases;
- processing operations/methods;
- recipients/processors and cross-border transfer position;
- localization/storage description without exposing infrastructure secrets;
- retention/deletion rules by purpose;
- subject and representative rights/request procedure;
- security approach at a high level;
- document version/effective date/change history.

### Separate consent text where consent is the basis
The checkbox/action must not be bundled into acceptance of unrelated terms. Store evidence sufficient to show:
- policy/consent version;
- timestamp;
- subject/account/request identifier;
- exact consent purpose;
- actor type (subject or representative);
- withdrawal method.

Do not store a raw IP address solely for proving consent unless it is actually necessary and documented; prefer account/request id + timestamp + immutable consent version.

### Minor / representative wording
Use neutral age-aware wording instead of claiming that every action by every 14–17-year-old always requires parental consent. Suggested product rule:

> If you submit data or manage an account on behalf of a minor, you confirm that you are the child's parent or other lawful representative and have authority to act for the child. Where the law or the selected legal basis requires representative consent, Adelia may request confirmation of that authority. Do not send special-category or biometric information through ordinary forms.

For young children, route contractual/consent actions through the parent/legal representative. For older minors, the exact contract/consent model should be checked against the relevant civil-law capacity rules and the concrete service/payment flow.

## Public trial form gate

Current form already states the 7-day-style temporary-data principle and the backend has a 7-day retention/purge mechanism. Before final release:

- [ ] add an explicit, separate privacy-consent checkbox/link before submission where consent is the chosen basis;
- [ ] server must reject a trial submission if required consent evidence is absent;
- [ ] persist consent version + timestamp tied to the temporary request;
- [ ] keep trial data purpose-limited to contacting the applicant and organizing/converting the trial;
- [ ] do not pre-check the consent checkbox.

## Security release gates already present in code

- same-origin protection on public write route;
- bounded JSON body and auth rate-limit checks in Stage 12 selftest;
- hashed/keyed OTP architecture and bounded sessions;
- authenticated teacher-only receipt file route with private/no-store cache headers;
- role-scoped student/parent/teacher APIs;
- additive indexes for high-frequency ownership/privacy queries.

These are architecture checks only. They still require runtime regression tests against a production-like database before launch.

## Release decision

Legal/privacy status is YELLOW, not GREEN, until the mandatory operator/infrastructure facts are supplied and the separate consent UI + server-side evidence are implemented and tested.

Do not publish dead Privacy links, placeholder operator details, or a document claiming full legal compliance before those gates pass.
