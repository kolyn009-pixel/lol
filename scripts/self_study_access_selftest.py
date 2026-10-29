import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import self_study_selftest as fixture
from web_backend import self_study_access as access
from web_backend.self_study_api import ROOT,GET_PATHS,POST_PATHS


class Parent(fixture.FakeHandler):
    def _teacher(self):return None
    def _auth(self):return {'id':101,'role':'parent'} if self.teacher else None


class Student(Parent):
    def _auth(self):return {'id':101,'role':'student'} if self.teacher else None
    def _student(self):return self._auth()


class Tests(unittest.TestCase):
    def setUp(self):
        access.ensure_schema();conn=fixture.connect()
        conn.executescript("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);
          CREATE TABLE IF NOT EXISTS parent_accounts(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);
          INSERT OR REPLACE INTO users VALUES(101,'Сестра',1),(102,'Брат',1);
          INSERT OR REPLACE INTO parent_accounts VALUES(101,'Мама',1),(102,'Папа',1);
          DELETE FROM personal_study_memberships;DELETE FROM personal_study_invitations;
          INSERT OR REPLACE INTO admin_accounts VALUES(303,'ADMIN',1);""");conn.commit();conn.close()

    def invite(self,role='student',sid=101):return access.issue(101,{'account_role':role,'account_id':sid})

    def test_student_and_parent_same_id_are_distinct(self):
        token=self.invite('parent')['token'];access.accept(101,{'token':token},'parent')
        self.assertTrue(access.is_member(101,'parent'));self.assertFalse(access.is_member(101,'student'))
        self.assertNotEqual(access.study_identity('parent',101),access.study_identity('student',101))

    def test_only_owner_can_manage_language_invitations(self):
        for teacher in (303,999):
            with self.assertRaises(PermissionError):access.issue(teacher,{'student_id':101})
            with self.assertRaises(PermissionError):access.overview(teacher)

    def test_link_is_account_and_role_bound(self):
        token=self.invite()['token']
        for sid,role in ((102,'student'),(101,'parent')):
            with self.assertRaises(PermissionError):access.accept(sid,{'token':token},role)
        access.accept(101,{'token':token})

    def test_token_is_hashed_and_not_returned_in_lists(self):
        token=self.invite()['token'];conn=fixture.connect();row=conn.execute('SELECT * FROM personal_study_invitations').fetchone();conn.close()
        self.assertNotIn(token,str(dict(row)));self.assertNotIn(token,str(access.overview(101)))

    def test_expiry_prevents_activation(self):
        with patch.object(access.time,'time',return_value=1000):token=self.invite()['token']
        with patch.object(access.time,'time',return_value=1000+8*86400):
            with self.assertRaises(PermissionError):access.accept(101,{'token':token})

    def test_concurrent_activation_idempotent(self):
        token=self.invite()['token']
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:access.accept(101,{'token':token}),range(3)))
        self.assertEqual([{'status':'active'}]*3,results)

    def test_revocation_blocks_every_language_route(self):
        token=self.invite('parent')['token'];access.accept(101,{'token':token},'parent')
        access.revoke(101,{'account_role':'parent','account_id':101})
        for path in GET_PATHS:
            if '/parent/' in path:self.assertEqual(403,Parent().self_study_route(path)[0])
        for path in POST_PATHS:
            if '/parent/' in path and not path.endswith('/access/accept'):
                self.assertEqual(403,Parent(body={}).self_study_route(path,write=True)[0])
        with self.assertRaises(PermissionError):access.accept(101,{'token':token},'parent')

    def test_parent_can_activate_and_use_own_profile(self):
        token=self.invite('parent')['token']
        path=(ROOT+'/access/accept').replace('/teacher/','/parent/')
        self.assertEqual(200,Parent(body={'token':token}).self_study_route(path,write=True)[0])
        status,data=Parent().self_study_route(ROOT.replace('/teacher/','/parent/'))
        self.assertEqual(200,status);self.assertEqual(-(10**12+101),data['owner_id'])
        self.assertNotEqual(-101,data['owner_id'])

    def test_no_language_invite_means_no_course_access(self):
        self.assertEqual(403,Student().self_study_route(ROOT.replace('/teacher/','/student/'))[0])
        self.assertEqual(403,Parent().self_study_route(ROOT.replace('/teacher/','/parent/'))[0])

    def test_renewal_invalidates_old_link(self):
        first=self.invite()['token'];second=self.invite()['token']
        with self.assertRaises(PermissionError):access.accept(101,{'token':first})
        access.accept(101,{'token':second})

    def test_working_accounts_unchanged_by_invite_accept_revoke(self):
        conn=fixture.connect();before=[tuple(r) for r in conn.execute('SELECT * FROM users')]+[tuple(r) for r in conn.execute('SELECT * FROM parent_accounts')];conn.close()
        token=self.invite('parent')['token'];access.accept(101,{'token':token},'parent');access.revoke(101,{'account_role':'parent','account_id':101})
        conn=fixture.connect();after=[tuple(r) for r in conn.execute('SELECT * FROM users')]+[tuple(r) for r in conn.execute('SELECT * FROM parent_accounts')];conn.close()
        self.assertEqual(before,after)

    def test_accept_requires_session_and_origin(self):
        path=(ROOT+'/access/accept').replace('/teacher/','/parent/')
        self.assertEqual(401,Parent(teacher=None,body={}).self_study_route(path,write=True)[0])
        self.assertEqual(403,Parent(body={},origin=False).self_study_route(path,write=True)[0])


if __name__=='__main__':unittest.main()
