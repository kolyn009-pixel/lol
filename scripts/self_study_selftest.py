"""Stage-1 integration tests; disposable SQLite, never the TutorBot database.

--serve starts a local fixture for the browser tests (fake teacher login only).
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import ModuleType
import unittest
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from threading import Thread
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TEMP=tempfile.TemporaryDirectory()
DB=Path(TEMP.name)/'self-study.db'


def connect():
    conn=sqlite3.connect(DB,timeout=10)
    conn.row_factory=sqlite3.Row
    return conn


conn=connect();conn.executescript("CREATE TABLE admin_accounts(telegram_id INTEGER PRIMARY KEY,role TEXT,active INTEGER); INSERT INTO admin_accounts VALUES(9,'OWNER',1),(101,'OWNER',1),(202,'OWNER',1);");conn.commit();conn.close()
database=ModuleType('database');database.connect=connect
sys.modules['database']=database
from learning.language_program import LANGUAGES, RESOURCES, catalogue, lesson
from web_backend import self_study as study
from web_backend.self_study_api import SelfStudyMixin, ROOT as API_ROOT


def correct_body(lesson_id='en-01',request_id=None):
    item=lesson(lesson_id,True)
    return {'lesson_id':lesson_id,'request_id':request_id or str(uuid4()),
            'answers':{q['id']:q['answers'][0] for q in item['checks']}}


class FakeHandler(SelfStudyMixin):
    def __init__(self,teacher=101,body=None,origin=True):
        self.teacher=teacher;self.body=body;self.origin=origin;self.body_read=False
    def _teacher(self):
        return {'role':'teacher','id':self.teacher,'admin_telegram_id':self.teacher} if self.teacher else None
    def _same_origin_write(self):return self.origin
    def _body(self):self.body_read=True;return self.body
    def _json(self,status,payload):return status,payload


class Tests(unittest.TestCase):
    def setUp(self):
        study.ensure_schema()
        conn=connect()
        for name in ('profiles','attempts','drafts'):
            conn.execute('DELETE FROM personal_study_'+name)
        conn.commit();conn.close()

    def test_program_every_lesson_grades_and_never_exposes_keys(self):
        ids=[x['id'] for items in catalogue().values() for x in items]
        self.assertEqual(28,len(ids));self.assertEqual(len(ids),len(set(ids)))
        for lesson_id in ids:
            item=study.get_lesson(101,lesson_id)
            self.assertEqual(4,len(item['checks']))
            self.assertTrue(item['speaking'] and item['passage'])
            for q in item['checks']:
                self.assertNotIn('answers',q);self.assertNotIn('explanation',q)
            result=study.submit(101,correct_body(lesson_id))
            self.assertEqual((4,4,True),(result['correct'],result['total'],result['passed']))

    def test_defaults_and_three_hour_allocation(self):
        p=study.profile(101)
        self.assertEqual(120,sum(x['minutes'] for x in p['languages'].values()))
        p=study.save_profile(101,{'daily_minutes':180})
        self.assertEqual(180,sum(x['minutes'] for x in p['languages'].values()))
        self.assertEqual('2027-09-01',p['languages']['en']['target_date'])
        self.assertEqual(120,study.profile(202)['daily_minutes'])

    def test_settings_survive_new_connection(self):
        study.save_profile(101,{'daily_minutes':120,'target_dates':{'en':'2027-09-15'}})
        self.assertEqual('2027-09-15',study.profile(101)['languages']['en']['target_date'])

    def test_bad_settings_do_not_partially_write(self):
        for body in ({'daily_minutes':True},{'daily_minutes':121},
                     {'daily_minutes':180,'target_dates':{'en':'2027-02-30'}},
                     {'daily_minutes':180,'target_dates':{'xx':'2027-01-01'}},
                     {'daily_minutes':180,'target_dates':{'en':123}}):
            with self.assertRaises(ValueError):study.save_profile(101,body)
        self.assertEqual(120,study.profile(101)['daily_minutes'])

    def test_draft_is_private_and_restored(self):
        study.save_draft(101,{'lesson_id':'en-01','answers':{'d0':' used to '},'owner_id':202})
        self.assertEqual({'d0':'used to'},study.get_lesson(101,'en-01')['draft'])
        self.assertEqual({},study.get_lesson(202,'en-01')['draft'])
        study.submit(101,correct_body())
        self.assertEqual({},study.get_lesson(101,'en-01')['draft'])

    def test_double_submit_is_idempotent_even_concurrently(self):
        body=correct_body()
        # Schema is already prepared; production requests may race after retries.
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:study.submit(101,body),range(4)))
        self.assertTrue(all(x==results[0] for x in results))
        self.assertEqual(1,len(study.overview(101)['history']))

    def test_uuid_cannot_be_reused_with_changed_answers(self):
        body=correct_body();study.submit(101,body);body['answers']['d0']='different'
        with self.assertRaisesRegex(ValueError,'request_conflict'):study.submit(101,body)

    def test_uuid_scope_is_owner(self):
        body=correct_body();study.submit(101,body);study.submit(202,body)
        self.assertEqual(1,len(study.overview(101)['history']))
        self.assertEqual(1,len(study.overview(202)['history']))

    def test_latest_attempt_drives_progress_not_best_score(self):
        study.submit(101,correct_body())
        wrong=correct_body();wrong['answers']={k:'wrong' for k in wrong['answers']}
        result=study.submit(101,wrong)
        self.assertFalse(result['passed']);self.assertEqual(2,result['attempt_number'])
        item=study.overview(101)['courses']['en'][0]
        self.assertEqual(4,item['first']['correct']);self.assertEqual(0,item['latest']['correct'])
        self.assertFalse(item['passed']);self.assertEqual(0,study.overview(202)['profile']['languages']['en']['completed'])

    def test_missing_or_unexpected_answers_cannot_create_progress(self):
        for answers in ({},{'q0':'something'},{'d0':[]},{'extra':'x'}):
            with self.assertRaises(ValueError):study.submit(101,{'lesson_id':'en-01','answers':answers,'request_id':str(uuid4())})
        self.assertEqual([],study.overview(101)['history'])

    def test_normalisation_handles_persian_variants_and_punctuation(self):
        self.assertEqual(study.normalise('يك چاي!'),study.normalise('یک چای'))
        self.assertEqual(study.normalise('  USED   TO. '),'used to')
        body=correct_body('fa-03');body['answers']['d0']='بدون شكر.'
        self.assertEqual(4,study.submit(101,body)['correct'])

    def test_wrong_language_or_lesson_is_rejected(self):
        for lesson_id in ('xx-01','en-00','en-99',None,'../../database.py'):
            with self.assertRaises(ValueError):study.get_lesson(101,lesson_id)

    def test_authentication_before_parsing_body(self):
        handler=FakeHandler(teacher=None,body=correct_body())
        self.assertEqual(401,handler.self_study_route(API_ROOT+'/submit',write=True)[0])
        self.assertFalse(handler.body_read)

    def test_csrf_rejected_before_mutation(self):
        handler=FakeHandler(body=correct_body(),origin=False)
        self.assertEqual(403,handler.self_study_route(API_ROOT+'/submit',write=True)[0])
        self.assertFalse(handler.body_read);self.assertEqual([],study.overview(101)['history'])

    def test_client_identity_is_ignored(self):
        body=correct_body();body.update(owner_id=202,user_id=202)
        handler=FakeHandler(body=body)
        self.assertEqual(200,handler.self_study_route(API_ROOT+'/submit',write=True)[0])
        self.assertEqual(1,len(study.overview(101)['history']))
        self.assertEqual([],study.overview(202)['history'])

    def test_malformed_body_and_input_return_validation_error(self):
        for body in (None,[],{'lesson_id':'en-01','request_id':None,'answers':correct_body()['answers']}):
            status,result=FakeHandler(body=body).self_study_route(API_ROOT+'/submit',write=True)
            self.assertEqual(400,status)
        status,result=FakeHandler().self_study_route(API_ROOT+'/lesson',{'id':['missing']})
        self.assertEqual((400,'lesson_not_found'),(status,result['error']))

    def test_schema_is_additive_and_idempotent(self):
        conn=connect();conn.execute('CREATE TABLE IF NOT EXISTS pupils_guard (value TEXT)')
        conn.execute('DELETE FROM pupils_guard');conn.execute("INSERT INTO pupils_guard VALUES('untouched')");conn.commit();conn.close()
        study.ensure_schema();study.ensure_schema()
        conn=connect();self.assertEqual('untouched',conn.execute('SELECT value FROM pupils_guard').fetchone()[0]);conn.close()

    def test_http_round_trip_and_origin_denial(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),BrowserFixture)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def request(path,body=None,authenticated=True,origin=None):
            headers={'Cookie':'role=teacher'} if authenticated else {}
            if body is not None:headers.update({'Content-Type':'application/json','Origin':origin or base})
            req=Request(base+API_ROOT+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            try:
                with urlopen(req,timeout=3) as response:return response.status,json.loads(response.read())
            except HTTPError as exc:return exc.code,json.loads(exc.read())
        try:
            self.assertEqual(401,request('',authenticated=False)[0])
            self.assertEqual(200,request('')[0])
            body=correct_body('de-01')
            self.assertEqual(403,request('/submit',body,origin='https://other.example')[0])
            status,data=request('/submit',body)
            self.assertEqual((200,4),(status,data['correct']))
            self.assertEqual(1,request('')[1]['profile']['languages']['de']['completed'])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)


class BrowserFixture(SelfStudyMixin,BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def _teacher(self):
        return {'id':101,'admin_telegram_id':101,'role':'teacher'} if 'role=teacher' in self.headers.get('Cookie','') else None
    def _auth(self):
        role='parent' if 'role=parent' in self.headers.get('Cookie','') else 'student' if 'role=student' in self.headers.get('Cookie','') else 'teacher'
        return {'id':101,'role':role}
    def _student(self):
        return {'id':101,'role':'student'} if 'role=student' in self.headers.get('Cookie','') else None
    def _same_origin_write(self):
        return self.headers.get('Origin')=='http://'+self.headers['Host']
    def _body(self):
        try:return json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
        except Exception:return None
    def _json(self,status,payload):
        body=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_POST(self):
        return self.self_study_route(urlparse(self.path).path,write=True)
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path.startswith(API_ROOT):return self.self_study_route(parsed.path,parse_qs(parsed.query))
        if parsed.path=='/app/self-study.html':
            body=(ROOT/'web/self-study.html').read_bytes();ctype='text/html; charset=utf-8'
        elif parsed.path in ('/app/self_study.css','/app/self_study.js','/app/self_study_voice.js','/app/self_study_scenes.js','/app/self_study_settings.js'):
            body=(ROOT/'web'/Path(parsed.path).name).read_bytes()
            ctype='text/css' if parsed.path.endswith('.css') else 'text/javascript'
        else:
            body=('''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/app/self_study.css"><style>body{font-family:Arial;background:#f7f6fb;margin:0;color:#24213b}.teacher-shell{display:grid;grid-template-columns:190px 1fr}aside{padding:20px;background:white}nav{display:grid;gap:10px}nav button{padding:12px;background:#eee8ff;border:0;border-radius:10px}main{padding:24px;min-width:0}header{margin-bottom:20px}h1{font-size:24px}@media(max-width:650px){.teacher-shell{grid-template-columns:1fr}aside{padding:10px}nav{display:flex}main{padding:12px}}</style></head><body><div class="teacher-shell"><aside><nav><button data-view="dashboard">Сегодня</button><button data-self-study>Моё обучение</button></nav></aside><main><header><h1 id="title">Сегодня</h1></header><div id="app">Рабочий кабинет</div></main></div><script>document.querySelector('[data-view]').onclick=()=>{document.querySelector('#title').textContent='Сегодня';document.querySelector('#app').textContent='Рабочий кабинет'}</script><script src="/app/self_study.js"></script><script src="/app/self_study_voice.js"></script><script src="/app/self_study_scenes.js"></script><script src="/app/self_study_settings.js"></script></body></html>''').encode()
            ctype='text/html; charset=utf-8'
        self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


if __name__=='__main__':
    if '--serve' in sys.argv:
        conn=connect();conn.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);INSERT INTO users VALUES(101,'Ученица',1);CREATE TABLE parent_accounts(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);INSERT INTO parent_accounts VALUES(101,'Родитель',1);");conn.commit();conn.close()
        server=ThreadingHTTPServer(('127.0.0.1',0),BrowserFixture)
        print(json.dumps({'port':server.server_port}),flush=True)
        try:server.serve_forever()
        finally:server.server_close();TEMP.cleanup()
    else:
        unittest.main()
