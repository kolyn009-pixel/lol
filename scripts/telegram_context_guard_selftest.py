import ast,asyncio,importlib.util,json,unittest
from pathlib import Path
from types import SimpleNamespace as NS
ROOT=Path(__file__).resolve().parents[1]
class Stop(Exception):pass

def function(path,name,env):
    tree=ast.parse((ROOT/path).read_text());node=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name==name)
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
    exec(compile(ast.fix_missing_locations(module),str(path),'exec'),env)
    return env[name]

class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_board_ignores_missing_user_and_no_state_but_handles_active(self):
        received=[]
        async def receive(update,context):received.append(context.user_data['admin_board_user_id'])
        f=function('handlers/board_admin.py','guarded_receive',{'STATE_KEY':'admin_board_user_id','receive':receive,'ApplicationHandlerStop':Stop})
        for user,data in [(None,None),(NS(id=1),None),(None,{'admin_board_user_id':7}),(NS(id=1),{})]:
            await f(NS(effective_user=user),NS(user_data=data))
        self.assertEqual(received,[])
        with self.assertRaises(Stop):await f(NS(effective_user=NS(id=1)),NS(user_data={'admin_board_user_id':7}))
        self.assertEqual(received,[7])

    async def test_payment_ignores_channel_and_stale_state_preserves_validation(self):
        replies=[]
        async def reply(text,**kwargs):replies.append(text)
        env={'ApplicationHandlerStop':Stop,'admin_roles':NS(is_admin_id=lambda uid:uid==1)}
        f=function('handlers/pricing_ux_patch.py','_manual_paid_count_text',env)
        msg=NS(text='abc',reply_text=reply)
        for user,data,message in [(None,None,msg),(NS(id=1),None,msg),(None,{'manual_paid_wait_count':{'user_id':7}},msg),(NS(id=1),{},msg),(NS(id=1),{'manual_paid_wait_count':{'user_id':7}},None),(NS(id=2),{'manual_paid_wait_count':{'user_id':7}},msg)]:
            await f(NS(effective_user=user,message=message),NS(user_data=data))
        self.assertEqual(replies,[])
        with self.assertRaises(Stop):await f(NS(effective_user=NS(id=1),message=msg),NS(user_data={'manual_paid_wait_count':{'user_id':7}}))
        self.assertIn('числом',replies[0])

class PatchTests(unittest.TestCase):
    def test_idempotent_and_preserves_unrelated_edits(self):
        spec=importlib.util.spec_from_file_location('guard_installer',ROOT/'scripts/install_telegram_context_guard.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        for name,hunks in json.loads((ROOT/'scripts/telegram_context_guard_hunks.json').read_text()).items():
            new=(ROOT/name).read_text();self.assertEqual(mod.patched(new,hunks),new)
            old=new
            for h in hunks:old=old.replace(h['new'],h['old'])
            self.assertEqual(mod.patched('# local customization\n'+old,hunks),'# local customization\n'+new)
            with self.assertRaises(RuntimeError):mod.patched('unexpected source',hunks)
if __name__=='__main__':unittest.main()
