"""Real HTTP/JSON journeys on disposable SQLite and explicit fixture-only identities."""
import json
from threading import Thread
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import unittest
from uuid import uuid4
import self_study_selftest as fixture


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        conn=fixture.connect();conn.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);INSERT INTO users VALUES(101,'Ученица',1);CREATE TABLE parent_accounts(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);INSERT INTO parent_accounts VALUES(101,'Родитель',1);");conn.commit();conn.close()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),fixture.BrowserFixture)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)

    def setUp(self):
        conn=fixture.connect()
        tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'personal_study_%'")]
        for table in tables:conn.execute('DELETE FROM '+table)
        conn.commit();conn.close()

    def request(self,path,role='teacher',body=None,expected=200,origin=True):
        headers={'Cookie':'role='+role}
        if body is not None:
            headers['Content-Type']='application/json'
            if origin:headers['Origin']=self.url
        r=Request(self.url+path,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        try:response=urlopen(r,timeout=10)
        except HTTPError as e:response=e
        with response:
            self.assertEqual(expected,response.status,path)
            self.assertIn('application/json',response.headers.get('Content-Type',''),path)
            return json.load(response)

    def api(self,suffix='',role='teacher',**kwargs):
        return self.request('/api/'+role+'/self-study'+suffix,role=role,**kwargs)

    def invite(self,role):
        token=self.api('/access/invite',body={'account_role':role,'account_id':101})['token']
        return self.api('/access/accept',role=role,body={'token':token})

    def configure_and_place(self,role,language='es'):
        self.invite(role)
        self.api('/preferences/save',role=role,body={'courses':[language],'priority':language,'daily_minutes':30,'age_group':'adult','goals':{},'levels':{},'target_dates':{},'topics':[], 'genres':[], 'formats':[], 'custom_series':[]})
        q=self.api('/placement?language='+language,role=role)['questions']
        self.assertTrue(all('answer' not in x for x in q))
        return self.api('/placement/submit',role=role,body={'language':language,'answers':{x['id']:'unknown' for x in q}})

    def test_all_role_get_routes_return_json_with_auth_denial(self):
        for role in ('teacher','student','parent'):
            self.request('/api/'+role+'/self-study',role='none',expected=401)
        self.request('/api/student/self-study/missing',expected=404)

    def test_family_activation_and_mandatory_placement_over_http(self):
        for role in ('student','parent'):
            self.api(role=role,expected=403);self.invite(role)
            state=self.api(role=role);self.assertTrue(state['placement']['pending'])
            err=self.api('/lesson?id=es-01',role=role,expected=400)
            self.assertEqual('placement_required',err['error'])
            q=self.api('/placement?language=es',role=role)['questions'];self.assertEqual(16,len(q))
            self.assertTrue(self.api('/placement/status',role=role)['required'])

    def test_complete_family_session_and_reload(self):
        for role in ('student','parent'):
            self.configure_and_place(role)
            state=self.api(role=role);self.assertEqual([],state['placement']['pending'])
            route=self.api('/route?language=es',role=role);self.assertTrue(route['enabled']);self.assertEqual('A1',route['current_band'])
            error=self.api('/route/check?language=es&band=A2',role=role,expected=400);self.assertEqual('route_check_locked',error['error'])
            s=self.api('/day/start',role=role,body={'language':'es','minutes':5,'timezone':'Europe/Moscow'})['session']
            self.assertEqual('es-01',s['lesson_id'])
            def update(session,action='advance',**extra):
                return self.api('/day/update',role=role,body={'session_id':session['id'],'version':session['version'],'action':action,**extra})['session']
            s=update(s,'pause');self.assertEqual('PAUSED',self.api('/day?language=es',role=role)['session']['status'])
            s=update(s,'resume');s=update(s)
            error=self.api('/day/update',role=role,expected=400,body={'session_id':s['id'],'version':s['version'],'action':'advance'})
            self.assertEqual('practice_result_required',error['error'])
            self.api('/submit',role=role,body=fixture.correct_body('es-01'))
            s=update(s);s=update(s,reflection='with_help')
            self.assertEqual('FINISHED',s['status']);self.assertIsNone(self.api('/day?language=es',role=role)['session'])
            self.assertEqual('checked_task',s['evidence'][1]['type'])

    def test_vocabulary_day_and_spaced_review_over_http(self):
        self.configure_and_place('parent')
        self.api('/vocabulary/goal',role='parent',body={'language':'es','target':10,'deadline':'2026-11-10'})
        a=self.api('/vocabulary/start',role='parent',body={'language':'es'})
        b=self.api('/vocabulary/start',role='parent',body={'language':'es'})
        self.assertEqual(a['cards'],b['cards']);self.assertGreater(len(a['cards']),0)
        card=self.api('/practice?language=es',role='parent')['items'][0]
        self.assertNotIn('answer',card)
        r=self.api('/review/answer',role='parent',body={'card_id':card['id'],'version':card['version'],'answer':'?', 'request_id':str(uuid4())})
        self.assertFalse(r['correct']);self.assertIn('expected',r)
        self.api('/review/rate',role='parent',body={'review_id':r['review_id'],'rating':'again'})
        self.assertEqual(a['in_deck'],self.api('/vocabulary?language=es',role='parent')['in_deck'])

    def test_same_id_parent_student_and_teacher_are_separate(self):
        for role in ('student','parent'):self.configure_and_place(role)
        self.api('/submit',role='parent',body=fixture.correct_body('es-01'))
        self.assertEqual(1,len(self.api(role='parent')['history']))
        self.assertEqual([],self.api(role='student')['history']);self.assertEqual([],self.api()['history'])
        self.api('/day/start',role='parent',body={'language':'es','minutes':5})
        self.assertIsNone(self.api('/day?language=es',role='student')['session'])

    def test_revoke_only_language_access_after_activation(self):
        self.configure_and_place('parent')
        self.api('/access/revoke',body={'account_role':'parent','account_id':101})
        self.assertEqual('family_access_required',self.api(role='parent',expected=403)['error'])
        conn=fixture.connect()
        try:self.assertEqual(1,conn.execute('SELECT active FROM parent_accounts WHERE id=101').fetchone()[0])
        finally:conn.close()

    def test_cross_origin_post_is_rejected(self):
        self.assertEqual('cross_origin_forbidden',self.api('/access/invite',body={'account_role':'student','account_id':101},expected=403,origin=False)['error'])

    def test_budget_and_dates_refresh_complete_overview(self):
        self.api('/profile',body={'daily_minutes':180,'target_dates':{'en':'2027-09-15'}})
        state=self.api();self.assertEqual(120,state['profile']['languages']['en']['minutes'])
        self.assertEqual('2027-09-15',state['profile']['languages']['en']['target_date'])
        self.assertTrue(any(x['id']==state['profile']['languages']['en']['next_lesson'] for x in state['courses']['en']))

    def test_old_english_entry_updates_new_route_and_preserves_legacy_report(self):
        self.configure_and_place('student','en')
        from learning.family_placement import questions
        answers={q['id']:q['answer'] for q in questions('en',True)}
        result=self.api('/entry/submit',role='student',body={'answers':answers})
        self.assertEqual('B2',result['working_band']);self.assertIn('reading',result);self.assertIn('speaking_tasks',result)
        state=self.api(role='student');self.assertEqual('B2',state['placement']['results']['en']['working_band'])
        self.assertEqual('B2',self.api('/route?language=en',role='student')['start_band'])

    def test_new_features_complete_family_journey_over_http(self):
        for role in ('student','parent'):
            self.configure_and_place(role)
            c=self.api('/conversation/start',role=role,body={'scenario_id':'es-meeting','request_id':str(uuid4())})
            for turn in range(3):
                c=self.api('/conversation/answer',role=role,body={'session_id':c['id'],'version':c['version'],'request_id':str(uuid4()),'text':'Podemos practicar mañana.','intention':'agree','reflection':'with_help' if turn==2 else None})
            self.assertTrue(c['finished'])
            self.api('/skills/start',role=role,body={'language':'es'})
            task=self.api('/skills/task?language=es&skill=writing',role=role)
            self.api('/skills/sample',role=role,body={'language':'es','skill':'writing','form_id':task['form_id'],'request_id':str(uuid4()),'text':'¿Podemos empezar a las siete?','rubric':{k:True for k in task['rubric']}})
            report=self.api('/skills?language=es',role=role);self.assertEqual(1,len(report['writing']['samples']));self.assertEqual(1,report['speaking']['completed_conversations'])
            s=self.api('/listening/start',role=role,body={'source_id':'rtve-ministerio','request_id':str(uuid4())})
            for phase in ('first','second'):s=self.api('/listening/submit',role=role,body={'session_id':s['id'],'phase':phase,'heard':True,'reference':'serie 1, 00:30–01:00','note':'Escucho una pregunta sobre el tiempo.'})
            self.assertEqual('self_report',s['first']['type'])
            self.api('/comfort/save',role=role,body={'minutes':10})
            self.assertEqual(10,self.api('/comfort?language=es',role=role)['short_minutes'])
            day=self.api('/day/start',role=role,body={'language':'es','minutes':25})['session']
            short=self.api('/day/update',role=role,body={'session_id':day['id'],'version':day['version'],'action':'shorten','minutes':5})['session']
            self.assertEqual(5,short['minutes']);self.assertEqual(day['lesson_id'],short['lesson_id']);self.assertEqual(0,short['step'])

    def test_every_learning_asset_is_served_as_javascript(self):
        from pathlib import Path
        for path in (fixture.ROOT/'web').glob('self_study*.js'):
            with urlopen(self.url+'/app/'+path.name,timeout=5) as response:
                self.assertIn('javascript',response.headers.get('Content-Type',''));self.assertEqual(path.read_bytes(),response.read())


if __name__=='__main__':unittest.main()
