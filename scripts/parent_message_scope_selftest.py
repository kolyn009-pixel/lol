import importlib.util
import io
import sqlite3
import sys
import types
from datetime import datetime

db = sqlite3.connect(':memory:')
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);
CREATE TABLE parent_accounts(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);
CREATE TABLE parent_student_links(parent_id INTEGER,student_id INTEGER);
INSERT INTO users VALUES(1,'Первый ученик',1),(2,'Второй ученик',1);
INSERT INTO parent_accounts VALUES(10,'Мама',1),(11,'Папа',1);
INSERT INTO parent_student_links VALUES(10,1),(11,1),(11,2);
""")
class Conn:
    def execute(self,*a): return db.execute(*a)
    def executescript(self,*a): return db.executescript(*a)
    def commit(self): return db.commit()
    def rollback(self): return db.rollback()
    def close(self): pass
database = types.ModuleType('database')
database.connect = Conn
database.now_iso = lambda: datetime.now().isoformat()
sys.modules['database'] = database
pkg = types.ModuleType('web_backend')
pkg.__path__ = []
sys.modules['web_backend'] = pkg
parent_portal = types.ModuleType('web_backend.parent_portal')
def assert_link(pid, uid):
    row=db.execute("SELECT 1 FROM parent_student_links l JOIN parent_accounts p ON p.id=l.parent_id AND p.active=1 JOIN users u ON u.id=l.student_id AND u.active=1 WHERE l.parent_id=? AND l.student_id=?",(int(pid),int(uid))).fetchone()
    if not row: raise PermissionError('student_not_linked')
    return int(uid)
parent_portal._assert_link = assert_link
parent_portal.linked_students = lambda pid: [dict(r) for r in db.execute("SELECT u.id,u.name FROM users u JOIN parent_student_links l ON l.student_id=u.id WHERE l.parent_id=?",(pid,))]
sys.modules['web_backend.parent_portal'] = parent_portal
media=types.ModuleType('web_backend.message_media')
media.read=lambda token: (media.metadata(token),b'data') if media.metadata(token) else (_ for _ in ()).throw(FileNotFoundError())
media.metadata=lambda token: {'token':token,'student_id':1,'participant_type':'PARENT','participant_id':10,'kind':'document','name':'file.pdf','mime':'application/pdf','size':4,'url':'/api/message-media/'+token} if token=='parent10' else None
sys.modules['web_backend.message_media']=media
pushes=[]
web_push=types.ModuleType('web_backend.web_push')
web_push.send=lambda role, entity_id, *args: pushes.append((role, entity_id)) or {'sent':1}
sys.modules['web_backend.web_push']=web_push
push_events=types.ModuleType('web_backend.push_events')
push_events.teachers=lambda *args: pushes.append(('teacher', None)) or {'sent':1}
sys.modules['web_backend.push_events']=push_events
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module
um=load('web_backend.unified_messaging','web_backend/unified_messaging.py')
pm=load('web_backend.parent_messages','web_backend/parent_messages.py')
assert pm.students(10)['items']==[{'id':1,'name':'Первый ученик'}]
inbound=pm.send(10,1,'Привет')
assert pm.thread(10,1)['items'][0]['body']=='Привет'
assert pm.thread(11,1)['items']==[]
attached=pm.send(10,1,'',{'token':'parent10'})
assert pm.thread(10,1)['items'][-1]['attachment']['token']=='parent10'
try: pm.send(11,1,'Чужой файл',{'token':'parent10'})
except ValueError: pass
else: raise AssertionError('cross-parent media accepted')
for action in (lambda:pm.thread(10,2),lambda:pm.send(10,2,'Запрет'),lambda:pm.mark_parent_read(10,2)):
    try: action()
    except PermissionError: pass
    else: raise AssertionError('unlinked parent accessed student')
reply=pm.send_teacher_to_parent(inbound['conversation_id'],'Здравствуйте',42)
assert [m['body'] for m in pm.thread(10,1)['items']]==['Привет','','Здравствуйте']
assert pm.thread(11,1)['items']==[]
assert pushes==[('teacher', None),('teacher', None),('parent', 10)]
assert pm.mark_parent_read(10,1)['status']=='ok'
assert um.conversations()[0]['name']=='Мама'
assert um.conversations()[0]['student_name']=='Первый ученик'
assert um.conversation(1,'STUDENT',None)['id'] != inbound['conversation_id']
delivery=types.ModuleType('web_backend.message_delivery')
delivery.send_teacher_reply=lambda *args: None
delivery.send_existing_message_channels=lambda *args: None
sys.modules['web_backend.message_delivery']=delivery
read_sync=types.ModuleType('web_backend.message_read_sync')
read_sync.mark_conversation_read=lambda *args: None
sys.modules['web_backend.message_read_sync']=read_sync
stage=load('web_backend.stage10_api','web_backend/stage10_api.py')
class Handler(stage.Stage10Mixin):
    def __init__(self,role,entity): self.auth={'role':role,'id':entity};self.wfile=io.BytesIO()
    def _auth(self): return self.auth
    def _json(self,status,data): return status,data
    def send_response(self,*args): pass
    def send_header(self,*args): pass
    def end_headers(self): pass
for role,entity,allowed in [('student',1,False),('parent',11,False),('parent',10,True),('teacher',42,True)]:
    h=Handler(role,entity)
    result=h.stage10_get('/api/message-media/parent10',{})
    assert (h.wfile.getvalue()==b'data')==allowed,(role,entity,result)
db.execute('DELETE FROM parent_student_links WHERE parent_id=10 AND student_id=1')
assert Handler('parent',10).stage10_get('/api/message-media/parent10',{})[0]==403
try: pm.send_teacher_to_parent(inbound['conversation_id'],'После отвязки',42)
except ValueError: pass
else: raise AssertionError('unlinked parent received teacher reply')
print('PARENT_MESSAGE_SCOPE=PASS')

