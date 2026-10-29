"""Own-account workshop journeys on disposable SQLite; no real provider or messages."""
import unittest,json,time,sys
from types import ModuleType,SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
import self_study_selftest as f
from web_backend import self_study_support as support,self_study_tutor as tutor,self_study_series as series,self_study_weekly as weekly,self_study_listening as listening,self_study_scenes as scenes,self_study_practice as practice
from learning.listening_program import SOURCES,source
from datetime import datetime,timezone,timedelta

class Tests(unittest.TestCase):
 def setUp(self):
  f.study.ensure_schema()
  for m in (support,tutor,series,listening,scenes):m.ensure_schema()
  conn=f.connect()
  for table in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'personal_study_%'")]:conn.execute('DELETE FROM '+table)
  conn.commit();conn.close()
 def test_support_does_not_expose_key_or_change_module(self):
  d=support.material(101,'en-01','d0');self.assertNotIn('answer',d['drill']);self.assertFalse(d['generic']);self.assertIn('used to',d['drill']['options'])
  rid=str(uuid4());body={'lesson_id':'en-01','check_id':'d0','answer':'used to','request_id':rid}
  self.assertTrue(support.submit(101,body)['correct']);self.assertEqual(support.submit(101,body),support.submit(101,body));self.assertEqual([],f.study.overview(101)['history'])
  with self.assertRaises(ValueError):support.submit(101,{**body,'answer':'is used to'})
 def test_support_all_languages_and_generic_honesty(self):
  for lid in ('en-01','de-01','fa-01'):
   d=support.material(101,lid);self.assertTrue(d['generic']);self.assertTrue(d['help']['frames']);self.assertNotIn('answer',d['drill'])
  with self.assertRaises(ValueError):support.material(101,'es-01')
 def test_repair_prioritises_frequent_errors_and_no_automatic_resolve(self):
  body=f.correct_body('en-01');body['answers']['d0']='wrong';body['answers']['d1']='wrong';f.study.submit(101,body)
  practice.sync_lessons(101)
  conn=f.connect();conn.execute("UPDATE personal_study_errors SET wrong_count=4 WHERE check_id='d1'");conn.commit();conn.close()
  self.assertEqual('d1',support.repair(101,'en')['errors'][0]['check_id'])
  cards=practice.practice(101,'en')['items'];conn=f.connect()
  try:self.assertEqual('d1',conn.execute('SELECT source_key FROM personal_study_cards WHERE id=?',(cards[0]['id'],)).fetchone()[0])
  finally:conn.close()
 def start_tutor(self,owner=101):return tutor.start(owner,{'scenario_id':'en-meeting','request_id':str(uuid4())})
 def send(self,s,owner=101,**extra):
  data={'session_id':s['id'],'version':s['version'],'text':'Could we meet on Friday?','consent':True,'request_id':str(uuid4()),**extra}
  return data
 def test_tutor_private_idempotent_and_versioned(self):
  s=self.start_tutor();body=self.send(s);response={'reply':'Yes. What time works for you?','corrections':[],'retry_frame':'How about six?'}
  with patch.object(tutor,'generate',return_value=response) as ai:
   result=tutor.answer(101,body);again=tutor.answer(101,body);self.assertEqual(result,again);ai.assert_called_once();self.assertEqual(2,result['version'])
   with self.assertRaisesRegex(ValueError,'tutor_changed'):tutor.answer(101,{**body,'request_id':str(uuid4())})
   with self.assertRaisesRegex(ValueError,'request_conflict'):tutor.answer(101,{**body,'text':'Different text'})
  with self.assertRaisesRegex(ValueError,'tutor_not_found'):tutor.get(202,s['id'])
 def test_tutor_consent_required_before_provider(self):
  s=self.start_tutor()
  with patch.object(tutor,'generate') as ai:
   with self.assertRaises(ValueError):tutor.answer(101,self.send(s,consent=False))
   ai.assert_not_called()
 def test_tutor_failure_preserves_version_and_releases_pending(self):
  s=self.start_tutor();body=self.send(s)
  with patch.object(tutor,'generate',side_effect=RuntimeError('ai_not_configured')):
   with self.assertRaisesRegex(RuntimeError,'ai_not_configured'):tutor.answer(101,body)
  saved=tutor.get(101,s['id']);self.assertEqual(1,saved['version']);self.assertFalse(saved['pending']);self.assertEqual([],saved['turns'])
  with patch.object(tutor,'generate',return_value={'reply':'Friday is fine.','corrections':[],'retry_frame':'At six.'}):self.assertEqual(2,tutor.answer(101,body)['version'])
 def test_tutor_concurrent_request_does_not_duplicate_provider(self):
  s=self.start_tutor();first=self.send(s);second=self.send(s)
  def call(owner,context):
   with self.assertRaisesRegex(RuntimeError,'feedback_rate_limited'):tutor.answer(owner,second)
   return {'reply':'What time?','corrections':[],'retry_frame':'At six.'}
  with patch.object(tutor,'generate',side_effect=call) as ai:tutor.answer(101,first);ai.assert_called_once()
 def test_provider_json_validation_and_limiter_release(self):
  provider=SimpleNamespace(active_provider=lambda:'configured',request_chat=lambda *a,**k:json.dumps({'reply':'When can you meet?','corrections':[],'retry_frame':'I can meet…'}))
  package=ModuleType('ai_assistant');package.providers=provider
  from web_backend import self_study_feedback as limits
  with limits._lock:limits._recent.clear();limits._active.clear()
  with patch.dict(sys.modules,{'ai_assistant':package}):
   self.assertEqual('When can you meet?',tutor.generate(101,{'language':'en'})['reply'])
   provider.request_chat=lambda *a,**k:'{"reply":"Missing required fields"}'
   with self.assertRaisesRegex(RuntimeError,'ai_invalid_response'):tutor.generate(101,{'language':'en'})
   self.assertNotIn(101,limits._active)
  with limits._lock:limits._recent.clear()
 def test_tutor_cap_and_retry_history(self):
  s=self.start_tutor()
  with patch.object(tutor,'generate',return_value={'reply':'Why?','corrections':['Try a shorter sentence.'],'retry_frame':'Because…'}):
   for i in range(8):s=tutor.answer(101,self.send(s,mode='retry' if i==1 else 'continue'))
   self.assertTrue(s['finished']);self.assertEqual('retry',s['turns'][1]['mode'])
   with self.assertRaisesRegex(ValueError,'conversation_finished'):tutor.answer(101,self.send(s))
 def test_tutor_feedback_context_rejects_future_and_foreign(self):
  from web_backend.self_study_feedback import context_for
  s=self.start_tutor();self.assertEqual('en',context_for('tutor:'+str(s['id'])+':1',101)[0])
  with self.assertRaises(ValueError):context_for('tutor:'+str(s['id'])+':2',101)
  with self.assertRaises(ValueError):context_for('tutor:'+str(s['id'])+':1',202)
 def test_author_audio_bank_and_answers(self):
  studio=[(k,v) for k,v in SOURCES.items() if v.get('delivery')=='browser_tts'];self.assertEqual(16,len(studio));self.assertEqual({'en','de','es','fa'},{v['language'] for _,v in studio})
  for k,m in studio:
   self.assertTrue(m['speech_text']);self.assertTrue(all(q['answer'] in q['options'] for q in m['checks']));self.assertTrue(all('answer' not in q for q in source(k)['checks']))
 def test_studio_first_second_and_retry(self):
  s=listening.start(101,{'source_id':'studio-en-a1','request_id':str(uuid4())});m=SOURCES[s['source_id']];body={'session_id':s['id'],'phase':'first','heard':True,'answers':{q['id']:q['answer'] for q in m['checks']}}
  r=listening.submit(101,body);self.assertEqual(2,r['first']['correct']);self.assertIn('saved_at',r['first']);self.assertEqual(r,listening.submit(101,body));self.assertIsNone(r['second'])
 def make_scene(self,owner=101):return scenes.save_scene(owner,{'resource_id':'landman','season':1,'episode':1,'start_seconds':0,'end_seconds':60,'summary':'A conversation.','comprehension':'gist','phrases':[{'expression':'at stake','meaning':'на кону'}],'request_id':str(uuid4())})['scene']
 def test_series_plan_saved_steps_and_scene_required(self):
  body={'resource_id':'landman','minutes':10,'request_id':str(uuid4())};p=series.start(101,body);self.assertEqual(p,series.start(101,body));self.assertEqual(10,sum(s['minutes'] for s in p['steps']))
  for _ in range(3):p=series.advance(101,{'plan_id':p['id'],'version':p['version']})
  with self.assertRaisesRegex(ValueError,'series_scene_required'):series.advance(101,{'plan_id':p['id'],'version':p['version']})
  foreign=self.make_scene(202)
  with self.assertRaises(ValueError):series.advance(101,{'plan_id':p['id'],'version':p['version'],'scene_id':foreign['id']})
  own=self.make_scene();p=series.advance(101,{'plan_id':p['id'],'version':p['version'],'scene_id':own['id']});self.assertEqual(4,p['step'])
  p=series.advance(101,{'plan_id':p['id'],'version':p['version'],'retold':True});self.assertTrue(p['finished']);self.assertEqual(p,series.current(101,'en')['plan'])
 def test_series_stale_and_active_protection(self):
  body={'resource_id':'landman','minutes':5,'request_id':str(uuid4())};p=series.start(101,body);self.assertTrue(all(s['minutes']>=1 for s in p['steps']))
  with self.assertRaisesRegex(ValueError,'series_plan_active'):series.start(101,{**body,'request_id':str(uuid4())})
  series.advance(101,{'plan_id':p['id'],'version':p['version']})
  with self.assertRaisesRegex(ValueError,'series_plan_changed'):series.advance(101,{'plan_id':p['id'],'version':p['version']})
  with self.assertRaises(ValueError):series.advance(202,{'plan_id':p['id'],'version':2})
 def test_weekly_counts_first_and_repeat_without_fake_growth(self):
  f.study.submit(101,f.correct_body());body=f.correct_body();f.study.submit(101,body)
  r=weekly.report(101,'en');self.assertEqual(1,r['first_modules']);self.assertEqual(1,r['repeat_modules']);self.assertEqual(0,r['tutor_turns']);self.assertEqual(0,weekly.report(202,'en')['first_modules'])
 def test_weekly_does_not_relabel_old_material_as_new(self):
  f.study.submit(101,f.correct_body())
  old=(datetime.now(timezone.utc)-timedelta(days=20)).isoformat()
  conn=f.connect();conn.execute('UPDATE personal_study_attempts SET created_at=?',(old,));conn.commit();conn.close()
  f.study.submit(101,f.correct_body())
  r=weekly.report(101,'en');self.assertEqual(0,r['first_modules']);self.assertEqual(1,r['repeat_modules'])
 def test_series_all_time_presets_have_positive_exact_steps(self):
  for n in (5,10,15,20,30):
   row={'id':1,'owner_id':101,'request_id':str(uuid4()),'minutes':n,'step':0}
   result=series.payload(row);self.assertEqual(n,sum(x['minutes'] for x in result['steps']));self.assertTrue(all(x['minutes']>=1 for x in result['steps']))
 def test_weekly_separates_synthesis_familiar_and_human(self):
  for key in ('studio-en-a1','studio-en-a1','bc-table'):
   s=listening.start(101,{'source_id':key,'request_id':str(uuid4())});listening.submit(101,{'session_id':s['id'],'phase':'first','heard':True,'answers':{q['id']:q['answer'] for q in SOURCES[key]['checks']}})
  rows=weekly.report(101,'en')['listening'];self.assertEqual(['browser_tts','browser_tts','publisher'],[r['delivery'] for r in rows]);self.assertEqual([False,True,False],[r['familiar'] for r in rows])

if __name__=='__main__':unittest.main()
