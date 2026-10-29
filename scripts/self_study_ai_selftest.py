import unittest,tempfile,json,os,sys
from pathlib import Path
from types import ModuleType,SimpleNamespace
from unittest.mock import patch
import self_study_selftest as fixture
import configure_self_study_ai as setup
from web_backend import self_study_ai as ai

class Tests(unittest.TestCase):
 def provider(self):return {'api_key':'test-secret-never-print','base_url':'https://openrouter.ai/api/v1','model':'existing-model'}
 def test_missing_private_config_uses_existing_provider(self):
  with tempfile.TemporaryDirectory() as tmp:
   package=ModuleType('ai_assistant');package.providers=SimpleNamespace(active_provider=lambda:{'id':'existing'})
   with patch.object(ai,'CONFIG_PATH',Path(tmp)/'missing'),patch.dict(sys.modules,{'ai_assistant':package}):self.assertEqual({'id':'existing'},ai.active_provider())
 def test_private_config_does_not_change_environment_or_global_settings(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'ai.json';path.write_text(json.dumps(self.provider()));before=dict(os.environ)
   with patch.object(ai,'CONFIG_PATH',path):self.assertEqual('existing-model',ai.active_provider()['model'])
   self.assertEqual(before,dict(os.environ))
 def test_tutor_uses_private_key_when_global_provider_is_absent(self):
  from web_backend import self_study_tutor as tutor,self_study_feedback as limits
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'ai.json';path.write_text(json.dumps(self.provider()))
   calls=[]
   def request(provider,*args,**kwargs):
    calls.append(provider['model']);return json.dumps({'reply':'When can you meet?','corrections':[],'retry_frame':'On Friday.'})
   package=ModuleType('ai_assistant');package.providers=SimpleNamespace(active_provider=lambda:None,request_chat=request)
   with patch.object(ai,'CONFIG_PATH',path),patch.dict(sys.modules,{'ai_assistant':package}):
    self.assertTrue(tutor.provider_ready());self.assertEqual('When can you meet?',tutor.generate(999,{'language':'en'})['reply']);self.assertEqual(['existing-model'],calls)
   with limits._lock:limits._recent.pop(999,None)
 def test_bad_config_and_url_not_accepted(self):
  for data in ({},{**self.provider(),'api_key':''},{**self.provider(),'base_url':'http://example.test'},{**self.provider(),'base_url':'https://user:password@example.test'}):
   with self.assertRaises(ValueError):ai.validate(data)
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'ai.json';path.write_text('{bad')
   with patch.object(ai,'CONFIG_PATH',path):self.assertIsNone(ai.active_provider())
 def processes(self,tmp,uid=0,gid=0):
  root=Path(tmp);bot=root/'bot';web=root/'web';bot.mkdir();web.mkdir()
  (bot/'environ').write_bytes(b'OPENROUTER_API_KEY=test-secret-never-print\0AI_MODEL=existing-model\0BOT_TOKEN=unrelated-secret\0')
  (web/'status').write_text('Uid:\t{0}\t{0}\t{0}\t{0}\nGid:\t{1}\t{1}\t{1}\t{1}\n'.format(uid,gid))
  return bot,web,root/'config/ai.json'
 def test_check_has_no_writes_or_secrets(self):
  with tempfile.TemporaryDirectory() as tmp:
   bot,web,target=self.processes(tmp);r=setup.configure(bot,web,target)
   self.assertEqual('check',r['status']);self.assertFalse(target.parent.exists());self.assertNotIn('test-secret',json.dumps(r));self.assertNotIn('unrelated',json.dumps(r))
 def test_apply_copies_only_ai_and_is_idempotent(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(setup.os,'chown'),patch.object(setup.os,'fchown'):
   bot,web,target=self.processes(tmp);r=setup.configure(bot,web,target,True);self.assertEqual('configured',r['status']);saved=json.loads(target.read_text());self.assertEqual('existing-model',saved['model']);self.assertNotIn('BOT_TOKEN',saved);self.assertEqual(0o600,target.stat().st_mode&0o777)
   self.assertEqual('already_configured',setup.configure(bot,web,target,True)['status']);self.assertNotIn('test-secret',json.dumps(r))
 def test_group_read_for_nonroot_web_service(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(setup.os,'chown'),patch.object(setup.os,'fchown'):
   bot,web,target=self.processes(tmp,123,456);setup.configure(bot,web,target,True);self.assertEqual(0o640,target.stat().st_mode&0o777);self.assertEqual(0o750,target.parent.stat().st_mode&0o777)
 def test_refuses_existing_different_config(self):
  with tempfile.TemporaryDirectory() as tmp:
   bot,web,target=self.processes(tmp);target.parent.mkdir();different={**self.provider(),'model':'another-model'};target.write_text(json.dumps(different))
   with self.assertRaises(RuntimeError):setup.configure(bot,web,target,True)
   self.assertEqual(different,json.loads(target.read_text()))

if __name__=='__main__':unittest.main()
