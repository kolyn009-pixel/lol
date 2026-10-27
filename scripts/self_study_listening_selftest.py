import unittest
from uuid import uuid4
import self_study_selftest as f
from web_backend import self_study_listening as listen
from learning.listening_program import source

class Tests(unittest.TestCase):
 def setUp(self):self.owner=int(uuid4().hex[:7],16)+1000
 def start(self):return listen.start(self.owner,{'source_id':'bc-table','request_id':str(uuid4())})
 def body(self,s,phase='first',correct=True):return {'session_id':s['id'],'phase':phase,'heard':True,'answers':{'people':'6' if correct else '4','time':'20:00' if correct else '21:00'}}
 def test_public_material_does_not_reveal_answers_or_review(self):
  m=source('bc-table');self.assertNotIn('review',m);self.assertTrue(all('answer' not in q for q in m['checks']))
 def test_first_and_second_are_separate_and_immutable(self):
  s=self.start();a=listen.submit(self.owner,self.body(s,correct=False));b=listen.submit(self.owner,self.body(s,'second'))
  self.assertEqual(0,b['first']['correct']);self.assertEqual(2,b['second']['correct']);self.assertIn('review',a['material'])
  with self.assertRaisesRegex(ValueError,'request_conflict'):listen.submit(self.owner,self.body(s))
 def test_second_cannot_skip_first(self):
  with self.assertRaisesRegex(ValueError,'listening_first_required'):listen.submit(self.owner,self.body(self.start(),'second'))
 def test_unheard_or_invalid_phase_rejected(self):
  b=self.body(self.start());b['heard']=False
  with self.assertRaises(ValueError):listen.submit(self.owner,b)
  b['heard']=True;b['phase']='other'
  with self.assertRaises(ValueError):listen.submit(self.owner,b)
 def test_first_retry_is_idempotent(self):
  b=self.body(self.start());self.assertEqual(listen.submit(self.owner,b),listen.submit(self.owner,b))
 def test_start_retry_is_idempotent(self):
  b={'source_id':'bc-table','request_id':str(uuid4())};self.assertEqual(listen.start(self.owner,b),listen.start(self.owner,b))
 def test_other_owner_cannot_read_or_update_session(self):
  s=self.start();self.assertEqual([],listen.catalog(self.owner+1,'en')['sessions'])
  with self.assertRaisesRegex(ValueError,'listening_not_found'):listen.submit(self.owner+1,self.body(s))
 def test_incomplete_answers_do_not_reveal_review(self):
  s=self.start();b=self.body(s);b['answers']={}
  with self.assertRaises(ValueError):listen.submit(self.owner,b)
  self.assertNotIn('review',listen.catalog(self.owner,'en')['sessions'][0]['material'])
 def test_guided_mode_never_creates_checked_score(self):
  s=listen.start(self.owner,{'source_id':'dw-nico','request_id':str(uuid4())})
  out=listen.submit(self.owner,{'session_id':s['id'],'phase':'first','heard':True,'note':'Услышал просьбу повторить имя.','reference':'Episode 1, 00:30–01:00'})
  self.assertEqual('self_report',out['first']['type']);self.assertNotIn('correct',out['first'])
 def test_disabled_language_cannot_be_started(self):
  with self.assertRaisesRegex(ValueError,'invalid_language'):listen.start(self.owner,{'source_id':'rtve-ministerio','request_id':str(uuid4())})
 def test_no_cefr_or_lesson_scores_are_created(self):
  s=self.start();listen.submit(self.owner,self.body(s));self.assertEqual([],f.study.overview(self.owner)['history'])
 def test_real_api_requires_auth_and_origin(self):
  from web_backend.self_study_api import ROOT,GET_PATHS,POST_PATHS
  self.assertIn(ROOT.replace('/teacher/','/parent/')+'/listening',GET_PATHS)
  self.assertIn(ROOT.replace('/teacher/','/student/')+'/listening/start',POST_PATHS)
  self.assertEqual(401,f.FakeHandler(teacher=None).self_study_route(ROOT+'/listening')[0])
  self.assertEqual(403,f.FakeHandler(origin=False).self_study_route(ROOT+'/listening/start',write=True)[0])
  self.assertEqual(200,f.FakeHandler().self_study_route(ROOT+'/listening',{'language':['en']})[0])

 def test_b2_science_recording_has_checked_questions_with_hidden_keys(self):
  public=source('bc-experiment');self.assertEqual('checked',public['mode']);self.assertTrue(all('answer' not in q for q in public['checks']))
  private=source('bc-experiment',True);session=listen.start(self.owner,{'source_id':'bc-experiment','request_id':str(uuid4())});result=listen.submit(self.owner,{'session_id':session['id'],'phase':'first','heard':True,'answers':{q['id']:q['answer'] for q in private['checks']}});self.assertEqual(2,result['first']['correct'])
 def test_beginner_german_recording_stays_self_report(self):
  self.assertEqual('guided',source('goethe-a1')['mode']);self.assertNotIn('checks',source('goethe-a1'))
if __name__=='__main__':unittest.main()
