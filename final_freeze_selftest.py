import os,tempfile,sys,types
work=tempfile.mkdtemp(prefix='tutorbot_freeze_')
os.environ['TUTORBOT_TEST_DATA_DIR']=os.path.join(work,'testdata')
# PTB is present on the server venv. Local build verification uses import-only stubs.
tg=types.ModuleType('telegram')
class Dummy:
    def __init__(self,*a,**k): pass
for n in ('InlineKeyboardButton','InlineKeyboardMarkup','Update'): setattr(tg,n,Dummy)
sys.modules.setdefault('telegram',tg)
ext=types.ModuleType('telegram.ext')
for n in (
    'CallbackQueryHandler',
    'CommandHandler',
    'ContextTypes',
    'ConversationHandler',
    'MessageHandler',
):
    setattr(ext,n,Dummy)

class DummyFilters:
    def __getattr__(self, name):
        return self
    def __and__(self, other):
        return self
    def __or__(self, other):
        return self
    def __invert__(self):
        return self

ext.filters = DummyFilters()
sys.modules.setdefault('telegram.ext',ext)
import database
database.DB_NAME=os.path.join(work,'prod.db')
database.TEST_DATA_DIR=os.path.join(work,'testdata')
database.TEST_DB_NAME=os.path.join(database.TEST_DATA_DIR,'tutor_test.db')
from core import test_lab

database.create_tables(); test_lab.ensure_schema(); test_lab.ensure_test_db()
assert os.path.exists(database.TEST_DB_NAME)
assert database.DB_NAME != database.TEST_DB_NAME
database.set_test_mode(True)
c=database.connect();c.execute("INSERT INTO bot_settings(key,value,updated_at) VALUES('freeze_test','1','now') ON CONFLICT(key) DO UPDATE SET value='1'");c.commit();c.close()
database.set_test_mode(False)
c=database.connect();r=c.execute("SELECT value FROM bot_settings WHERE key='freeze_test'").fetchone();c.close()
assert r is None, 'sandbox write leaked into production'
print('FINAL FREEZE SELFTEST: OK')
