# Olympiad calendar — 2026-10-29

Additive module for the teacher and student cabinets, including the same pages
loaded by the desktop app and PWA. It does not change native installers, lessons,
payments, existing homework or existing subject study-plan steps.

## Included

- 39 physics/chemistry profile records from the 2026/27 RSOSh list as a boot catalog;
  successful daily registry parsing refreshes titles, levels and current membership.
  This first version selects profiles explicitly named physics or chemistry,
  rather than assigning interdisciplinary engineering contests to a school subject.
- Responsive cards, subject/confirmed-grade/level/event-format filters, month view,
  subscriptions, source links and check timestamps, event history and ICS export.
- Teacher recommendations to an existing student and optional olympiad preparation
  goals shown alongside the existing learning plan. Recommending does not subscribe
  the student or register them with an organizer. Teachers can add/edit all five
  stage types: registration, qualifier, final, results and appeal.
- Ten initially verified schedule entries: Lomonosov physics and chemistry,
  SPbU Internet Physics Olympiad and Moscow Chemistry Olympiad. Moscow finals are
  explicitly tentative. Unknown eligibility and dates stay unknown.
- Daily structured date adapters for those three organizers. The two Lomonosov
  profile registration deadlines are fetched separately from the qualifier dates.
  Other organizer pages are monitored for content changes and flagged for teacher
  review; their dates are NOT automatically understood by a generic scraper.
- Hourly reminder worker: 7 days / 1 day before starts and deadlines. Date-only
  reminders run at 09:00 Moscow; the UI never invents an event start time.
- In-app notification feed and opt-in linked Telegram/VK / configured Web Push.
  Teacher Telegram and Web Push are supported; teacher VK is deliberately not
  broadcast via the project's all-admin VK helper. Student VK is supported.
- Per-channel outbox, retries, leases, opt-out checks, cancel/revision checks,
  history and delivery status. External delivery is at-least-once across a crash
  between remote acceptance and the local acknowledgement.

## Data rules

No past-season date extrapolation. Tentative/cancelled/unpublished events do not
produce deadline reminders. A failing or changed-unparsed source blocks reminders
for its events. Events older than three days without verification also do not
produce reminders. Stored dates remain visible with source warnings. Reviewed
manual corrections survive automatic parsing; future edits use a revision check.
ICS is a dated snapshot, not an automatically subscribed feed.

The registry/source parsers have fixture coverage. Real organizer HTML may change;
this must produce a visible error/review flag, never blank out existing dates.
This environment did not verify a native browser render or deliver live messages.

## Installation on the server

Use an isolated checkout of the exact reviewed commit. Do not reset the active
release, copy the database or reuse an app-build folder with generated changes.

```
python3 scripts/install_olympiads.py --root /opt/adelia-current
python3 scripts/install_olympiads.py --root /opt/adelia-current \
  --database /opt/tutorbot/tutor.db --apply --monitoring
```

The installer preserves production additions in learning_hub_api.py and both
HTML files. Unknown modifications to the new standalone modules stop preflight.
The web process's working directory/database and its actual Python executable are
checked. Web environment files are reused by the new worker without printing
secrets. All source changes get a backup under /opt/tutorbot/backups/olympiads-*.
Failed restart, health or auth-route checks restore the original source files.
New empty additive tables may remain after rollback; existing tables are untouched.

Success markers: OLYMPIADS_INSTALLED and OLYMPIAD_MONITORING_ENABLED.
The timer triggers after boot and hourly; it refreshes official pages at most
once per 24 hours. Running service/worker requires existing project dependencies.
It may take several minutes to check all organizers; individual requests time out.

```
systemctl list-timers adelia-olympiads.timer
systemctl start --no-block adelia-olympiads.service
journalctl -u adelia-olympiads.service -n 30 --no-pager
```

Stop this module's automated processing with:

```
systemctl disable --now adelia-olympiads.timer
systemctl stop adelia-olympiads.service
```

## Verification

```
python3 scripts/olympiads_selftest.py
node scripts/olympiads_ui_selftest.cjs
```

The UI selftest needs linkedom (development only). It can use an installed
linkedom package or the local qa-deps dependency directory. Backend tests use an
isolated SQLite database and mocked transports; no production recipients are used.

After deployment: open Olympics as teacher and student, select a grade, recommend
to a test student, opt into a connected channel and check the delivery feed. Run a
real source refresh and inspect review flags before relying on deadline reminders.

Sources used for the seed, checked 2026-10-29:
https://rsr-olymp.ru/
https://olymp.msu.ru/rus/page/main/29/page/grafik-provedeniya-otborochnogo-ehtapa
https://olymp.msu.ru/rus/event/11026/
https://olymp.msu.ru/rus/event/11029/
https://distolymp2.spbu.ru/olymp/
https://moschem.olimpiada.ru/news/492


## Verified dates expansion and annual rollover

The boot calendar now contains 48 stage/deadline/result entries for 15 subject
profiles. Added official schedules: MIPT chemistry, Rosatom physics, Belchonok,
SPbU, KFU, Izumrud, and explicitly tentative HSE / Energy Hope dates.
Date-only entries preserve the organizer's precision; no class-specific session
start time is applied to all pupils. Belchonok UTC+7 times are converted by the UI.

Current exact source facts are revalidated daily. If a reviewed date expression
no longer matches, the source becomes a review item; replacement dates are not
guessed. Fully structured next-season date extraction currently covers the
existing MSU/SPbU-Internet adapters, MIPT chemistry and Rosatom physics. The other
reviewed date adapters are season-specific and require a new reviewed schedule
when organizers publish the next year. Complete automatic extraction for every
organizer is not claimed.

The academic season switches on August 1 in Europe/Moscow. The daily registry
check requires the new season explicitly, imports its own levels/membership and
configures supported permanent source adapters. MSU profile links are discovered
from its current schedule. Until the registry or schedules are published, no
previous-season dates are substituted. Existing opted-in subscriptions carry to
the same registry number/subject once per season, only for active students or
teachers. An unsubscribe is never reversed by subsequent refreshes. Old learning
goals/recommendations remain season-specific. Retired contests are not carried.
