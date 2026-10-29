import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import self_study_selftest as f
from web_backend import self_study_comfort as comfort,self_study_day as day

class Tests(unittest.TestCase):
 def setUp(self):self.owner=int(uuid4().hex[:7],16)+1000;self.now=datetime(2026,10,27,12,tzinfo=timezone.utc)
 def start(self):return day.start(self.owner,{'language':'en','minutes':25})['session']
 def change(self,s,action='shorten',**extra):return day.update(self.owner,{'session_id':s['id'],'version':s['version'],'action':action,**extra})['session']
 def test_shortening_keeps_lesson_step_and_evidence(self):
  s=self.change(self.start(),'advance');before=s['evidence'];s=self.change(s,minutes=5)
  self.assertEqual(1,s['step']);self.assertEqual(before,s['evidence']);self.assertEqual(5,sum(x['minutes'] for x in s['plan'][s['step']:]))
 def test_shortening_does_not_bypass_real_check(self):
  s=self.change(self.start(),'advance');s=self.change(s,minutes=5)
  with self.assertRaisesRegex(ValueError,'practice_result_required'):self.change(s,'advance')
 def test_shortening_resumes_pause(self):
  s=self.change(self.start(),'pause');s=self.change(s,minutes=5);self.assertEqual('ACTIVE',s['status']);self.assertTrue(all(x['minutes']>0 for x in s['plan']))
 def test_shortening_does_not_extend_already_short_plan(self):
  s=day.start(self.owner,{'language':'en','minutes':5})['session'];s=self.change(s,minutes=10);self.assertEqual(5,s['minutes'])
 def test_stale_shortening_is_rejected(self):
  s=self.start();self.change(s,minutes=5)
  with self.assertRaisesRegex(ValueError,'session_changed'):self.change(s,minutes=5)
 def test_invalid_short_minutes(self):
  s=self.start()
  for value in (True,0,15,'5'):
   with self.assertRaises(ValueError):self.change(s,minutes=value)
   with self.assertRaises(ValueError):comfort.save(self.owner,{'minutes':value})
 def test_preferences_private(self):
  comfort.save(self.owner,{'minutes':10});self.assertEqual(10,comfort.report(self.owner,'en')['short_minutes']);self.assertEqual(5,comfort.report(self.owner+1,'en')['short_minutes'])
 def test_new_account_is_not_told_it_missed_days(self):
  r=comfort.report(self.owner,'en');self.assertIsNone(r['gap_days']);self.assertFalse(r['returning'])
 def test_return_after_pause_is_detected_without_writing_scores(self):
  f.study.submit(self.owner,f.correct_body('en-01'));conn=f.connect();conn.execute('UPDATE personal_study_attempts SET created_at=? WHERE owner_id=?',((self.now-timedelta(days=7)).isoformat(),self.owner));conn.commit();conn.close()
  with patch.object(comfort,'clock',return_value=self.now):r=comfort.report(self.owner,'en')
  self.assertTrue(r['returning']);self.assertEqual(7,r['gap_days']);self.assertEqual(1,len(f.study.overview(self.owner)['history']))
 def test_deadline_warning_is_lower_bound_and_does_not_change_goal(self):
  f.study.save_profile(self.owner,{'daily_minutes':120,'target_dates':{'en':'2026-10-27'}})
  with patch.object(comfort,'clock',return_value=self.now):r=comfort.report(self.owner,'en')
  self.assertTrue(r['deadline_tight_for_modules']);self.assertEqual('2026-10-27',f.study.profile(self.owner)['languages']['en']['target_date']);self.assertIn('не прогноз CEFR',r['note'])
 def test_other_owner_cannot_shorten_session(self):
  s=self.start()
  with self.assertRaisesRegex(ValueError,'session_not_found'):day.update(self.owner+1,{'session_id':s['id'],'version':s['version'],'action':'shorten','minutes':5})
 def test_api_auth_and_family_aliases(self):
  from web_backend.self_study_api import ROOT,GET_PATHS,POST_PATHS
  self.assertIn(ROOT.replace('/teacher/','/parent/')+'/comfort',GET_PATHS);self.assertIn(ROOT.replace('/teacher/','/student/')+'/comfort/save',POST_PATHS)
  self.assertEqual(401,f.FakeHandler(teacher=None).self_study_route(ROOT+'/comfort')[0]);self.assertEqual(403,f.FakeHandler(origin=False).self_study_route(ROOT+'/comfort/save',write=True)[0]);self.assertEqual(200,f.FakeHandler().self_study_route(ROOT+'/comfort',{'language':['en']})[0])

if __name__=='__main__':unittest.main()
