import unittest
from uuid import uuid4
import self_study_selftest as fixture
from learning.family_placement import questions,assess
from web_backend import self_study_placement as placement,self_study_preferences as prefs,self_study_entry as entry,self_study_access as access
from web_backend.self_study_api import ROOT
from self_study_access_selftest import Student,Parent


def config(codes):
    return {'courses':codes,'priority':codes[0],'daily_minutes':60,'age_group':'adult','topics':[],'genres':[],'formats':[],'goals':{},'levels':{},'target_dates':{},'custom_series':[]}


def answers(code,correct=False):return {q['id']:q['answer'] if correct else 'unknown' for q in questions(code,True)}


class Tests(unittest.TestCase):
    def setUp(self):
        self.owner=-int(uuid4().hex[:7],16)

    def test_all_banks_hide_answers_and_have_new_reading(self):
        for code in ('en','de','es','fa'):
            public=questions(code);private=questions(code,True)
            self.assertTrue(all('answer' not in q for q in public));self.assertTrue(all(q['answer'] in q['options'] for q in private))
            self.assertGreaterEqual(sum(q['skill']=='reading' for q in public),3)

    def test_unknown_is_valid_beginner_result_in_every_language(self):
        for code in ('en','de','es','fa'):self.assertEqual('A0',assess(code,answers(code))['working_band'])

    def test_high_result_is_b2_screen_not_c1_certificate(self):
        for code in ('en','de','es','fa'):
            r=assess(code,answers(code,True));self.assertEqual('B2',r['working_band']);self.assertIn('не подтверждаются',r['note'])

    def test_advanced_guesses_do_not_skip_missing_foundation(self):
        for code in ('en','de','es','fa'):
            a=answers(code)
            for q in questions(code,True):
                if q['band']=='B2':a[q['id']]=q['answer']
            self.assertEqual('A0',assess(code,a)['working_band'])

    def test_invalid_or_incomplete_answers_do_not_save(self):
        for a in ({}, {'g0':'invented'},answers('de')|{'extra':'unknown'}):
            with self.assertRaises(ValueError):placement.submit(self.owner,{'language':'de','answers':a})
        self.assertIsNone(placement.result(self.owner,'de'))

    def test_each_selected_course_requires_its_own_check(self):
        prefs.save(self.owner,config(['en','de','es','fa']))
        self.assertEqual(4,len(placement.status(self.owner)['pending']))
        placement.submit(self.owner,{'language':'es','answers':answers('es')})
        self.assertEqual({'en','de','fa'},set(placement.status(self.owner)['pending']))

    def test_owner_is_exempt_but_can_take_test(self):
        self.assertFalse(placement.status(abs(self.owner))['required']);self.assertEqual([],placement.status(abs(self.owner))['pending'])
        placement.submit(abs(self.owner),{'language':'de','answers':answers('de',True)})
        self.assertEqual('B2',placement.result(abs(self.owner),'de')['working_band'])

    def test_existing_english_check_is_credited(self):
        entry.submit(self.owner,{'answers':answers('en')})
        self.assertTrue(placement.result(self.owner,'en')['legacy']);self.assertNotIn('en',placement.status(self.owner)['pending'])

    def test_result_is_private_to_account_and_language(self):
        placement.submit(self.owner,{'language':'fa','answers':answers('fa')})
        self.assertIsNone(placement.result(self.owner-1,'fa'));self.assertIsNone(placement.result(self.owner,'de'))

    def test_zero_english_routes_to_foundation_after_test(self):
        prefs.save(self.owner,config(['en']))
        placement.submit(self.owner,{'language':'en','answers':answers('en')})
        state=fixture.study.overview(self.owner)
        self.assertEqual('en0-01',state['courses']['en'][0]['id']);self.assertIn('A0',state['profile']['languages']['en']['start'])

    def test_strong_screen_and_c1_history_allow_advanced_challenge(self):
        prefs.save(self.owner,{**config(['de']),'levels':{'de':'C1'}})
        placement.submit(self.owner,{'language':'de','answers':answers('de',True)})
        s=fixture.study.overview(self.owner)
        self.assertEqual('dex-01',s['courses']['de'][0]['id']);self.assertIn('уровень не подтверждён',s['profile']['languages']['de']['start'])

    def test_german_beginner_result_gets_foundation_modules(self):
        prefs.save(self.owner,config(['de']))
        placement.submit(self.owner,{'language':'de','answers':answers('de')})
        state=fixture.study.overview(self.owner);self.assertEqual('de0-01',state['courses']['de'][0]['id'])
        from learning.beginner_languages import units
        from learning.language_program import lesson
        for item in units('de'):
            self.assertTrue(all('answers' not in q for q in lesson(item['id'])['checks']))
            self.assertEqual(4,fixture.study.submit(self.owner,fixture.correct_body(item['id']))['correct'])

    def test_recommendation_has_concrete_goal_without_changing_user_goal(self):
        prefs.save(self.owner,{**config(['es']),'goals':{'es':'Путешествия'},'target_dates':{'es':'2027-05-01'}})
        r=placement.submit(self.owner,{'language':'es','answers':answers('es')})['recommendation']
        self.assertTrue(r['goal']);self.assertTrue(r['review_date']);self.assertEqual('A1',r['suggested_next_band'])
        self.assertEqual('Путешествия',fixture.study.profile(self.owner)['languages']['es']['goal'])
        self.assertEqual('2027-05-01',fixture.study.profile(self.owner)['languages']['es']['target_date'])

    def test_new_selected_language_requires_only_missing_check(self):
        prefs.save(self.owner,config(['es']));placement.submit(self.owner,{'language':'es','answers':answers('es')})
        self.assertEqual([],placement.status(self.owner)['pending'])
        prefs.save(self.owner,config(['es','fa']));self.assertEqual(['fa'],placement.status(self.owner)['pending'])

    def test_api_blocks_direct_learning_links_until_all_selected_tests(self):
        access.ensure_schema();placement.ensure_schema();entry.ensure_schema();prefs.ensure_schema();fixture.study.ensure_schema()
        conn=fixture.connect();conn.execute("INSERT OR REPLACE INTO personal_study_memberships VALUES('student:101',101,1,'2026-10-27')")
        for table in ('personal_study_entry','personal_study_placement','personal_study_preferences','personal_study_profiles'):
            conn.execute('DELETE FROM '+table+' WHERE owner_id=?',(-101,))
        conn.commit();conn.close();prefs.save(-101,config(['es','fa']))
        root=ROOT.replace('/teacher/','/student/')
        for path,q in (('/lesson',{'id':['es-01']}),('/practice',{'language':['es']}),('/vocabulary',{'language':['es']})):
            code,r=Student().self_study_route(root+path,q);self.assertEqual(400,code);self.assertEqual('placement_required',r['error'])
        self.assertEqual(200,Student().self_study_route(root+'/placement',{'language':['es']})[0])
        for lang in ('es','fa'):
            code,_=Student(body={'language':lang,'answers':answers(lang),'owner_id':101}).self_study_route(root+'/placement/submit',write=True)
            self.assertEqual(200,code)
        self.assertEqual(200,Student().self_study_route(root+'/lesson',{'id':['es-01']})[0])
        self.assertIsNone(placement.result(101,'es'))
        self.assertEqual(401,Student(teacher=None).self_study_route(root+'/placement')[0])
        self.assertEqual(403,Student(body={},origin=False).self_study_route(root+'/placement/submit',write=True)[0])

    def test_parent_and_student_same_id_have_independent_checks(self):
        student=access.study_identity('student',101);parent=access.study_identity('parent',101)
        placement.submit(parent,{'language':'de','answers':answers('de',True)})
        self.assertIsNone(placement.result(student,'de'));self.assertEqual('B2',placement.result(parent,'de')['working_band'])


if __name__=='__main__':unittest.main()
