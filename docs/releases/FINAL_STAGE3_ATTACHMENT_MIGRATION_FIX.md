# Stage 3 attachment migration compatibility fix

Production compatibility patch for the pre-Stage-2 `homework_attachments` schema.

- preserves legacy `telegram_file_id`
- additively creates Stage-2 `file_id`
- backfills `file_id` from `telegram_file_id` only when empty
- migration is idempotent
- legacy self-test now reproduces the observed production schema
- live DB copy probe remains mandatory before service restart
