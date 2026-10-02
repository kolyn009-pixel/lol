"""Isolated real-SQLite tests. Does not load production settings or databases."""
import importlib
import io
import json
import pathlib
import sqlite3
import sys
import tempfile
import types
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
tmp = tempfile.TemporaryDirectory()
def connect():
    c = sqlite3.connect(str(pathlib.Path(tmp.name) / 'test.db'), timeout=15)
    c.row_factory = sqlite3.Row
    return c
db = types.ModuleType('database')
db.connect = connect
db.now_iso = lambda: '2026-10-02T12:00:00'
db.get_user = lambda uid: {'id': uid}
sys.modules['database'] = db
from web_backend import legal_documents as legal
from web_backend.legal_api import LegalMixin
from web_backend import finance_pricing as pricing, public_catalog


class Handler(LegalMixin):
    def __init__(self, role='parent', uid=1, origin=True, body=None):
        self.auth = {'role': role, 'id': uid} if role else None
        self.origin = origin
        self.body = body
    def _auth(self): return self.auth
    def _teacher(self): return self.auth if self.auth and self.auth['role']=='teacher' else None
    def _owner(self): return self._teacher() if self.auth and self.auth['id']==42 else None
    def _same_origin_write(self): return self.origin
    def _body(self): return self.body
    def _legal_body(self): return self.body
    def _json(self, status, data): self.response = (status, data)


class LegalTests(unittest.TestCase):
    def setUp(self):
        legal.ensure_schema()
        c=connect()
        for table in ('legal_draft','legal_current','legal_editions','parent_legal_acceptances'):
            c.execute('DELETE FROM '+table)
        c.commit();c.close()
        self.data = dict(name='Тестовый исполнитель', inn='500100732259', email='test@example.com',
                         phone='+79990000000', address='Тестовый адрес',
                         terms='Условия для проверки. '*12, privacy='Политика для проверки. '*12,
                         consent='Отдельное согласие для проверки. '*12, reviewed=True)
    def publish(self): return legal.save(self.data, 42, True)['version']
    def accept(self, uid=1, version=None):
        return legal.accept(uid, dict(version=version or legal.public()['version'],terms=True,privacy_ack=True,consent=True))
    def test_draft_is_private_and_does_not_gate(self):
        legal.save({'terms':'черновик'},42)
        self.assertIsNone(legal.public())
        self.assertFalse(legal.status(1)['required'])
        with self.assertRaises(ValueError): legal.save({'terms':'черновик','reviewed':True},42,True)
    def test_explicit_checkboxes_and_stale_version(self):
        version=self.publish()
        for val in (False, 'true', 1, None):
            with self.assertRaises(ValueError): legal.accept(1,dict(version=version,terms=True,privacy_ack=True,consent=val))
        with self.assertRaisesRegex(ValueError,'documents_changed'): self.accept(version='stale')
        self.assertTrue(legal.status(1)['required'])
    def test_versions_identity_and_immutable_history(self):
        old=self.publish();self.accept()
        self.assertFalse(legal.status(1)['required']);self.assertTrue(legal.status(2)['required'])
        self.data['terms']+='Новая редакция.'
        legal.save(self.data,42) # Saving a draft does not invalidate acceptance.
        self.assertFalse(legal.status(1)['required'])
        new=self.publish()
        self.assertNotEqual(old,new);self.assertTrue(legal.status(1)['required'])
        self.assertNotIn('Новая редакция',legal.public(old)['terms'])
        self.accept();self.assertFalse(legal.status(1)['required'])
        c=connect();self.assertEqual(c.execute('SELECT count(*) FROM parent_legal_acceptances').fetchone()[0],2);c.close()
    def test_parallel_retries_are_idempotent(self):
        self.publish()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.accept(),range(8)))
        c=connect();self.assertEqual(c.execute('SELECT count(*) FROM parent_legal_acceptances').fetchone()[0],1);c.close()
    def test_auth_csrf_and_server_gate(self):
        v=self.publish()
        for role in (None,'student','parent'):
            h=Handler(role=role);h.legal_get('/api/teacher/legal',{});self.assertEqual(h.response[0],403)
        h=Handler(role='teacher');h.legal_post('/api/teacher/legal/publish');self.assertEqual(h.response[0],403)
        h=Handler(origin=False);h.legal_post('/api/parent/legal/accept');self.assertEqual(h.response[0],403)
        h=Handler(uid=2,body=dict(version=v,terms=True,privacy_ack=True,consent=True,parent_id=1))
        h.legal_post('/api/parent/legal/accept');self.assertEqual(h.response[0],200)
        self.assertTrue(legal.status(1)['required']);self.assertFalse(legal.status(2)['required'])
        for path in ('/api/parent/dashboard','/api/parent/messages/send','/api/payments/robokassa/checkout','/api/messages/media'):
            h=Handler();self.assertTrue(h.legal_parent_gate(path));self.assertEqual(h.response[0],428)
        for path in ('/api/auth/logout','/api/public/legal','/api/parent/legal/status','/api/payments/robokassa/result'):
            self.assertFalse(Handler().legal_parent_gate(path))
        self.accept();self.assertFalse(Handler().legal_parent_gate('/api/parent/dashboard'))
    def test_publish_validation(self):
        for field,value in [('inn','000000000000'),('inn','500100732250'),('email','invalid'),('terms','[Заполнить правила]'),('reviewed',False)]:
            body={**self.data,field:value}
            with self.assertRaises(ValueError): legal.save(body,42,True)
        self.assertIsNone(legal.public())
    def test_wire_body_size_and_type(self):
        raw=json.dumps({'terms':'a'*70000}).encode()
        h=Handler();h.headers={'Content-Type':'application/json','Content-Length':str(len(raw))};h.rfile=io.BytesIO(raw)
        self.assertEqual(len(LegalMixin._legal_body(h)['terms']),70000)
        h.headers={'Content-Type':'text/plain','Content-Length':str(len(raw))};h.rfile=io.BytesIO(raw)
        self.assertIsNone(LegalMixin._legal_body(h))
        h.headers={'Content-Type':'application/json','Content-Length':'300000'}
        self.assertIsNone(LegalMixin._legal_body(h))


class PricingTests(unittest.TestCase):
    def test_duration_sync_public_catalog_and_disabled_rates(self):
        c=connect()
        c.execute('CREATE TABLE IF NOT EXISTS price_settings(rate_key TEXT PRIMARY KEY,study_goal TEXT,subject TEXT,grade_min INTEGER,grade_max INTEGER,hourly_rate INTEGER,title TEXT,active INTEGER,created_at TEXT,updated_at TEXT)')
        c.commit();c.close()
        pricing.set_price('EGE_PHYSICS',2400,duration_minutes=90)
        items={x['key']:x for x in public_catalog.get_public_price_catalog()}
        self.assertEqual((items['EGE_PHYSICS']['amount'],items['EGE_PHYSICS']['duration_minutes'],items['EGE_PHYSICS']['hourly_rate']),(2400,90,1600))
        c=connect();self.assertEqual(c.execute("SELECT hourly_rate FROM price_settings WHERE rate_key='EGE_PHYSICS'").fetchone()[0],1600);c.close()
        pricing.set_price('COLLEGE_PHYSICS',2000,duration_minutes=60)
        self.assertIn('COLLEGE_PHYSICS',{x['key'] for x in public_catalog.get_public_price_catalog()})
        pricing.set_price('EGE_PHYSICS',2400,duration_minutes=90,active=False)
        self.assertNotIn('EGE_PHYSICS',{x['key'] for x in public_catalog.get_public_price_catalog()})

if __name__=='__main__': unittest.main()
