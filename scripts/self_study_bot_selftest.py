import unittest,sys,asyncio,tempfile
from pathlib import Path
from types import ModuleType,SimpleNamespace
from unittest.mock import patch,AsyncMock
import self_study_selftest as f
from web_backend import self_study_bot as bot,self_study_access as access
import install_self_study_bot as install

class Tests(unittest.TestCase):
 def setUp(self):
  access.ensure_schema();conn=f.connect();conn.execute('DELETE FROM personal_study_memberships');conn.commit();conn.close()
  self.lookups=patch.multiple(f.database,get_user_by_telegram_id=lambda _:None,get_parent_by_telegram_id=lambda _:None,create=True);self.lookups.start();self.addCleanup(self.lookups.stop)
 def member(self,role,aid=101):
  conn=f.connect();conn.execute('INSERT OR REPLACE INTO personal_study_memberships VALUES(?,?,1,?)',(role+':'+str(aid),101,'2026-10-27'));conn.commit();conn.close()
 def test_unknown_and_nonowner_denied(self):
  self.assertEqual('denied',bot.entry(999)['status']);self.assertEqual([],bot.identities('101'))
 def test_owner_receives_own_url_not_invite_or_other_data(self):
  r=bot.entry(101);self.assertEqual('ready',r['status']);self.assertIn('teacher.html?study=1',r['url']);self.assertNotIn('token',r)
 def test_parent_membership_uses_parent_account(self):
  self.member('parent')
  with patch.object(f.database,'get_parent_by_telegram_id',return_value={'id':101,'active':1}):
   r=bot.entry(777);self.assertEqual('parent',r['role']);self.assertIn('role=parent',r['url']);self.assertIn('стартовые',r['text'])
 def test_both_roles_require_explicit_choice(self):
  self.member('parent');self.member('student')
  with patch.object(f.database,'get_parent_by_telegram_id',return_value={'id':101,'active':1}),patch.object(f.database,'get_user_by_telegram_id',return_value={'id':101,'active':1}):
   r=bot.entry(777);self.assertEqual('choose',r['status']);self.assertEqual({'student','parent'},set(r['roles']));self.assertEqual('parent',bot.entry(777,'parent')['role'])
 def test_inactive_or_revoked_not_allowed(self):
  self.member('parent')
  with patch.object(f.database,'get_parent_by_telegram_id',return_value={'id':101,'active':0}):self.assertEqual('denied',bot.entry(777)['status'])
  conn=f.connect();conn.execute('UPDATE personal_study_memberships SET active=0');conn.commit();conn.close()
  with patch.object(f.database,'get_parent_by_telegram_id',return_value={'id':101,'active':1}):self.assertEqual('denied',bot.entry(777)['status'])
 def test_cannot_select_unowned_role(self):self.assertEqual('denied',bot.entry(101,'parent')['status'])
 def test_bot_patch_idempotent_and_rejects_unknown_layout(self):
  s='def main():\n'+install.ANCHOR+'\n';p=install.patch_bot(s);self.assertEqual(p,install.patch_bot(p));self.assertEqual(1,p.count(install.HOOK))
  with self.assertRaises(RuntimeError):install.patch_bot('def main(): pass')
 def setup_live(self,tmp):
  root=Path(tmp)/'live';(root/'web_backend').mkdir(parents=True);(root/'web_backend/self_study_access.py').write_text('# installed web module');(root/'bot.py').write_text('def main():\n'+install.ANCHOR+'\n');(root/'work.txt').write_text('work unchanged');return root
 def test_bot_install_dry_run_has_no_writes(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=self.setup_live(tmp);before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()};install.install(root,'test.service');self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
 def test_bot_install_backups_idempotence_and_code_rollback(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(install,'restart'):
   root=self.setup_live(tmp);old=(root/'bot.py').read_bytes();backup=install.install(root,'test.service',True);self.assertIsNotNone(backup);self.assertIsNone(install.install(root,'test.service',True));install.restore(root,backup);self.assertEqual(old,(root/'bot.py').read_bytes());self.assertEqual('work unchanged',(root/'work.txt').read_text())
 def test_bot_install_restart_failure_rolls_back(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(install,'restart',side_effect=[RuntimeError('failed'),None]):
   root=self.setup_live(tmp);old=(root/'bot.py').read_bytes()
   with self.assertRaises(RuntimeError):install.install(root,'test.service',True)
   self.assertEqual(old,(root/'bot.py').read_bytes());self.assertFalse((root/'handlers/self_study_family.py').exists())
 def test_bot_install_conflicting_module_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=self.setup_live(tmp);(root/'web_backend/self_study_bot.py').write_text('external edits')
   with self.assertRaises(RuntimeError):install.install(root,'test.service',True)
 def test_handler_private_only_no_live_messages(self):
  tg=ModuleType('telegram');ext=ModuleType('telegram.ext')
  class Stop(Exception):pass
  class H:
   def __init__(self,*args,**kwargs):self.args=args;self.kwargs=kwargs
  tg.Update=H;tg.BotCommand=H;tg.BotCommandScopeChat=H;tg.BotCommandScopeAllPrivateChats=H;tg.BotCommandScopeDefault=H;ext.TypeHandler=H;tg.InlineKeyboardButton=H;tg.InlineKeyboardMarkup=H;ext.CommandHandler=H;ext.CallbackQueryHandler=H;ext.ApplicationHandlerStop=Stop
  with patch.dict(sys.modules,{'telegram':tg,'telegram.ext':ext}):
   import importlib.util
   spec=importlib.util.spec_from_file_location('family_test',f.ROOT/'handlers/self_study_family.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   message=SimpleNamespace(reply_text=AsyncMock(),text='/languages');update=SimpleNamespace(effective_chat=SimpleNamespace(type='group'),effective_user=SimpleNamespace(id=101),effective_message=message,callback_query=None)
   with self.assertRaises(Stop):asyncio.run(m.language_entry(update,SimpleNamespace(args=[])))
   message.reply_text.assert_not_awaited()
   update.effective_chat.type='private'
   with self.assertRaises(Stop):asyncio.run(m.language_entry(update,SimpleNamespace(args=[])))
   message.reply_text.assert_awaited_once()
   app=SimpleNamespace(bot_data={},add_handler=lambda *a,**k:calls.append((a,k)));calls=[];m.install(app);m.install(app);self.assertEqual(3,len(calls))
 def menu_fixture(self):
  import importlib.util
  tg=ModuleType('telegram');ext=ModuleType('telegram.ext')
  class Item:
   def __init__(self,command=None,description=None):self.command=command;self.description=description
  for key in ('Update','BotCommand','BotCommandScopeChat','BotCommandScopeAllPrivateChats','BotCommandScopeDefault','InlineKeyboardButton','InlineKeyboardMarkup'):setattr(tg,key,Item)
  for key in ('CommandHandler','CallbackQueryHandler','ApplicationHandlerStop','TypeHandler'):setattr(ext,key,Item)
  with patch.dict(sys.modules,{'telegram':tg,'telegram.ext':ext}):
   spec=importlib.util.spec_from_file_location('family_menu_test',f.ROOT/'handlers/self_study_family.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  update=SimpleNamespace(effective_chat=SimpleNamespace(type='private',id=777),effective_user=SimpleNamespace(id=777,language_code='ru'))
  context=SimpleNamespace(bot=SimpleNamespace(get_my_commands=AsyncMock(),set_my_commands=AsyncMock(),delete_my_commands=AsyncMock()),chat_data={})
  return m,update,context,Item
 def test_menu_adds_to_effective_commands_for_member_only(self):
  m,u,c,Item=self.menu_fixture();start=Item('start','Начать');c.bot.get_my_commands.side_effect=[[],[],[],[],[start]]
  with patch.object(m,'identities',return_value=[{'role':'parent'}]):asyncio.run(m.sync_language_menu(u,c))
  args=c.bot.set_my_commands.call_args;self.assertEqual(['start','languages'],[x.command for x in args.args[0]]);self.assertEqual(777,args.kwargs['scope'].command);self.assertEqual('ru',args.kwargs['language_code'])
 def test_menu_nonmember_no_change_and_group_no_queries(self):
  m,u,c,_=self.menu_fixture();c.bot.get_my_commands.return_value=[]
  with patch.object(m,'identities',return_value=[]):asyncio.run(m.sync_language_menu(u,c))
  c.bot.set_my_commands.assert_not_awaited();c.bot.delete_my_commands.assert_not_awaited();c.bot.get_my_commands.reset_mock();u.effective_chat.type='group';asyncio.run(m.sync_language_menu(u,c));c.bot.get_my_commands.assert_not_awaited()
 def test_menu_revoke_removes_only_managed_entry(self):
  m,u,c,Item=self.menu_fixture();c.bot.get_my_commands.return_value=[Item('start','Start'),Item('languages',m.MENU_DESCRIPTION)]
  with patch.object(m,'identities',return_value=[]):asyncio.run(m.sync_language_menu(u,c))
  self.assertEqual(['start'],[x.command for x in c.bot.set_my_commands.call_args.args[0]])
 def test_menu_failure_does_not_interrupt_work(self):
  m,u,c,_=self.menu_fixture();c.bot.get_my_commands.side_effect=RuntimeError('offline')
  with patch.object(m,'identities',return_value=[{}]):asyncio.run(m.sync_language_menu(u,c))
  c.bot.set_my_commands.assert_not_awaited()
 def test_menu_deduplicates_and_throttles(self):
  m,u,c,Item=self.menu_fixture();c.bot.get_my_commands.return_value=[Item('start','Start'),Item('languages',m.MENU_DESCRIPTION)]
  with patch.object(m,'identities',return_value=[{}]):
   asyncio.run(m.sync_language_menu(u,c));asyncio.run(m.sync_language_menu(u,c))
  c.bot.get_my_commands.assert_awaited_once();c.bot.set_my_commands.assert_not_awaited()
 def test_vk_patch_idempotent_and_rejects_unknown_layout(self):
  text='def handle_message(message):\n    return app.work(message)\n';patched=install.patch_vk(text)
  self.assertEqual(patched,install.patch_vk(patched));self.assertIn('return app.work(message)',patched)
  with self.assertRaises(RuntimeError):install.patch_vk('other = 1')
 def test_vk_installer_preserves_ordinary_runtime(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(install,'restart'):
   root=self.setup_live(tmp);(root/'vk_adapter').mkdir();runtime=root/'vk_adapter/runtime.py';old='def handle_message(message):\n    return app.work(message)\n';runtime.write_text(old)
   backup=install.install(root,'vk.service',True,channel='vk');self.assertIn(install.VK_HOOK,runtime.read_text());self.assertEqual('work unchanged',(root/'work.txt').read_text());install.restore(root,backup);self.assertEqual(old,runtime.read_text())
 def test_vk_commands_private_verified_and_no_work_interception(self):
  from unittest.mock import Mock
  import importlib.util
  service=ModuleType('vk_adapter.service');teacher=ModuleType('vk_adapter.teacher_service');service.linked_user=Mock(return_value=None);teacher.is_teacher=Mock(return_value=101)
  package=ModuleType('vk_adapter');package.__path__=[];package.service=service;package.teacher_service=teacher
  with patch.dict(sys.modules,{'vk_adapter':package,'vk_adapter.service':service,'vk_adapter.teacher_service':teacher}):
   spec=importlib.util.spec_from_file_location('vk_adapter.self_study_family',f.ROOT/'vk_adapter/self_study_family.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);app=SimpleNamespace(api=Mock())
   self.assertFalse(module.intercept(app,{'text':'/start','from_id':777,'peer_id':777}));app.api.assert_not_called();service.linked_user.assert_not_called()
   self.assertTrue(module.intercept(app,{'text':'/languages','from_id':777,'peer_id':2000000001}));app.api.assert_not_called()
   self.assertTrue(module.intercept(app,{'text':'/languages','from_id':777,'peer_id':777}));self.assertIn('teacher.html',app.api.call_args.kwargs['message']);self.assertEqual(777,app.api.call_args.kwargs['peer_id'])
 def test_vk_unlinked_identity_cannot_access_language_data(self):
  from unittest.mock import Mock
  import importlib.util
  service=ModuleType('vk_adapter.service');teacher=ModuleType('vk_adapter.teacher_service');service.linked_user=Mock(return_value=None);teacher.is_teacher=Mock(return_value=None);package=ModuleType('vk_adapter');package.__path__=[];package.service=service;package.teacher_service=teacher
  with patch.dict(sys.modules,{'vk_adapter':package,'vk_adapter.service':service,'vk_adapter.teacher_service':teacher}):
   spec=importlib.util.spec_from_file_location('vk_adapter.self_study_family',f.ROOT/'vk_adapter/self_study_family.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);app=SimpleNamespace(api=Mock());module.intercept(app,{'text':'/language_cards','from_id':777,'peer_id':777});self.assertNotIn('https://',app.api.call_args.kwargs['message'])
if __name__=='__main__':unittest.main()
