import os
import sqlite3
import tempfile

fd, path = tempfile.mkstemp(suffix='.db')
os.close(fd)
os.unlink(path)
c = sqlite3.connect(path)
c.executescript('''
CREATE TABLE homework_drafts(id INTEGER PRIMARY KEY AUTOINCREMENT, admin_telegram_id INTEGER NOT NULL, user_id INTEGER NOT NULL);
CREATE TABLE homework_attachments (
 id INTEGER PRIMARY KEY AUTOINCREMENT, homework_id INTEGER NOT NULL,
 telegram_file_id TEXT, max_file_id TEXT, source_platform TEXT,
 file_type TEXT NOT NULL, file_name TEXT, created_at TEXT NOT NULL
);
INSERT INTO homework_drafts(admin_telegram_id,user_id) VALUES(90001,10001);
INSERT INTO homework_attachments(homework_id,telegram_file_id,max_file_id,source_platform,file_type,file_name,created_at)
VALUES(77,'legacy-telegram-file-id','legacy-max-id','telegram','document','old.pdf',CURRENT_TIMESTAMP);
''')
c.commit(); c.close()
os.environ['TUTORBOT_TEST_DB'] = path
import database
database.TEST_DB_NAME = path
database.set_test_mode(True)
from learning import homework_flow as h
h.initialize(); h.initialize()
c = database.connect()
try:
    attach_cols = {r['name'] for r in c.execute('PRAGMA table_info(homework_attachments)').fetchall()}
    indexes = {r['name'] for r in c.execute("PRAGMA index_list('homework_attachments')").fetchall()}
    assert {'draft_id','homework_id','file_id','file_unique_id','file_name','caption','created_at','telegram_file_id'}.issubset(attach_cols), attach_cols
    assert {'idx_hw_attach_draft','idx_hw_attach_hw'}.issubset(indexes), indexes
    legacy = c.execute("SELECT file_id,telegram_file_id FROM homework_attachments WHERE homework_id=77").fetchone()
    assert legacy['telegram_file_id'] == 'legacy-telegram-file-id'
    assert legacy['file_id'] == 'legacy-telegram-file-id'
finally:
    c.close(); os.unlink(path)
print('STAGE2 LEGACY TELEGRAM_FILE_ID MIGRATION SELFTEST: OK')
