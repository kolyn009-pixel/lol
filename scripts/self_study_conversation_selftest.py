import unittest
from uuid import uuid4
import self_study_selftest as f
from web_backend import self_study_conversation as talk
from web_backend.self_study_feedback import context_for
from learning.conversation_program import DATA

class Tests(unittest.TestCase):
 def setUp(self):self.owner=int(uuid4().hex[:7],16)+1000
 def start(self,identifier='en-meeting'):return talk.start(self.owner,{'scenario_id':identifier,'request_id':str(uuid4())})
 def body(self,s,intention='agree'):return {'session_id':s['id'],'version':s['version'],'request_id':str(uuid4()),'text':'Could we meet tomorrow?','intention':intention,'reflection':'with_help' if s['turn']==2 else None}
 def test_ten_scenarios_four_languages(self):
  self.assertEqual(10,len(DATA));self.assertEqual({'en','de','es','fa'},{m['language'] for m in DATA.values()})
 def test_full_three_turn_flow_and_resume(self):
  s=self.start()
  for _ in range(3):s=talk.answer(self.owner,self.body(s))
  self.assertTrue(s['finished']);self.assertIsNone(s['prompt']);self.assertEqual(s,talk.get(self.owner,s['id']))
 def test_intention_changes_reply(self):
  a=talk.answer(self.owner,self.body(self.start(),'clarify'));b=talk.answer(self.owner,self.body(self.start(),'alternative'));self.assertNotEqual(a['prompt'],b['prompt'])
 def test_stale_version_does_not_overwrite(self):
  s=self.start();talk.answer(self.owner,self.body(s))
  with self.assertRaisesRegex(ValueError,'conversation_changed'):talk.answer(self.owner,self.body(s))
 def test_answer_retry_idempotent(self):
  s=self.start();b=self.body(s);a=talk.answer(self.owner,b);self.assertEqual(a,talk.answer(self.owner,b))
  b['text']='Changed answer'
  with self.assertRaisesRegex(ValueError,'request_conflict'):talk.answer(self.owner,b)
 def test_start_retry_idempotent(self):
  b={'scenario_id':'en-meeting','request_id':str(uuid4())};self.assertEqual(talk.start(self.owner,b),talk.start(self.owner,b))
 def test_other_account_cannot_read_or_coach(self):
  s=self.start()
  with self.assertRaisesRegex(ValueError,'conversation_not_found'):talk.get(self.owner+1,s['id'])
  with self.assertRaises(ValueError):context_for('conversation:'+str(s['id'])+':0',self.owner+1)
 def test_coaching_uses_current_prompt_and_denies_future_turn(self):
  s=self.start();lang,prompt=context_for('conversation:'+str(s['id'])+':0',self.owner);self.assertEqual('en',lang);self.assertEqual(s['prompt'],prompt)
  with self.assertRaises(ValueError):context_for('conversation:'+str(s['id'])+':2',self.owner)
 def test_invalid_answer_or_intention_does_not_advance(self):
  s=self.start();b=self.body(s);b['intention']='invented'
  with self.assertRaises(ValueError):talk.answer(self.owner,b)
  b['intention']='agree';b['text']=' '
  with self.assertRaises(ValueError):talk.answer(self.owner,b)
  self.assertEqual(0,talk.get(self.owner,s['id'])['turn'])
 def test_final_reflection_required_and_finished_cannot_advance(self):
  s=self.start()
  for _ in range(2):s=talk.answer(self.owner,self.body(s))
  b=self.body(s);b['reflection']=None
  with self.assertRaisesRegex(ValueError,'reflection_required'):talk.answer(self.owner,b)
  s=talk.answer(self.owner,self.body(s))
  with self.assertRaisesRegex(ValueError,'conversation_finished'):talk.answer(self.owner,self.body(s))
 def test_no_lesson_or_cefr_score_created(self):
  s=self.start();talk.answer(self.owner,self.body(s));self.assertEqual([],f.study.overview(self.owner)['history'])
 def test_api_aliases_and_auth(self):
  from web_backend.self_study_api import ROOT,GET_PATHS,POST_PATHS
  self.assertIn(ROOT.replace('/teacher/','/parent/')+'/conversation',GET_PATHS);self.assertIn(ROOT.replace('/teacher/','/student/')+'/conversation/answer',POST_PATHS)
  self.assertEqual(401,f.FakeHandler(teacher=None).self_study_route(ROOT+'/conversation')[0]);self.assertEqual(403,f.FakeHandler(origin=False).self_study_route(ROOT+'/conversation/start',write=True)[0])
  self.assertEqual(200,f.FakeHandler().self_study_route(ROOT+'/conversation',{'language':['en']})[0])

if __name__=='__main__':unittest.main()
