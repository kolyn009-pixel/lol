# Teacher tasks startup fix

Fixed a startup crash in `core/teacher_tasks.initialize()` where stale-task cleanup referenced `live_keys` and `now` that only exist inside `sync_auto()`.

Changes:
- `initialize()` is schema-only and safe during bot startup.
- stale AUTO task reconciliation stays in `sync_auto()`.
- added `teacher_tasks_runtime_selftest.py` that executes the real startup path twice and then `sync_auto()` on an isolated database.
- deploy now requires that runtime selftest.
- deploy waits six seconds after the service first reports `active` and re-checks it, preventing a transient active state from being mistaken for a healthy release.
