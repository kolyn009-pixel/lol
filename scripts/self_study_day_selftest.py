"""Resumable journeys against disposable SQLite, with real grading and review APIs."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import self_study_selftest as fixture
from web_backend import self_study_day as day, self_study_practice as practice
from web_backend import self_study_preferences as prefs


class Tests(unittest.TestCase):
    def setUp(self):
        self.owner=80000+int(uuid4().hex[:7],16)

    def start(self,language='en',minutes=10):
        return day.start(self.owner,{'language':language,'minutes':minutes,'timezone':'Europe/Moscow'})['session']

    def advance(self,s,action='advance',**extra):
        return day.update(self.owner,{'session_id':s['id'],'version':s['version'],'action':action,**extra})['session']

    def test_daily_api_uses_existing_auth_and_origin_guards(self):
        from web_backend.self_study_api import ROOT,GET_PATHS,POST_PATHS
        self.assertIn(ROOT.replace('/teacher/','/parent/')+'/day',GET_PATHS)
        self.assertIn(ROOT.replace('/teacher/','/student/')+'/day/update',POST_PATHS)
        self.assertEqual(401,fixture.FakeHandler(teacher=None).self_study_route(ROOT+'/day')[0])
        self.assertEqual(403,fixture.FakeHandler(origin=False).self_study_route(ROOT+'/day/start',write=True)[0])
        handler=fixture.FakeHandler(body={'language':'en','minutes':5})
        code,result=handler.self_study_route(ROOT+'/day/start',write=True)
        self.assertEqual(200,code);self.assertEqual('en',result['session']['language'])
        self.assertEqual(200,fixture.FakeHandler().self_study_route(ROOT+'/day',{'language':['en']})[0])

    def test_plan_has_exact_positive_budget(self):
        for n in range(5,121):
            for reviews in (True,False):
                p=day._plan(n,reviews)
                self.assertEqual(n,sum(x['minutes'] for x in p));self.assertTrue(all(x['minutes']>0 for x in p))

    def test_start_and_resume_pin_material_and_hide_answers(self):
        s=self.start();self.assertNotIn('owner_id',s)
        self.assertTrue(all('answers' not in x for x in s['material']['checks']))
        self.assertEqual(s['id'],self.start()['id'])
        self.assertEqual(s,day.current(self.owner,'en')['session'])

    def test_parallel_start_creates_one_session(self):
        self.start()  # initialise schemas before racing requests
        with ThreadPoolExecutor(4) as pool:rows=list(pool.map(lambda _:self.start(),range(4)))
        self.assertEqual(1,len({s['id'] for s in rows}))

    def test_invalid_time_and_zone(self):
        for n in (0,4,999,True,'10'):
            with self.assertRaisesRegex(ValueError,'invalid_session_minutes'):self.start(minutes=n)
        with self.assertRaisesRegex(ValueError,'invalid_timezone'):
            day.start(self.owner,{'language':'en','minutes':10,'timezone':'not/a/zone'})

    def test_account_and_language_isolation(self):
        s=self.start();self.assertIsNone(day.current(self.owner+1,'en')['session'])
        self.assertIsNone(day.current(self.owner,'de')['session'])
        with self.assertRaisesRegex(ValueError,'session_not_found'):
            day.update(self.owner+1,{'session_id':s['id'],'version':s['version'],'action':'advance'})

    def test_stale_update_cannot_advance_twice(self):
        s=self.start();self.advance(s)
        with self.assertRaisesRegex(ValueError,'session_changed'):self.advance(s)

    def test_pause_survives_reload(self):
        s=self.advance(self.start(),'pause');self.assertEqual('PAUSED',day.current(self.owner,'en')['session']['status'])
        with self.assertRaisesRegex(ValueError,'session_paused'):self.advance(s)
        s=self.advance(s,'resume');self.assertEqual(0,s['step']);self.assertEqual('ACTIVE',s['status'])

    def test_old_or_other_lesson_result_cannot_complete_practice(self):
        fixture.study.submit(self.owner,fixture.correct_body('en-01'));s=self.start();s=self.advance(s)
        fixture.study.submit(self.owner,fixture.correct_body('en-03'))
        with self.assertRaisesRegex(ValueError,'practice_result_required'):self.advance(s)

    def test_complete_journey_separates_evidence(self):
        s=self.advance(self.start())
        fixture.study.submit(self.owner,fixture.correct_body(s['lesson_id']))
        s=self.advance(s)
        with self.assertRaisesRegex(ValueError,'reflection_required'):self.advance(s)
        s=self.advance(s,reflection='with_help')
        self.assertEqual('FINISHED',s['status']);self.assertEqual(['self_report','checked_task','self_report'],[x['type'] for x in s['evidence']])
        self.assertEqual(4,s['evidence'][1]['correct']);self.assertIsNone(day.current(self.owner,'en')['session'])

    def review_start(self):
        fixture.study.submit(self.owner,fixture.correct_body('en-01'))
        s=self.start(minutes=25);self.assertEqual('review',s['plan'][0]['kind']);return s

    def test_review_requires_rating_and_language_match(self):
        s=self.review_start()
        fixture.study.submit(self.owner,fixture.correct_body('de-01'))
        card=practice.practice(self.owner,'de')['items'][0]
        answer=practice.answer_card(self.owner,{'card_id':card['id'],'version':card['version'],'answer':'?', 'request_id':str(uuid4())})
        practice.rate_card(self.owner,{'review_id':answer['review_id'],'rating':'again'})
        with self.assertRaisesRegex(ValueError,'review_result_required'):self.advance(s)
        card=practice.practice(self.owner,'en')['items'][0]
        answer=practice.answer_card(self.owner,{'card_id':card['id'],'version':card['version'],'answer':'?', 'request_id':str(uuid4())})
        with self.assertRaisesRegex(ValueError,'review_result_required'):self.advance(s)
        practice.rate_card(self.owner,{'review_id':answer['review_id'],'rating':'again'})
        self.assertEqual('recorded_review',self.advance(s)['evidence'][0]['type'])

    def test_explicit_review_skip_is_not_success(self):
        s=self.advance(self.review_start(),'skip_review');self.assertEqual('skipped',s['evidence'][0]['type'])
        with self.assertRaisesRegex(ValueError,'invalid_session'):self.advance(s,'skip_review')

    def test_unknown_family_english_starts_with_diagnostic(self):
        self.owner=-self.owner
        self.assertEqual('diagnostic',day.start(self.owner,{'language':'en','minutes':10})['action'])
        self.assertIsNone(day.current(self.owner,'en')['session'])

    def test_disabled_course_rejected(self):
        prefs.save(self.owner,{'courses':['es'],'priority':'es','daily_minutes':30,'age_group':'adult','topics':[], 'genres':[], 'formats':[], 'goals':{},'levels':{},'target_dates':{},'custom_series':[]})
        with self.assertRaisesRegex(ValueError,'invalid_language'):self.start()
        self.assertEqual('es',self.start('es')['language'])

    def test_draft_is_selected_first(self):
        fixture.study.save_draft(self.owner,{'lesson_id':'en-03','answers':{}})
        self.assertEqual('en-03',self.start()['lesson_id'])

    def test_exhausted_content_note_survives_resume(self):
        state=fixture.study.overview(self.owner)
        for item in state['courses']['en']:fixture.study.submit(self.owner,fixture.correct_body(item['id']))
        s=self.start();self.assertTrue(s['content_exhausted']);self.assertIn('закрепляем знакомое',day.current(self.owner,'en')['session']['note'])


if __name__=='__main__':unittest.main()
