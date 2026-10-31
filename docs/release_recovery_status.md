# Release preparation checkpoint

Base: 1cb0dd20d171b493b3cde6078f52e952e16da2dd. Production was not changed.

Workspace maintenance removed uncommitted work from the interrupted session. Earlier commentary described local implementations and local test runs, not deployed or committed features. This checkpoint distinguishes recovered work from pending reconstruction.

Recovered and tested:
- Manual payment reads and validates the lesson inside BEGIN IMMEDIATE. Concurrent confirmations return the same payment/package.
- Existing invoices require explicit review instead of automatic whole-invoice approval from a lesson payment action.
- Manual payments link to their lesson and record actor/source in the same transaction.
- Disposable SQLite regression verifies concurrent calls, exact total, actor, rejection of nonpositive amount and linked-invoice guard.

Preserved in base:
- Formula subject/section/topic catalogue; payment status explanations and correction journal; group finance panels; mobile student layout changes.
- Previously prepared Telegram None user_data guards, job grace periods, exchange inbox and reschedule calendar changes remain in the repository, with separate installers. Their production installation is unconfirmed.
- Desktop 0.3.1 source includes board account and Telemost compatibility work. Native calls still require real-device validation.

Pending reconstruction before a final release:
- Durable per-channel message and homework delivery with success deduplication, ambiguous-send handling and worker heartbeat.
- Factual lesson timeline, balance explanation, accidental-start reversal, local scoped drafts and existing-account recovery UI.
- Verified backup/archive/isolated restore, external destination configuration and operational readiness UI.
- Unified installer planning all surgical patches before mutation, code rollback, SQLite online backup, service/asset checks and worker units.
- Release source gate and Mac/Windows build handoff; cached Docker builder fallback for registry timeouts.

Do not publish the incomplete release or describe installers as built. No macOS/Windows binaries were created in this environment. No off-server backup destination is configured. The unexplained historical production PAID entries still need the read-only production diagnostic; reproducing a race does not prove their cause.
