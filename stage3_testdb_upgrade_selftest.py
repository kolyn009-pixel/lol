from __future__ import annotations
import os, sqlite3, tempfile, shutil
import database
from core import test_lab

root = tempfile.mkdtemp(prefix='tutorbot_testdb_upgrade_')
path = os.path.join(root, 'tutor_test.db')
# Simulate a persistent sandbox created by an older release.
c = sqlite3.connect(path)
c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY, telegram_id INTEGER, name TEXT, grade INTEGER, study_goal TEXT, main_subject TEXT, created_at TEXT)')
c.commit(); c.close()

old_dir, old_db = database.TEST_DATA_DIR, database.TEST_DB_NAME
database.TEST_DATA_DIR, database.TEST_DB_NAME = root, path
try:
    test_lab.ensure_test_db()
    test_lab.ensure_test_db()  # idempotency
    c = sqlite3.connect(path)
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = {'user_timezones','homework_drafts','homework_attachments','formula_favorites','formula_recent','formula_quiz_stats'}
    missing = sorted(required - tables)
    if missing:
        raise RuntimeError(f'test DB missing after upgrade: {missing}')
    user_cols = {r[1] for r in c.execute('PRAGMA table_info(users)')}
    if 'telegram_username' not in user_cols:
        raise RuntimeError('users missing telegram_username after migration')
    indexes = {r[1] for r in c.execute("PRAGMA index_list('users')")}
    if 'idx_users_username' not in indexes:
        raise RuntimeError('users missing idx_users_username after migration')

    cols = {r[1] for r in c.execute('PRAGMA table_info(homework_attachments)')}
    for col in ('draft_id','homework_id','file_id','telegram_file_id'):
        if col not in cols:
            raise RuntimeError(f'homework_attachments missing {col}')
    c.close()
    print('STAGE3 TEST-DB UPGRADE SELFTEST: OK')
finally:
    database.TEST_DATA_DIR, database.TEST_DB_NAME = old_dir, old_db
    database.set_test_mode(False)
    shutil.rmtree(root, ignore_errors=True)
