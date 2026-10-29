import unittest
from uuid import uuid4
import self_study_selftest as fixture
from web_backend import self_study_preferences as prefs
from web_backend import self_study_scenes as scenes
from web_backend import self_study_entry as entry
from web_backend.self_study_feedback import context_for


class Tests(unittest.TestCase):
    def setUp(self):
        fixture.study.ensure_schema();prefs.ensure_schema();entry.ensure_schema()
        conn=fixture.connect()
        for table in ('personal_study_preferences','personal_study_profiles','personal_study_attempts','personal_study_entry'):
            conn.execute('DELETE FROM '+table)
        conn.commit();conn.close()
        self.config={'courses':['en','de','es','fa'],'priority':'en','daily_minutes':60,'age_group':'adult',
                     'topics':['oil'],'genres':['drama'],'formats':['speaking'],'goals':{'en':'B1 к концу 7 класса'},
                     'levels':{'en':'A1','de':'C1','es':'A0','fa':'A0'},'target_dates':{'en':'2028-05-31'},
                     'custom_series':[{'title':'Мой любимый сериал','language':'es'}]}

    def test_all_four_courses_and_exact_budget(self):
        prefs.save(-101,self.config);p=fixture.study.profile(-101)
        self.assertEqual(set(self.config['courses']),set(p['languages']))
        self.assertEqual(60,sum(x['minutes'] for x in p['languages'].values()))
        self.assertGreater(p['languages']['en']['minutes'],p['languages']['de']['minutes'])

    def test_new_survey_budget_overrides_existing_default(self):
        fixture.study.save_profile(-101,{'daily_minutes':120})
        prefs.save(-101,{**self.config,'daily_minutes':30})
        self.assertEqual(30,fixture.study.profile(-101)['daily_minutes'])
        fixture.study.save_profile(-101,{'daily_minutes':45})
        self.assertEqual(45,fixture.study.profile(-101)['daily_minutes'])

    def test_personal_minutes_for_all_identities_and_exact_allocation(self):
        for owner in (101,-101,-1000000000101):
            for minutes in (15,20,30,45,60,75,105,121,150,180):
                p=fixture.study.save_profile(owner,{'daily_minutes':minutes})
                self.assertEqual(minutes,fixture.study.profile(owner)['daily_minutes'])
                self.assertEqual(minutes,sum(x['minutes'] for x in p['languages'].values()))
                self.assertTrue(all(x['minutes']>=5 for x in p['languages'].values()))
                self.assertIn(30,p['budget_options'])

    def test_custom_survey_time_and_minimum_for_four_languages(self):
        prefs.save(-101,{**self.config,'daily_minutes':105})
        p=fixture.study.profile(-101)
        self.assertEqual(105,p['daily_minutes'])
        self.assertEqual(105,sum(x['minutes'] for x in p['languages'].values()))
        self.assertEqual(20,p['budget_min_minutes'])
        self.assertNotIn(15,p['budget_options'])
        with self.assertRaises(ValueError):fixture.study.save_profile(-101,{'daily_minutes':15})
        with self.assertRaises(ValueError):prefs.save(-101,{**self.config,'daily_minutes':15})
        self.assertEqual(105,fixture.study.profile(-101)['daily_minutes'])

    def test_invalid_custom_minutes_do_not_change_budget(self):
        for minutes in (True,False,0,-10,14,181,30.5,'60',None):
            with self.assertRaises(ValueError):fixture.study.save_profile(101,{'daily_minutes':minutes})
        self.assertEqual(120,fixture.study.profile(101)['daily_minutes'])

    def test_selected_courses_only_and_no_answer_keys(self):
        prefs.save(-101,{**self.config,'courses':['de'],'priority':'de','custom_series':[]})
        result=fixture.study.overview(-101)
        self.assertEqual({'de'},set(result['courses']))
        self.assertTrue(all('checks' not in x for x in result['courses']['de']))
        self.assertIn('не сформирован',result['profile']['languages']['de']['content_note'])

    def test_goals_and_optional_dates(self):
        prefs.save(-101,self.config);p=fixture.study.profile(-101)
        self.assertEqual('2028-05-31',p['languages']['en']['target_date'])
        self.assertEqual('',p['languages']['de']['target_date'])
        fixture.study.save_profile(-101,{'daily_minutes':60,'target_dates':{'en':'2028-06-01'}})
        self.assertEqual('2028-06-01',fixture.study.profile(-101)['languages']['en']['target_date'])

    def test_diagnostic_not_interest_sets_english_start(self):
        prefs.save(-101,self.config)
        self.assertEqual('en0-01',fixture.study.overview(-101)['courses']['en'][0]['id'])
        from learning.entry_diagnostic import questions
        entry.submit(-101,{'answers':{q['id']:q['answer'] for q in questions(True)}})
        self.assertEqual('en-01',fixture.study.overview(-101)['courses']['en'][0]['id'])

    def test_child_has_short_sessions_and_no_adult_recommendations(self):
        prefs.save(-101,{**self.config,'age_group':'child'})
        result=fixture.study.overview(-101)
        self.assertTrue(all(x['session_minutes']<=15 for x in result['profile']['languages'].values()))
        self.assertFalse({'landman','valeria','schwarzes-gold','ministerio'}&{r['id'] for r in result['resources']})

    def test_interests_rank_landman_first_among_official_resources(self):
        prefs.save(-101,self.config)
        result=fixture.study.overview(-101)
        official=[r for r in result['resources'] if not r['id'].startswith('custom-')]
        self.assertEqual('landman',official[0]['id'])
        self.assertGreater(official[0]['match_score'],0)

    def test_custom_series_can_be_journalled_only_by_owner(self):
        prefs.save(-101,self.config)
        custom=next(r for r in fixture.study.overview(-101)['resources'] if r['id'].startswith('custom-'))
        record=scenes.save_scene(-101,{'resource_id':custom['id'],'season':1,'episode':1,'start_seconds':0,'end_seconds':120,'summary':'Моя заметка','comprehension':'gist','phrases':[],'request_id':str(uuid4())})
        self.assertEqual('es',record['scene']['language'])
        language,prompt=context_for('scene:'+str(record['scene']['id']),-101);self.assertEqual('es',language)
        with self.assertRaises(ValueError):scenes.resource(custom['id'],-202)

    def test_switching_course_does_not_delete_previous_results(self):
        fixture.study.submit(-101,fixture.correct_body())
        prefs.save(-101,{**self.config,'courses':['es'],'priority':'es'})
        self.assertEqual({'es'},set(fixture.study.overview(-101)['courses']))
        prefs.save(-101,self.config)
        en=fixture.study.overview(-101)['courses']['en']
        self.assertEqual(1,next(x for x in en if x['id']=='en-01')['attempt_count'])

    def test_adaptive_focus_uses_results_without_granting_cefr(self):
        prefs.save(-101,self.config);body=fixture.correct_body();body['answers']={k:'wrong' for k in body['answers']}
        fixture.study.submit(-101,body)
        p=fixture.study.overview(-101)['profile']['languages']['en']
        self.assertIn('Снизь сложность',p['practice_focus']);self.assertIn('самооценка',p['start'])

    def test_invalid_survey_does_not_overwrite_settings(self):
        prefs.save(-101,self.config)
        for update in ({'courses':[]},{'courses':['xx']},{'priority':'xx'},{'daily_minutes':True},{'age_group':'other'},
                       {'topics':['invented']},{'target_dates':{'en':'2028-02-30'}},{'custom_series':[{'title':'x','language':'xx'}]}):
            with self.assertRaises(ValueError):prefs.save(-101,{**self.config,**update})
        self.assertEqual(self.config['courses'],prefs.stored(-101)['courses'])
        self.assertIsNone(prefs.stored(-202))


if __name__=='__main__':unittest.main()
