import sqlite3, os, tempfile, shutil
import database
from crm_plus import schema,service

schema.initialize()
conn=database.connect()
required={'crm_student_messages','student_pinned_notes','student_agreements','crm_settings','billing_offers','crm_undo_log'}
existing={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
missing=required-existing
assert not missing,missing
assert service.get_setting('quiet_start')
print('CRM PLUS SELFTEST: OK')
conn.close()
