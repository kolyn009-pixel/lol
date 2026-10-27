import unittest
from datetime import date,timedelta
from unittest.mock import patch
from uuid import uuid4
import self_study_selftest as f
from web_backend import self_study_pilot as pilot

class Tests(unittest.TestCase):
 def setUp(self):
  self.owner=int(uuid4().hex[:7],16)+1000;self.day=date(2026,10,27);p=patch.object(pilot,'today',return_value=self.day);p.start();self.addCleanup(p.stop)
 def body(self,day=1,version=0):return {'day':day,'version':version,'ease':4,'effort':2,'minutes':10,'note':'Хочу короче объяснения.'}
 def test_start_keeps_original_date(self):
  a=pilot.start(self.owner)
  with patch.object(pilot,'today',return_value=self.day+timedelta(days=2)):b=pilot.start(self.owner)
  self.assertEqual(a['started_on'],b['started_on']);self.assertEqual(3,b['current_day'])
 def test_future_day_cannot_be_filled(self):
  pilot.start(self.owner)
  with self.assertRaisesRegex(ValueError,'pilot_day_unavailable'):pilot.save(self.owner,self.body(2))
 def test_real_days_unlock_and_period_finishes(self):
  pilot.start(self.owner)
  with patch.object(pilot,'today',return_value=self.day+timedelta(days=7)):
   self.assertTrue(pilot.status(self.owner)['finished_period']);self.assertTrue(all(x['available'] for x in pilot.status(self.owner)['days']))
 def test_own_feedback_private(self):
  pilot.start(self.owner);pilot.save(self.owner,self.body());self.assertEqual([],pilot.status(self.owner+1)['feedback'])
 def test_no_start_no_feedback(self):
  with self.assertRaises(ValueError):pilot.save(self.owner,self.body())
 def test_retry_does_not_duplicate(self):
  pilot.start(self.owner);a=pilot.save(self.owner,self.body());b=pilot.save(self.owner,self.body());self.assertEqual(a,b);self.assertEqual(1,len(b['feedback']))
 def test_stale_edit_rejected_but_versioned_edit_works(self):
  pilot.start(self.owner);pilot.save(self.owner,self.body());b=self.body();b['note']='Changed'
  with self.assertRaisesRegex(ValueError,'pilot_changed'):pilot.save(self.owner,b)
  b['version']=1;self.assertEqual(2,pilot.save(self.owner,b)['feedback'][0]['version'])
 def test_rest_day_zero_minutes_valid_no_language_grade(self):
  pilot.start(self.owner);b=self.body();b['minutes']=0;r=pilot.save(self.owner,b);self.assertEqual(0,r['feedback'][0]['minutes']);self.assertNotIn('cefr',r);self.assertEqual([],f.study.overview(self.owner)['history'])
 def test_bad_values_rejected(self):
  pilot.start(self.owner)
  for k,v in [('ease',True),('effort',6),('minutes',-1),('note','x'*1001)]:
   b=self.body();b[k]=v
   with self.assertRaises(ValueError):pilot.save(self.owner,b)
 def test_auth_origin_and_role_aliases(self):
  from web_backend.self_study_api import ROOT,GET_PATHS,POST_PATHS
  self.assertIn(ROOT.replace('/teacher/','/parent/')+'/pilot',GET_PATHS);self.assertIn(ROOT.replace('/teacher/','/student/')+'/pilot/feedback',POST_PATHS)
  self.assertEqual(401,f.FakeHandler(teacher=None).self_study_route(ROOT+'/pilot')[0]);self.assertEqual(403,f.FakeHandler(origin=False).self_study_route(ROOT+'/pilot/start',write=True)[0]);self.assertEqual(200,f.FakeHandler().self_study_route(ROOT+'/pilot')[0])
if __name__=='__main__':unittest.main()
