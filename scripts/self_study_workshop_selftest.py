"""Pass 1: scaffold help and original synthesized listening. Disposable SQLite."""
import unittest
from uuid import uuid4
import self_study_selftest as f
from web_backend import self_study_support as support,self_study_listening as listening
from learning.listening_program import SOURCES,source

class Tests(unittest.TestCase):
 def setUp(self):
  support.ensure_schema();listening.ensure_schema();conn=f.connect()
  for table in [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'personal_study_%'")]:conn.execute('DELETE FROM '+table)
  conn.commit();conn.close()
 def test_help_hides_keys_and_does_not_advance_lesson(self):
  d=support.material(101,'en-01','d0');self.assertNotIn('answer',d['drill']);self.assertFalse(d['generic'])
  body={'lesson_id':'en-01','check_id':'d0','answer':'used to','request_id':str(uuid4())}
  self.assertTrue(support.submit(101,body)['correct']);self.assertEqual([],f.study.overview(101)['history'])
  self.assertEqual(support.submit(101,body),support.submit(101,body))
  with self.assertRaisesRegex(ValueError,'request_conflict'):support.submit(101,{**body,'answer':'is used to'})
 def test_help_works_for_languages_and_labels_generic_drill(self):
  for lid in ('en-01','de-01','fa-01'):
   d=support.material(101,lid);self.assertTrue(d['generic']);self.assertTrue(d['help']['frames']);self.assertNotIn('answer',d['drill'])
  with self.assertRaisesRegex(ValueError,'invalid_language'):support.material(101,'es-01')
 def test_help_rejects_unknown_question_without_writes(self):
  with self.assertRaises(ValueError):support.material(101,'en-01','fake')
  with self.assertRaises(ValueError):support.submit(101,{'lesson_id':'en-01','check_id':'d0','answer':'random','request_id':str(uuid4())})
  self.assertEqual([],f.study.overview(101)['history'])
 def test_synthesis_bank_has_16_original_texts_and_hidden_keys(self):
  rows=[(k,v) for k,v in SOURCES.items() if v.get('delivery')=='browser_tts'];self.assertEqual(16,len(rows));self.assertEqual({'en','de','es','fa'},{v['language'] for _,v in rows})
  for k,v in rows:
   self.assertTrue(v['speech_text']);self.assertTrue(all(q['answer'] in q['options'] for q in v['checks']));self.assertTrue(all('answer' not in q for q in source(k)['checks']))
 def test_synthesis_first_second_and_retry_separate(self):
  s=listening.start(101,{'source_id':'studio-en-a1','request_id':str(uuid4())});m=SOURCES[s['source_id']];body={'session_id':s['id'],'phase':'first','heard':True,'answers':{q['id']:q['answer'] for q in m['checks']}}
  r=listening.submit(101,body);self.assertEqual(2,r['first']['correct']);self.assertIn('saved_at',r['first']);self.assertEqual(r,listening.submit(101,body));self.assertIsNone(r['second'])
  r=listening.submit(101,{**body,'phase':'second'});self.assertEqual(2,r['second']['correct'])
 def test_synthesis_session_private_and_second_requires_first(self):
  s=listening.start(101,{'source_id':'studio-en-a1','request_id':str(uuid4())});m=SOURCES[s['source_id']];body={'session_id':s['id'],'phase':'second','heard':True,'answers':{q['id']:q['answer'] for q in m['checks']}}
  with self.assertRaisesRegex(ValueError,'listening_first_required'):listening.submit(101,body)
  with self.assertRaisesRegex(ValueError,'listening_not_found'):listening.submit(202,{**body,'phase':'first'})

if __name__=='__main__':unittest.main()
