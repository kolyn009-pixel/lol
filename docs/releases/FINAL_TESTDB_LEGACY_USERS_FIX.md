# FINAL TEST DB LEGACY USERS FIX

Исправлена миграция старой тестовой БД, в которой таблица `users` могла существовать без `telegram_username` и других более новых необязательных полей.

- недостающие поля `users` добавляются идемпотентно до создания UX-индексов;
- `idx_users_username` создаётся только после миграции колонок;
- Stage 3 test-DB selftest воспроизводит старую минимальную таблицу `users` и проверяет колонку + индекс;
- production БД и сохранённые тестовые профили не пересоздаются и не удаляются.


## v4 attachment compatibility
Clean Stage-2/Stage-3 databases now also create the nullable legacy `telegram_file_id` column in `homework_attachments`. New Telegram attachments populate both `file_id` and `telegram_file_id`, while legacy production rows are still backfilled into `file_id`. This keeps clean, legacy, and persistent test sandboxes on one compatible schema.
