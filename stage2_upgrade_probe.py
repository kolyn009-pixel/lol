"""Run Stage 2 additive migration against a COPY of the real DB before restart."""
import os
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: stage2_upgrade_probe.py /path/to/copied.db')
path = os.path.abspath(sys.argv[1])
if not os.path.isfile(path):
    raise SystemExit(f'probe DB not found: {path}')

os.environ['TUTORBOT_TEST_DB'] = path
import database
database.TEST_DB_NAME = path
database.set_test_mode(True)
from learning import homework_flow as h

h.initialize()
h.initialize()

c = database.connect()
try:
    cols = {r['name'] for r in c.execute('PRAGMA table_info(homework_attachments)').fetchall()}
    required = {'draft_id','homework_id','file_type','file_id'}
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError(f'homework_attachments missing after migration: {missing}')
    c.execute('SELECT draft_id,homework_id FROM homework_attachments LIMIT 1').fetchone()
finally:
    c.close()

print('STAGE2 LIVE-DB COPY MIGRATION PROBE: OK')
