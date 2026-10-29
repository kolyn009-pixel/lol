import unittest
from uuid import uuid4
import self_study_selftest as f
from learning.route_bridges import DATA,additional
from learning.language_routes import MAP,challenge
from learning.language_program import lesson
from web_backend import self_study_routes as routes,self_study_preferences as prefs,self_study_vocabulary as vocab,self_study_day as day

class Tests(unittest.TestCase):
 def setUp(self):
  self.owner=int(uuid4().hex[:7],16)+10000
  prefs.save(self.owner,{'courses':['es'],'priority':'es','daily_minutes':60,'age_group':'adult','levels':{'es':'A0'},'goals':{},'target_dates':{},'formats':[],'genres':[],'topics':[],'custom_series':[]})
 def activate(self):return routes.activate(self.owner,'es')
 def finish(self,band='A1'):
  for identifier in MAP['es'][band]:f.study.submit(self.owner,f.correct_body(identifier))
 def body(self,band='A1'):
  return {'language':'es','band':band,'request_id':str(uuid4()),'answers':{q['id']:q['answers'][0] for q in challenge('es',band,True)['checks']}}
 def test_all_24_bridges_grade_without_exposing_keys(self):
  items=[item for lang in DATA for item in additional(lang)];self.assertEqual(24,len(items))
  for item in items:
   self.assertTrue(all('answers' not in q for q in lesson(item['id'])['checks']))
   self.assertEqual(4,f.study.submit(self.owner,f.correct_body(item['id']))['correct'])
 def test_all_mapped_lessons_exist_and_are_unique_per_language(self):
  for lang,levels in MAP.items():
   ids=[i for items in levels.values() for i in items];self.assertEqual(len(ids),len(set(ids)))
   for identifier in ids:self.assertEqual(lang,lesson(identifier)['language'])
 def test_all_available_gates_have_valid_private_keys(self):
  for lang,levels in MAP.items():
   for band,items in levels.items():
    if not items:continue
    public=challenge(lang,band);private=challenge(lang,band,True)
    self.assertTrue(all('answers' not in q for q in public['checks']))
    for q in private['checks']:
     if q['kind']=='choice':self.assertIn(q['answers'][0],q['options'])
 def test_activation_is_idempotent_and_does_not_create_scores(self):
  a=self.activate();b=self.activate();self.assertEqual(a,b);self.assertEqual('A1',a['start_band']);self.assertEqual([],f.study.overview(self.owner)['history'])
 def test_locked_gate_cannot_be_submitted_directly(self):
  self.activate()
  with self.assertRaisesRegex(ValueError,'route_check_locked'):routes.submit_check(self.owner,self.body())
 def test_next_stage_requires_both_modules_and_gate(self):
  self.activate();self.finish();a=routes.view(self.owner,'es');self.assertEqual('check',a['next_action']);self.assertEqual('locked',a['stages'][1]['status'])
  r=routes.submit_check(self.owner,self.body());self.assertTrue(r['passed']);b=routes.view(self.owner,'es');self.assertEqual('A2',b['current_band']);self.assertEqual('esb-01',b['next_lesson'])
 def test_retry_uuid_does_not_duplicate_and_different_answers_conflict(self):
  self.activate();self.finish();body=self.body();a=routes.submit_check(self.owner,body);self.assertEqual(a,routes.submit_check(self.owner,body))
  body['answers']['d0']='wrong'
  with self.assertRaisesRegex(ValueError,'request_conflict'):routes.submit_check(self.owner,body)
 def test_repeat_is_labelled_as_familiar_not_independent_growth(self):
  self.activate();self.finish();a=routes.submit_check(self.owner,self.body());b=routes.submit_check(self.owner,self.body());self.assertTrue(a['fresh']);self.assertFalse(b['fresh'])
 def test_failed_gate_keeps_stage_closed(self):
  self.activate();self.finish();b=self.body();b['answers']={k:'wrong' for k in b['answers']};r=routes.submit_check(self.owner,b);self.assertFalse(r['passed']);self.assertEqual('A1',routes.view(self.owner,'es')['current_band'])
 def test_private_progress_does_not_unlock_another_account(self):
  self.activate();self.finish();routes.submit_check(self.owner,self.body());self.assertFalse(routes.view(self.owner+1,'en')['enabled'])
 def test_daily_plan_uses_route_then_sends_to_transition_check(self):
  self.activate();s=day.start(self.owner,{'language':'es','minutes':5})['session'];self.assertEqual('es-01',s['lesson_id'])
  conn=f.connect();conn.execute("UPDATE personal_study_sessions SET status='FINISHED' WHERE id=?",(s['id'],));conn.commit();conn.close();self.finish()
  self.assertEqual('route_check',day.start(self.owner,{'language':'es','minutes':5})['action'])
 def test_vocabulary_does_not_pull_from_locked_advanced_stages(self):
  self.activate();d=vocab.save_goal(self.owner,{'language':'es','target':100,'deadline':'2026-11-01'});d=vocab.start(self.owner,{'language':'es'})
  allowed={f.study.normalise(p['front']) for identifier in MAP['es']['A1'] for p in lesson(identifier)['phrases']}
  self.assertTrue(all(f.study.normalise(c['front']) in allowed for c in d['cards']))
 def test_missing_farsi_upper_material_is_reported_instead_of_unlocked(self):
  prefs.save(self.owner,{'courses':['fa'],'priority':'fa','daily_minutes':60,'age_group':'adult','levels':{'fa':'B2'},'goals':{},'target_dates':{}})
  r=routes.activate(self.owner,'fa');self.assertEqual('materials_needed',r['next_action']);self.assertEqual('missing',r['stages'][3]['coverage'])
 def test_lower_steps_are_review_without_invented_passes(self):
  prefs.save(self.owner,{'courses':['es'],'priority':'es','daily_minutes':60,'age_group':'adult','levels':{'es':'C1'},'goals':{},'target_dates':{}})
  r=self.activate();self.assertEqual('review',r['stages'][0]['status']);self.assertFalse(r['stages'][0]['checked']);self.assertEqual('esb-10',r['next_lesson'])

if __name__=='__main__':unittest.main()
