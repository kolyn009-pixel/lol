from __future__ import annotations
import sqlite3
import database
from core import test_lab

test_lab.ensure_test_db()
c = sqlite3.connect(database.TEST_DB_NAME)
tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
required = {'user_timezones','homework_drafts','homework_attachments','formula_favorites','formula_recent','formula_quiz_stats'}
missing = sorted(required - tables)
if missing:
    raise RuntimeError(f'test DB missing after migration: {missing}')
c.close()
print('STAGE3 TEST-DB LIVE UPGRADE: OK')
