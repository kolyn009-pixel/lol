# Final TEST DB attachment compatibility fix

The Stage 3 test-DB upgrade self-test correctly exposed a schema mismatch: a newly created `homework_attachments` table did not contain the legacy nullable `telegram_file_id` column, while the compatibility contract and legacy production schema require it.

Fix:
- clean databases create both canonical `file_id` and legacy-compatible `telegram_file_id`;
- migrations add either column if absent;
- legacy `telegram_file_id` values backfill canonical `file_id`;
- new Telegram homework attachments write both values;
- the migration remains idempotent.
