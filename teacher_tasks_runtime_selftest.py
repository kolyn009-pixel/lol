from __future__ import annotations
import os
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix='tutorbot_teacher_tasks_') as td:
    db_path = str(Path(td) / 'teacher_tasks_test.db')
    os.environ['TUTORBOT_TEST_DB'] = db_path
    import database
    database.TEST_DB_NAME = db_path
    database.set_test_mode(True)
    database.create_tables()
    from core import teacher_tasks
    # Startup path: this previously crashed with NameError(live_keys).
    teacher_tasks.initialize()
    teacher_tasks.initialize()
    # Runtime sync path owns live_keys and must also remain safe.
    teacher_tasks.sync_auto()
    c = database.connect()
    try:
        row = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='teacher_tasks'").fetchone()
        assert row is not None
        cols = {r['name'] for r in c.execute('PRAGMA table_info(teacher_tasks)').fetchall()}
        assert {'id','title','status','source_type','source_key','created_at','updated_at'}.issubset(cols)
    finally:
        c.close()

print('TEACHER TASKS RUNTIME SELFTEST: OK')
