"""Real SQLite group/invitation/onboarding checks; credential hashing and transport isolated."""
from pathlib import Path
import concurrent.futures
import sys
import tempfile
from types import ModuleType
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import database
from web_backend import group_lessons, group_workspace as groups
from web_backend.group_workspace_api import GroupWorkspaceMixin


class Groups(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.old=database.DB_NAME
        database.DB_NAME=str(Path(self.temp.name)/'groups.db')
        c=database.connect(); c.executescript('''
        CREATE TABLE users(id INTEGER PRIMARY KEY,active INTEGER DEFAULT 1,name TEXT,grade INTEGER,
          telegram_id INTEGER,telegram_username TEXT,phone TEXT,study_goal TEXT,main_subject TEXT,
          trial_used INTEGER,created_at TEXT,updated_at TEXT);
        CREATE TABLE regular_schedules(id INTEGER PRIMARY KEY,status TEXT);
        CREATE TABLE student_programs(user_id INTEGER,study_goal TEXT,subject TEXT,is_primary INTEGER,
          active INTEGER,approval_status TEXT,trial_used INTEGER,created_by TEXT,created_at TEXT);
        INSERT INTO users(id,active,name) VALUES(1,1,'Один'),(2,1,'Два'),(3,1,'Три'),(4,0,'Черновик');
        ''');c.commit();c.close()
        self.group=group_lessons.create_group('Физика ЕГЭ','PHYSICS','EGE',1500,max_members=2)
        self.gid=self.group['id']; self.token=groups.invitation(self.gid).split('invite=')[1]

    def tearDown(self):
        database.DB_NAME=self.old;self.temp.cleanup()

    def test_group_exists_without_lessons_and_public_preview_is_private(self):
        p=groups.preview(self.token)
        self.assertEqual(p['group']['name'],'Физика ЕГЭ');self.assertEqual(p['places_left'],2)
        self.assertNotIn('members',p['group']);self.assertNotIn('board_url',p['group'])
        self.assertEqual(groups.settings(self.gid)['group']['slots'],[])

    def test_join_idempotent_and_upcoming_lessons_remain_unpaid(self):
        slot=group_lessons.add_initial_slot(self.gid,0,'18:15',60)
        lesson=group_lessons.generate_lesson(self.gid,slot['slot_id'],'2099-01-05T18:15:00')
        for _ in range(2): self.assertEqual(groups.join(self.token,1)['group_id'],self.gid)
        c=database.connect()
        self.assertEqual(c.execute('SELECT COUNT(*) FROM group_members').fetchone()[0],1)
        p=c.execute('SELECT * FROM group_lesson_participants WHERE lesson_id=?',(lesson['lesson_id'],)).fetchone()
        self.assertEqual(p['payment_status'],'PENDING');self.assertEqual(p['access_granted'],0);c.close()

    def test_full_closed_paused_and_inactive(self):
        groups.join(self.token,1);groups.join(self.token,2)
        with self.assertRaisesRegex(ValueError,'group_full'): groups.join(self.token,3)
        with database.connect() as c:c.execute("UPDATE group_members SET status='PAUSED' WHERE user_id=2")
        with self.assertRaisesRegex(ValueError,'group_full'):groups.join(self.token,3)
        group_lessons.set_recruitment(self.gid,'CLOSED')
        self.assertEqual(groups.join(self.token,1)['status'],'ok')
        with self.assertRaisesRegex(ValueError,'group_recruitment_closed'):groups.join(self.token,3)
        with self.assertRaises(PermissionError):groups.join(self.token,4)

    def test_rotation_invalidates_old_link_without_removing_members(self):
        groups.join(self.token,1);new=groups.invitation(self.gid,True).split('invite=')[1]
        with self.assertRaisesRegex(ValueError,'invite_not_found'):groups.join(self.token,2)
        self.assertEqual(groups.join(new,1)['status'],'ok')

    def test_last_place_concurrent_requests(self):
        groups.join(self.token,1)
        def attempt(uid):
            try:groups.join(self.token,uid);return 'ok'
            except ValueError as e:return str(e)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(attempt,[2,3]))
        self.assertCountEqual(results,['ok','group_full'])

    def test_settings_validate_capacity_and_keep_generated_prices(self):
        slot=group_lessons.add_initial_slot(self.gid,0,'18:15',60)
        group_lessons.generate_lesson(self.gid,slot['slot_id'],'2099-01-05T18:15:00')
        payload={**self.group,'name':'Новая группа','price_per_lesson':1800}
        groups.update(self.gid,payload)
        self.assertEqual(groups.settings(self.gid)['group']['price_per_lesson'],1800)
        c=database.connect();self.assertEqual(c.execute('SELECT price_per_student FROM group_lessons').fetchone()[0],1500);c.close()
        payload['board_url']='javascript:alert(1)'
        with self.assertRaisesRegex(ValueError,'invalid_board_url'):groups.update(self.gid,payload)

    def test_registration_skips_individual_schedule_and_retains_invite(self):
        # Existing authentication primitives are not being changed by this feature.
        auth=ModuleType('web_backend.student_auth');auth.set_student_credentials=lambda uid,*a,**kw:{'login':a[0]}
        sessions=ModuleType('web_backend.web_sessions');sessions.create_session=lambda *a:'test-session'
        extras={f'web_backend.{name}':ModuleType(f'web_backend.{name}') for name in ['trial_conversion','public_trial_channel']}
        extras.update({'web_backend.student_auth':auth,'web_backend.web_sessions':sessions})
        with patch.dict(sys.modules,extras):
            sys.modules.pop('web_backend.student_onboarding',None)
            from web_backend import student_onboarding as onboarding
            result=groups.onboarding_start({'group_invite':self.token,'preferred_channel':'TELEGRAM','name':'Новый ученик','grade':11})
            token=result['token'];onboarding.confirm_channel(token,'TELEGRAM','12345678')
            status=groups.onboarding_region({'token':token,'region':'Москва','timezone':'Europe/Moscow'})
            self.assertEqual(status['status'],'SCHEDULE_SET');self.assertEqual(status['schedule'],[])
            self.assertEqual(status['group_invite'],self.token)
            result=groups.onboarding_complete({'token':token,'login':'student','password':'password123'})
            self.assertIn(self.token,result['redirect']);self.assertEqual(result['session_token'],'test-session')
            joined=groups.join(self.token,result['user_id']);self.assertEqual(joined['group_id'],self.gid)
            c=database.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM regular_schedules').fetchone()[0],0);c.close()

    def test_routes_require_auth_and_same_origin_and_delegate_unrelated(self):
        class Base:
            def do_GET(self):return 'original-get'
            def do_POST(self):return 'original-post'
        class Handler(GroupWorkspaceMixin,Base):
            def _json(self,status,body,**kw):return status,body
            def _teacher(self):return None
            def _student(self):return None
            def _same_origin_write(self):return True
        h=Handler();h.path='/api/teacher/group/settings?id=1';self.assertEqual(h.do_GET()[0],401)
        h.path='/api/student/group/invite/join';self.assertEqual(h.do_POST()[0],401)
        h._same_origin_write=lambda:False;self.assertEqual(h.do_POST()[0],403)
        h.path='/api/health';self.assertEqual(h.do_GET(),'original-get');self.assertEqual(h.do_POST(),'original-post')


if __name__=='__main__':unittest.main()
