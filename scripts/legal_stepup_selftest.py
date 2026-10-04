"""Real SQLite step-up tests; no production database or Telegram requests."""
import os
import pathlib
import sqlite3
import sys
import tempfile
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
tmp = tempfile.TemporaryDirectory()
def connect():
    conn = sqlite3.connect(str(pathlib.Path(tmp.name) / 'test.db'), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn
database = types.ModuleType('database')
database.connect = connect
sys.modules['database'] = database
legal = types.ModuleType('web_backend.legal_documents')
legal.editor = lambda: {'draft': {}}
legal.save = lambda *args: {'saved': True}
sys.modules['web_backend.legal_documents'] = legal
from web_backend import legal_stepup as step
from web_backend.legal_api import LegalMixin

class Handler(LegalMixin):
    def __init__(self, role='teacher', uid=42, token='browser-a', body=None, origin=True):
        self.auth = {'role': role, 'id': uid} if role else None
        self.token, self.body, self.origin = token, body or {}, origin
    def _auth(self): return self.auth
    def _token(self): return self.token
    def _owner(self): return bool(self.auth and self.auth['role']=='teacher' and self.auth['id']==42)
    def _same_origin_write(self): return self.origin
    def _legal_body(self): return self.body
    def _json(self, status, payload): self.response = status, payload

class Tests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'ADELIA_OTP_SECRET':'test-only-secret-' * 4})
        self.env.start()
        conn = step._db()
        conn.execute('DELETE FROM legal_stepup')
        conn.execute('DELETE FROM legal_stepup_requests')
        conn.commit(); conn.close()
        self.sent = []
    def tearDown(self): self.env.stop()
    def issue(self, token='browser-a'):
        step.issue(token, 42, sender=lambda owner, code:self.sent.append((owner,code)))
        return self.sent[-1][1]
    def test_code_is_session_bound_and_one_time(self):
        code = self.issue()
        self.assertFalse(step.allowed('browser-a',42))
        for token, uid in [('browser-b',42),('browser-a',43)]:
            with self.assertRaises(ValueError): step.verify(token,uid,code)
        step.verify('browser-a',42,code)
        self.assertTrue(step.allowed('browser-a',42))
        self.assertFalse(step.allowed('browser-b',42))
        with self.assertRaises(ValueError): step.verify('browser-a',42,code)
    def test_expired_code_and_access(self):
        with patch.object(step.time,'time',return_value=10000): code=self.issue()
        with patch.object(step.time,'time',return_value=10300):
            with self.assertRaises(ValueError): step.verify('browser-a',42,code)
        with patch.object(step.time,'time',return_value=10400):
            code=self.issue();step.verify('browser-a',42,code)
        with patch.object(step.time,'time',return_value=11000):
            self.assertFalse(step.allowed('browser-a',42))
    def test_five_wrong_attempts_lock_code(self):
        code=self.issue(); wrong='000000' if code!='000000' else '111111'
        for _ in range(5):
            with self.assertRaises(ValueError): step.verify('browser-a',42,wrong)
        with self.assertRaises(ValueError): step.verify('browser-a',42,code)
    def test_rate_limit_across_sessions(self):
        for i in range(5):
            with patch.object(step.time,'time',return_value=10000+i*61): self.issue(str(i))
        with patch.object(step.time,'time',return_value=10400):
            with self.assertRaisesRegex(ValueError,'rate_limited'): self.issue('another')
    def test_immediate_resend_limited(self):
        self.issue()
        with self.assertRaisesRegex(ValueError,'rate_limited'): self.issue('another')
    def test_delivery_failure_is_closed(self):
        with patch.object(step,'_send',side_effect=RuntimeError('stepup_delivery_failed')):
            with self.assertRaises(RuntimeError): step.issue('browser-a',42)
        self.assertFalse(step.allowed('browser-a',42))
    def test_no_plain_codes_or_tokens_stored(self):
        code=self.issue(); conn=connect()
        row=dict(conn.execute('SELECT * FROM legal_stepup').fetchone());conn.close()
        self.assertNotIn(code,row.values());self.assertNotIn('browser-a',row.values())
        self.assertTrue(row['code_hash'].startswith('h1$'))
    def test_concurrent_consume_once(self):
        code=self.issue()
        def consume(_):
            try: step.verify('browser-a',42,code);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(consume,range(2))),1)
    def test_server_routes_gate_read_and_writes(self):
        h=Handler();h.legal_get('/api/teacher/legal',{});self.assertEqual(h.response[0],403)
        for path in ['/draft','/publish']:
            h.legal_post('/api/teacher/legal'+path);self.assertEqual(h.response[0],403)
        code=self.issue();step.verify('browser-a',42,code)
        h.legal_get('/api/teacher/legal',{});self.assertEqual(h.response[0],200)
        h.legal_post('/api/teacher/legal/draft');self.assertEqual(h.response[0],200)
    def test_owner_and_origin_before_send(self):
        with patch.object(step,'issue') as send:
            for h in [Handler(role='parent'),Handler(role=None),Handler(uid=43),Handler(origin=False)]:
                h.legal_post('/api/teacher/legal/stepup/request')
                self.assertIn(h.response[0],[401,403])
            send.assert_not_called()
    def test_missing_secret_fails_closed(self):
        with patch.dict(os.environ,{'ADELIA_OTP_SECRET':''}):
            with self.assertRaises(RuntimeError): self.issue()
        self.assertEqual(self.sent,[])

if __name__=='__main__': unittest.main()
