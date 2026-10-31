import importlib.util,sqlite3,sys,tempfile,types,unittest,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 sp=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
class DeliveryTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'test.db';self.old={k:sys.modules.get(k) for k in ['database','web_backend','web_backend.reliable_channel_send','vk_adapter','vk_adapter.channel_delivery']}
  def connect():c=sqlite3.connect(self.db,timeout=5);c.row_factory=sqlite3.Row;return c
  self.connect=connect;db=types.ModuleType('database');db.connect=connect;db.now_iso=lambda:'2026-10-31T12:00:00';sys.modules['database']=db
  web=types.ModuleType('web_backend');p=load('provider','web_backend/reliable_channel_send.py');web.reliable_channel_send=p;sys.modules['web_backend']=web
  vk=types.ModuleType('vk_adapter');ident=types.SimpleNamespace(telegram_chat=lambda uid:100+uid,vk_peer=lambda uid:200+uid);vk.channel_delivery=ident;sys.modules['vk_adapter']=vk
  self.provider=p;self.ident=ident;self.m=load('delivery','web_backend/homework_channel_delivery.py');self.calls=[]
 def tearDown(self):
  for k,v in self.old.items():
   if v is None:sys.modules.pop(k,None)
   else:sys.modules[k]=v
  self.tmp.cleanup()
 def test_partial_retry_is_durable_and_skips_sent(self):
  def send(ch,rid,text,eid):
   self.calls.append((ch,rid,eid))
   if ch=='VK' and sum(x[0]=='VK' for x in self.calls)==1:raise self.provider.Retryable('rate_limit')
   return '123'
  self.provider.send=send;self.assertFalse(self.m.deliver({'id':7},'text',[1])[0]);self.m=load('delivery_restart','web_backend/homework_channel_delivery.py');self.assertTrue(self.m.deliver({'id':7},'text',[1])[0]);self.assertEqual([x[0] for x in self.calls],['TELEGRAM','VK','VK']);self.assertTrue(self.m.deliver({'id':7},'text',[1])[0]);self.assertEqual(len(self.calls),3)
 def test_uncertain_is_not_retried(self):
  def send(*a):self.calls.append(a);raise self.provider.Uncertain('timeout')
  self.provider.send=send;self.assertFalse(self.m.deliver({'id':7},'text',[1])[0]);self.assertFalse(self.m.deliver({'id':7},'text',[1])[0]);self.assertEqual(len(self.calls),2)
 def test_snapshot_does_not_redirect_to_new_recipient(self):
  def send(*a):self.calls.append(a);raise self.provider.Retryable('rate_limit')
  self.provider.send=send;self.m.deliver({'id':7},'text',[1]);self.ident.vk_peer=lambda uid:999;self.m.deliver({'id':7},'text',[1]);self.assertNotIn(999,[x[1] for x in self.calls]);c=self.connect();self.assertEqual(c.execute("SELECT status FROM homework_delivery_targets WHERE channel='VK'").fetchone()[0],'SKIPPED');c.close()
 def test_teacher_requires_all_recipients(self):
  def send(ch,rid,*a):
   if rid==202:raise self.provider.Permanent('blocked')
   return 'ok'
  self.provider.send=send;self.assertFalse(self.m.deliver({'id':7},'text',[1,2])[0])
 def test_stale_claim_is_ambiguous(self):
  self.m.schema();c=self.connect();c.executescript("INSERT INTO homework_delivery_batches VALUES(7,'now');INSERT INTO homework_delivery_targets(item_id,user_id,channel,recipient_id,status,claimed_at,updated_at) VALUES(7,1,'VK',201,'CLAIMED',0,'now');");c.commit();c.close();self.provider.send=lambda *a:self.fail('stale send repeated');self.assertFalse(self.m.deliver({'id':7},'text',[1])[0]);c=self.connect();self.assertEqual(c.execute('SELECT status FROM homework_delivery_targets').fetchone()[0],'UNKNOWN');c.close()
 def test_worker_does_not_mark_partial_as_delivered(self):
  import ast
  source=ast.parse((ROOT/'web_backend/homework_delivery_worker.py').read_text());fn=next(x for x in source.body if isinstance(x,ast.FunctionDef) and x.name=='deliver');sys.modules['web_backend.homework_channel_delivery']=self.m
  self.provider.send=lambda *a:(_ for _ in ()).throw(self.provider.Retryable('retry'))
  env={'_with_action':lambda x:'text','_teacher_ids':lambda:[1,2]};exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual-worker','exec'),env);self.assertFalse(env['deliver']({'id':7,'recipient_type':'STUDENT','user_id':1})[0])
if __name__=='__main__':unittest.main()
