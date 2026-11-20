"""Selftest for the public teacher profile (temp DB, real HTTP handler)."""
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
    # Third-party bot libs may be absent where the selftest runs; stub them lazily.
    def find_spec(self, name, path, target=None):
        if name.split('.')[0] in ('telegram', 'apscheduler', 'dotenv', 'httpx'):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
    def create_module(self, spec):
        m = mock.MagicMock(); m.__path__ = []; m.__spec__ = spec; return m
    def exec_module(self, m): pass
sys.meta_path.append(_Stub())
from web_backend import api
from web_backend.teacher_profile import ensure_teacher_profile_table
from database import connect

class H(api.Handler):
    def _auth(self):
        t = self.headers.get('X-Test')
        return {'role': 'teacher', 'id': 777} if t == 'teacher' else ({'role': 'student', 'id': 5} if t == 'student' else None)
srv = ThreadingHTTPServer(('127.0.0.1', 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

def call(method, path, body=None, who=None):
    h = {'Content-Type': 'application/json'}
    if who: h['X-Test'] = who
    r = urllib.request.Request('http://127.0.0.1:%d%s' % (port, path), method=method, headers=h,
                               data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(r) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

ensure_teacher_profile_table(); ensure_teacher_profile_table()
c = connect(); assert c.execute('SELECT COUNT(*) FROM teacher_public_profile').fetchone()[0] == 1; c.close()
st, d = call('GET', '/api/public/teacher-profile'); assert st == 200 and d['slug'] == 'solovyev'
assert d['links']['profi'].startswith('https://') and d['subjects'][0]['subject'] == 'PHYSICS' and 'Более 50 учеников' in d['facts']
assert 'teacher_id' not in d and 'active' not in d and d['education'] is None
assert call('GET', '/api/public/teacher-profile?slug=solovyev')[0] == 200
assert call('GET', '/api/public/teacher-profile?slug=nope')[0] == 404
assert call('PUT', '/api/teacher/public-profile', {'headline': 'x'})[0] == 401
assert call('PUT', '/api/teacher/public-profile', {'headline': 'x'}, 'student')[0] == 401
st, d = call('PUT', '/api/teacher/public-profile', {'headline': 'Физика и химия', 'links': {'vk': 'https://vk.ru/x'}}, 'teacher')
assert st == 200 and d['profile']['headline'] == 'Физика и химия' and d['profile']['links'] == {'vk': 'https://vk.ru/x'}
for bad in ({'links': {'vk': 'http://vk.ru/x'}}, {'links': {'vk': 'javascript:alert(1)'}}, {'links': {'evil': 'https://a.b'}},
            {'facts': 'str'}, {'subjects': [{'subject': 'X', 'label': 'a', 'goals': []}]}, {'bio': 'a' * 3001}, {'slug': 'Bad Slug'}):
    assert call('PUT', '/api/teacher/public-profile', bad, 'teacher')[0] == 400, bad
assert call('GET', '/api/public/teacher-profile')[1]['links'] == {'vk': 'https://vk.ru/x'}
print('OK teacher_profile selftest')
