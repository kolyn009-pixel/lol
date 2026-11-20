"""Selftest for GET /api/student/progress (temp DB, real HTTP handler)."""
import json, os, sys, tempfile, threading, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp()
os.environ['ADELIA_DB_PATH'] = os.path.join(tmp, 'main.db')
os.environ['TUTORBOT_TEST_DB'] = os.path.join(tmp, 'test.db')
os.environ['OWNER_ID'] = '777'
from http.server import ThreadingHTTPServer
import importlib.abc, importlib.machinery
from unittest import mock
class _Stub(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path, target=None):
        if name.split('.')[0] in ('telegram', 'apscheduler', 'dotenv', 'httpx'):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
    def create_module(self, spec):
        m = mock.MagicMock(); m.__path__ = []; m.__spec__ = spec; return m
    def exec_module(self, m): pass
sys.meta_path.append(_Stub())
import database
database.TEST_DB_NAME = os.environ['TUTORBOT_TEST_DB']; database.set_test_mode(True); database.create_tables()
from learning import schema as ls
ls.initialize(os.environ['TUTORBOT_TEST_DB'])
from web_backend import api_v2
from database import connect

class H(api_v2.Handler):
    def do_GET(self):
        database.set_test_mode(True)  # contextvar is per-thread
        return super().do_GET()
    def _auth(self):
        t = self.headers.get('X-Test')
        return {'role': 'student', 'id': int(t)} if t and t.isdigit() else None
srv = ThreadingHTTPServer(('127.0.0.1', 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

def call(path, who=None):
    h = {'X-Test': who} if who else {}
    r = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), headers=h)
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')

assert call('/api/student/progress')[0] == 401
st, d = call('/api/student/progress', '1')
assert st == 200 and d == {'summary': {'total': 0, 'started': 0, 'mastered': 0, 'avg_mastery': 0}, 'topics': []}, d
c = connect()
for i in range(1, 26):
    c.execute("INSERT INTO learning_topics(id,subject,study_goal,grade,section,topic) VALUES(?,?,?,?,?,?)", (i, 'MATH', 'SCHOOL', 9, 'Sec', 'T%d' % i))
rows = [(1, 1, 'MASTERED', 95, '2026-01-03'), (1, 2, 'LEARNING', 40, '2026-01-02'), (1, 3, 'NOT_STARTED', 0, '2026-01-01'), (2, 4, 'LEARNING', 70, '2026-01-09')]
rows += [(1, 5 + k, 'LEARNING', 10, '2026-02-%02d' % (k + 1)) for k in range(20)]
for u, t, s, m, up in rows:
    c.execute("INSERT INTO student_topic_progress(user_id,topic_id,status,mastery,updated_at) VALUES(?,?,?,?,?)", (u, t, s, m, up))
c.commit(); c.close()
st, d = call('/api/student/progress', '2')
assert st == 200 and d['summary'] == {'total': 1, 'started': 1, 'mastered': 0, 'avg_mastery': 70} and [t['topic_id'] for t in d['topics']] == [4], d
st, d = call('/api/student/progress', '1')
assert d['summary']['total'] == 23 and d['summary']['mastered'] == 1 and d['summary']['started'] == 22, d['summary']
assert len(d['topics']) == 20 and all(t['status'] == 'started' for t in d['topics']), d['topics'][:2]
c = connect(); c.execute("DELETE FROM student_topic_progress WHERE user_id=1 AND topic_id>=5"); c.commit(); c.close()
st, d = call('/api/student/progress', '1')
assert [(t['topic_id'], t['status']) for t in d['topics']] == [(2, 'started'), (1, 'mastered'), (3, 'new')], d['topics']
t = d['topics'][1]; assert t['title'] == 'T1' and t['section'] == 'Sec' and t['mastery'] == 95 and t['updated_at'] == '2026-01-03'
print('OK')
