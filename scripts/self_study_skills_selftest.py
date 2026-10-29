import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import self_study_selftest as f
from web_backend import self_study_skills as skills,self_study_listening as listening

class Tests(unittest.TestCase):
 def setUp(self):self.owner=int(uuid4().hex[:7],16)+1000;self.now=datetime(2026,10,27,12,tzinfo=timezone.utc)
 def body(self,skill='writing'):
  skills.cycle(self.owner,'en',start=True);t=skills.task(self.owner,'en',skill)
  return {'language':'en','skill':skill,'form_id':t['form_id'],'request_id':str(uuid4()),'text':'Could we meet at seven?','rubric':{k:True for k in t['rubric']}}
 def test_empty_report_has_four_skills_and_no_fake_scores(self):
  r=skills.report(self.owner,'en');self.assertEqual([],r['reading']['first_by_band']);self.assertEqual([],r['listening']['attempts']);self.assertEqual('self_report',r['speaking']['verification']);self.assertEqual([],r['writing']['samples']);self.assertNotIn('cefr',r)
 def test_task_requires_cycle(self):
  with self.assertRaisesRegex(ValueError,'skill_cycle_required'):skills.task(self.owner,'en','writing')
 def test_cycle_dates_do_not_slide_or_start_early(self):
  with patch.object(skills,'clock',return_value=self.now):a=skills.cycle(self.owner,'en',True)
  with patch.object(skills,'clock',return_value=self.now+timedelta(days=27)):b=skills.cycle(self.owner,'en',True)
  self.assertEqual(a['started_at'],b['started_at']);self.assertEqual(a['next_at'],b['next_at']);self.assertEqual('A',b['form_id'])
 def test_second_form_and_exhaustion(self):
  with patch.object(skills,'clock',return_value=self.now):skills.cycle(self.owner,'en',True)
  with patch.object(skills,'clock',return_value=self.now+timedelta(days=28)):self.assertEqual('B',skills.cycle(self.owner,'en',True)['form_id'])
  with patch.object(skills,'clock',return_value=self.now+timedelta(days=56)):
   with self.assertRaisesRegex(ValueError,'skill_forms_exhausted'):skills.cycle(self.owner,'en',True)
 def test_saved_writing_is_private_self_report(self):
  skills.save(self.owner,self.body());r=skills.report(self.owner,'en');self.assertEqual(1,len(r['writing']['samples']));self.assertEqual([],skills.report(self.owner+1,'en')['writing']['samples']);self.assertNotIn('correct',r['writing']['samples'][0])
 def test_uuid_retry_and_conflict(self):
  b=self.body();a=skills.save(self.owner,b);self.assertEqual(a,skills.save(self.owner,b));b['text']='Something else'
  with self.assertRaisesRegex(ValueError,'request_conflict'):skills.save(self.owner,b)
 def test_invalid_rubric_is_not_saved(self):
  b=self.body();b['rubric']['purpose']='yes'
  with self.assertRaisesRegex(ValueError,'invalid_skill_sample'):skills.save(self.owner,b)
  self.assertEqual([],skills.report(self.owner,'en')['writing']['samples'])
 def test_invalid_form_is_rejected(self):
  b=self.body();b['form_id']='B'
  with self.assertRaisesRegex(ValueError,'skill_form_changed'):skills.save(self.owner,b)
 def test_speaking_has_no_automatic_pronunciation_score(self):
  skills.save(self.owner,self.body('speaking'));r=skills.report(self.owner,'en');self.assertEqual(1,len(r['speaking']['samples']));self.assertNotIn('score',r['speaking'])
 def test_same_recording_is_marked_familiar_in_new_session(self):
  for _ in range(2):
   s=listening.start(self.owner,{'source_id':'bc-table','request_id':str(uuid4())});listening.submit(self.owner,{'session_id':s['id'],'phase':'first','heard':True,'answers':{'people':'6','time':'20:00'}})
  r=skills.report(self.owner,'en')['listening']['attempts'];self.assertFalse(r[0]['familiar']);self.assertTrue(r[1]['familiar'])
 def test_no_lesson_or_level_score_created(self):
  skills.save(self.owner,self.body());self.assertEqual([],f.study.overview(self.owner)['history'])
 def test_disabled_course_and_invalid_skill(self):
  with self.assertRaisesRegex(ValueError,'invalid_language'):skills.report(self.owner,'es')
  with self.assertRaisesRegex(ValueError,'invalid_skill'):skills.task(self.owner,'en','math')
 def test_api_aliases_auth_and_origin(self):
  from web_backend.self_study_api import ROOT,GET_PATHS,POST_PATHS
  self.assertIn(ROOT.replace('/teacher/','/parent/')+'/skills',GET_PATHS);self.assertIn(ROOT.replace('/teacher/','/student/')+'/skills/sample',POST_PATHS)
  self.assertEqual(401,f.FakeHandler(teacher=None).self_study_route(ROOT+'/skills')[0]);self.assertEqual(403,f.FakeHandler(origin=False).self_study_route(ROOT+'/skills/start',write=True)[0]);self.assertEqual(200,f.FakeHandler().self_study_route(ROOT+'/skills',{'language':['en']})[0])

if __name__=='__main__':unittest.main()
