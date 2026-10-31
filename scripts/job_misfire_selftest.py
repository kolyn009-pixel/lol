import ast,importlib.util,json,unittest
from pathlib import Path
from types import SimpleNamespace as NS
ROOT=Path(__file__).resolve().parents[1]
class Queue:
    def __init__(self):self.calls=[]
    def jobs(self):return [NS(name=c[1]['name']) for c in self.calls]
    def run_repeating(self,callback,**kwargs):self.calls.append((callback,kwargs))

def noop(*a,**kw):pass

def register(path,env):
    tree=ast.parse((ROOT/path).read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='register')
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),env);return env['register']

class JobsTests(unittest.TestCase):
    def test_actual_registration(self):
        q=Queue();stub=NS(register=noop,install=noop,regular_series_sync_job=noop)
        env={n:stub for n in ['student_onboarding_runtime','runtime_patch_v2','payment_reminder_routing','review_v2','pricing_ux_patch','lesson_link_bridge','public_trial_notifications']}
        env.update(weekly_dispatcher=noop,homework_watchdog_job=noop)
        register('handlers/musthave_jobs.py',env)(NS(job_queue=q))
        register('handlers/public_trial_notifications.py',{'CallbackQueryHandler':lambda *a,**kw:None,'callback':noop,'dispatch_job':noop})(NS(job_queue=q,add_handler=noop))
        register('crm_plus/jobs.py',{'brief_dispatcher':noop,'timezone_migration_job':noop,'messenger':NS(delivery_job=noop)})(NS(job_queue=q))
        expected={'public_trial_notify':(15,5,30),'adelia_weekly_dispatcher':(60,20,30),'timezone_migration_notifier':(300,20,60)}
        for name,(interval,first,grace) in expected.items():
            k=next(k for _,k in q.calls if k['name']==name)
            self.assertEqual((k['interval'],k['first']),(interval,first));self.assertEqual(k['job_kwargs'],{'misfire_grace_time':grace,'coalesce':True,'max_instances':1})
        # Unrelated jobs retain their original scheduling options.
        self.assertNotIn('job_kwargs',next(k for _,k in q.calls if k['name']=='crm_messenger_delivery'))

    def test_duplicate_public_trial_registration_is_skipped(self):
        q=Queue();f=register('handlers/public_trial_notifications.py',{'CallbackQueryHandler':lambda *a,**kw:None,'callback':noop,'dispatch_job':noop})
        a=NS(job_queue=q,add_handler=noop);f(a);f(a);self.assertEqual(len(q.calls),1)

    def test_reviewed_hunks_preserve_production_customizations(self):
        spec=importlib.util.spec_from_file_location('installer',ROOT/'scripts/install_job_misfire_fix.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        for name,hunks in json.loads((ROOT/'scripts/job_misfire_hunks.json').read_text()).items():
            new=(ROOT/name).read_text();old=new
            for h in hunks:old=old.replace(h['new'],h['old'])
            self.assertEqual(m.patched('# production edits\n'+old,hunks),'# production edits\n'+new)
            self.assertEqual(m.patched(new,hunks),new)
            with self.assertRaises(RuntimeError):m.patched('unreviewed code',hunks)
if __name__=='__main__':unittest.main()
