"""Exercise recruitment against an isolated SQLite database and a real HTTP server."""
import concurrent.futures
import http.client
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class RecruitmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        db_path = str(Path(cls.tmp.name) / 'recruitment.sqlite')
        db = types.ModuleType('database')
        def connect():
            c = sqlite3.connect(db_path, timeout=15)
            c.row_factory = sqlite3.Row
            return c
        db.connect = connect
        db.now_iso = lambda: datetime.now().isoformat(timespec='seconds')
        db.get_setting = lambda name, default=None: 'Europe/Moscow' if name == 'schedule_timezone' else default
        sys.modules['database'] = db
        cls.domain = importlib.import_module('web_backend.public_group_registration')
        cls.domain.ensure_schema()
        c = connect()
        c.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,active INTEGER DEFAULT 1)')
        for gid, state, active in [(1, 'OPEN', 1), (2, 'WAITLIST', 1), (3, 'CLOSED', 1), (4, 'OPEN', 0)]:
            c.execute('''INSERT INTO study_groups(id,name,subject,study_goal,description,price_per_lesson,max_members,recruitment_status,active,created_at,updated_at,board_url)
                VALUES(?,?,'PHYSICS','EGE','Подготовка',900,2,?,?,?,?,'PRIVATE-BOARD')''', (gid, 'Группа ' + str(gid), state, active, db.now_iso(), db.now_iso()))
        c.execute("INSERT INTO group_schedule_slots(group_id,weekday,start_time,duration_minutes,created_at,updated_at) VALUES(1,1,'18:00',90,?,?)", (db.now_iso(), db.now_iso()))
        c.commit(); c.close()
        # Only the unrelated application bootstrap is replaced; routes/domain are real.
        api = types.ModuleType('web_backend.api')
        api._allowed = lambda ip: True
        sys.modules['web_backend.api'] = api
        mixin = importlib.import_module('web_backend.public_group_registration_api').PublicGroupRegistrationMixin
        class Base(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def _same_origin_write(self): return self.headers.get('Origin') == 'https://adeliatutor.ru'
            def _teacher(self): return {'admin_telegram_id': 7} if self.headers.get('X-Test-Teacher') == 'yes' else None
            def _body(self):
                try: return json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
                except (ValueError, TypeError): return None
            def _json(self, status, payload):
                data = json.dumps(payload).encode()
                self.send_response(status); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
            def do_GET(self): self._json(404, {'error': 'not_found'})
            def do_POST(self): self._json(404, {'error': 'not_found'})
        handler = type('Handler', (mixin, Base), {})
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.tmp.cleanup()

    def setUp(self):
        c = sys.modules['database'].connect()
        c.execute('DELETE FROM public_group_registrations')
        c.execute('DELETE FROM group_members')
        c.commit(); c.close()

    def request(self, method, path, body=None, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=20)
        conn.request(method, path, json.dumps(body) if body is not None else None,
                     {'Origin': 'https://adeliatutor.ru', 'Content-Type': 'application/json', **headers})
        response = conn.getresponse(); result = (response.status, json.loads(response.read())); conn.close()
        return result

    def payload(self, **changes):
        return dict(group_id=1, name='Иван', grade=11, contact='@student', timezone='Europe/Moscow', consent=True, **changes)

    def test_public_preview_excludes_private_data(self):
        status, data = self.request('GET', '/api/public/group-registration?group_id=1')
        self.assertEqual(status, 200)
        self.assertEqual(data['slots'][0]['duration_minutes'], 90)
        self.assertEqual(data['group']['price_per_lesson'], 900)
        self.assertNotIn('PRIVATE-BOARD', json.dumps(data))
        self.assertNotIn('members', data['group'])

    def test_no_account_or_membership_created(self):
        status, data = self.request('POST', '/api/public/group-registration', self.payload())
        self.assertEqual((status, data['status']), (200, 'ok'))
        c = sys.modules['database'].connect()
        self.assertEqual(c.execute('SELECT count(*) FROM public_group_registrations').fetchone()[0], 1)
        for table in ['users', 'group_members', 'group_lessons', 'group_join_requests']:
            self.assertEqual(c.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
        c.close()
        row = self.domain.list_for_teacher()[0]
        self.assertEqual((row['group_id'], row['contact']), (1, '@student'))

    def test_concurrent_duplicate_submissions(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: self.request('POST', '/api/public/group-registration', self.payload()), range(5)))
        self.assertTrue(all(status == 200 for status, _ in results))
        self.assertEqual(len(self.domain.list_for_teacher()), 1)
        self.assertTrue(all('id' not in data and 'request_id' not in data for _, data in results))

    def test_waitlist_and_full_group(self):
        body = self.payload(); body['group_id'] = 2
        self.assertTrue(self.request('POST', '/api/public/group-registration', body)[1]['waitlist'])
        c = sys.modules['database'].connect()
        c.executemany("INSERT INTO group_members(group_id,user_id,status,joined_at) VALUES(1,?,'ACTIVE','now')", [(100,), (101,)])
        c.commit(); c.close()
        self.assertTrue(self.request('POST', '/api/public/group-registration', self.payload())[1]['waitlist'])

    def test_closed_inactive_missing_and_validation(self):
        for gid in [3, 4, 999]:
            self.assertEqual(self.request('GET', '/api/public/group-registration?group_id='+str(gid))[0], 404)
            body = self.payload(); body['group_id'] = gid
            self.assertEqual(self.request('POST', '/api/public/group-registration', body)[0], 400)
        for key, value in [('consent', False), ('grade', 12), ('timezone', 'Unknown/Zone'), ('contact', ''), ('name', 'x'*81), ('note', 'x'*601)]:
            body = self.payload(); body[key] = value
            self.assertEqual(self.request('POST', '/api/public/group-registration', body)[0], 400)
        self.assertEqual(self.request('POST', '/api/public/group-registration', [1, 2])[0], 400)

    def test_review_requires_teacher_and_same_origin(self):
        self.request('POST', '/api/public/group-registration', self.payload())
        rid = self.domain.list_for_teacher()[0]['id']
        route = '/api/teacher/group-registration/review'
        body = {'request_id': rid, 'status': 'CONTACTED'}
        self.assertEqual(self.request('POST', route, body)[0], 401)
        self.assertEqual(self.request('POST', route, body, **{'X-Test-Teacher': 'yes', 'Origin': 'https://other.example'})[0], 403)
        self.assertEqual(self.request('POST', route, body, **{'X-Test-Teacher': 'yes'})[0], 200)
        self.assertEqual(self.domain.list_for_teacher()[0]['status'], 'CONTACTED')
        body['status'] = 'CLOSED'
        self.assertEqual(self.request('POST', route, body, **{'X-Test-Teacher': 'yes'})[0], 200)
        self.assertEqual(self.domain.list_for_teacher(), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
