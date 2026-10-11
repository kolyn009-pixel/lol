"""Isolated SQLite tests; never use the deployed database or credentials."""
import importlib
import pathlib
import sqlite3
import struct
import sys
import tempfile
import types
import unittest
import zlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = tempfile.TemporaryDirectory()
DB_PATH = str(pathlib.Path(TMP.name) / 'test.db')

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

database = types.ModuleType('database')
database.connect = connect
database.now_iso = lambda: datetime.now(timezone.utc).isoformat()
sys.modules['database'] = database

for name in ('group_lessons', 'group_finance', 'group_runtime_v2', 'group_trials_and_coaching'):
    module = types.ModuleType('web_backend.' + name)
    module.ensure_schema = lambda: None
    sys.modules[module.__name__] = module

def get_group(gid, *_):
    with connect() as c:
        row = c.execute('SELECT * FROM study_groups WHERE id=? AND active=1', (gid,)).fetchone()
    if not row:
        raise ValueError('group_not_found')
    return dict(row)

sys.modules['web_backend.group_lessons'].get_group = get_group
from web_backend import profile_avatars as avatars, student_social_profile as profiles, group_portal as groups

def png(width=2, height=2, raw=None, metadata=False):
    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    raw = raw if raw is not None else (b'\0' + b'\x12\x34\x56\xff' * width) * height
    extra = avatars._chunk(b'tEXt', b'private-camera-info') if metadata else b''
    return b'\x89PNG\r\n\x1a\n' + avatars._chunk(b'IHDR', header) + extra + avatars._chunk(b'IDAT', zlib.compress(raw)) + avatars._chunk(b'IEND', b'')

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        c = connect()
        c.executescript('''
          DROP TABLE IF EXISTS profile_avatars;
          DROP TABLE IF EXISTS student_social_profiles;
          DROP TABLE IF EXISTS student_presence;
          DROP TABLE IF EXISTS group_chat_send_keys;
          DROP TABLE IF EXISTS group_chat_messages;
          DROP TABLE IF EXISTS group_members;
          DROP TABLE IF EXISTS study_groups;
          DROP TABLE IF EXISTS users;
          CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT);
          INSERT INTO users VALUES(1,'Аня'),(2,'Борис'),(3,'Посторонний');
          CREATE TABLE study_groups(id INTEGER PRIMARY KEY,active INTEGER,chat_mode TEXT);
          INSERT INTO study_groups VALUES(1,1,'OPEN'),(2,1,'ANNOUNCEMENTS'),(3,1,'CLOSED');
          CREATE TABLE group_members(group_id INTEGER,user_id INTEGER,status TEXT);
          INSERT INTO group_members VALUES(1,1,'ACTIVE'),(1,2,'PAUSED'),(2,1,'ACTIVE'),(3,1,'ACTIVE');
          CREATE TABLE group_chat_messages(id INTEGER PRIMARY KEY,group_id INTEGER,sender_user_id INTEGER,sender_role TEXT,body TEXT,created_at TEXT,deleted_at TEXT);
        ''')
        c.close()
        profiles.ensure_schema()
        for uid in (1,2,3): profiles.public_profile(uid, viewer_id=uid)
        self.student = {'role':'student','id':1}

    def test_png_roundtrip_and_metadata_removal(self):
        clean = avatars.sanitize_png(png(metadata=True))
        self.assertNotIn(b'private-camera-info', clean)
        self.assertEqual(avatars.sanitize_png(clean), clean)

    def test_png_rejects_svg_corruption_and_trailing_data(self):
        for content in (b'<svg onload="alert(1)">', png()[:-1], png()+b'junk', png().replace(b'IHDR',b'JHDR')):
            with self.subTest(content=content[:12]), self.assertRaises(ValueError): avatars.sanitize_png(content)

    def test_png_dimensions_and_zip_bomb(self):
        for content in (png(257,1), png(raw=b'\0'*500000), png(raw=b'\x05'+b'\0'*17)):
            with self.assertRaises(ValueError): avatars.sanitize_png(content)

    def test_own_avatar_is_persisted_in_database(self):
        result = avatars.save(self.student,content=png())
        self.assertTrue(result['custom'])
        self.assertEqual(avatars.read(self.student,'student',1)['content'],avatars.sanitize_png(png()))
        self.assertEqual(profiles.public_profile(1,viewer_id=1)['avatar_kind'],'CUSTOM')

    def test_image_access_requires_own_shared_group_or_teacher(self):
        avatars.save(self.student,content=png())
        for auth in ({'role':'student','id':2},{'role':'teacher','id':10}):
            self.assertEqual(avatars.read(auth,'student',1)['mime_type'],'image/png')
        for auth in ({'role':'student','id':3},{'role':'parent','id':10}):
            with self.assertRaises(PermissionError): avatars.read(auth,'student',1)
        with self.assertRaises(PermissionError): avatars.read(None,'student',1)

    def test_teacher_and_parent_photo_namespaces_are_separate(self):
        avatars.save({'role':'teacher','id':1},content=png())
        avatars.save({'role':'parent','id':1},preset='student_avatar_04')
        self.assertTrue(avatars.appearance({'role':'teacher','id':1})['custom'])
        self.assertFalse(avatars.appearance({'role':'parent','id':1})['custom'])
        with self.assertRaises(PermissionError): avatars.read(self.student,'teacher',1)

    def test_switching_preset_clears_old_photo(self):
        avatars.save(self.student,content=png())
        profiles.update(1,avatar_kind='PRESET',avatar_value='student_avatar_03')
        self.assertFalse(avatars.appearance(self.student)['custom'])
        self.assertEqual(avatars.appearance(self.student)['preset'],'student_avatar_03')
        with self.assertRaises(FileNotFoundError): avatars.read(self.student,'student',1)

    def test_avatar_rejects_untrusted_url_and_unknown_presets(self):
        for kind,value in [('CUSTOM','javascript:alert(1)'),('CUSTOM','https://tracker.example/pixel'),('CUSTOM','/api/profile/avatar?role=student&id=2'),('PRESET','missing')]:
            with self.assertRaises(ValueError): profiles.update(1,avatar_kind=kind,avatar_value=value)

    def test_group_retry_is_idempotent_and_scoped_to_sender(self):
        key='a'*32
        first=groups.post_group_message(1,1,'STUDENT','Привет',key)
        retry=groups.post_group_message(1,1,'STUDENT','Привет',key)
        other=groups.post_group_message(1,2,'STUDENT','Ответ',key)
        self.assertEqual(first['message_id'],retry['message_id'])
        self.assertNotEqual(first['message_id'],other['message_id'])
        self.assertEqual(len(groups.group_chat(1,1)),2)

    def test_group_author_is_not_confused_with_teacher(self):
        groups.post_group_message(1,1,'STUDENT','Привет')
        groups.post_group_message(1,None,'TEACHER','Здравствуйте')
        items=groups.group_chat(1,1)
        self.assertTrue(items[0]['mine']);self.assertFalse(items[1]['mine'])
        self.assertEqual(items[0]['sender_name'],'Аня')
        self.assertIsNotNone(datetime.fromisoformat(items[0]['created_at']).tzinfo)

    def test_group_access_and_modes(self):
        with self.assertRaises(PermissionError): groups.post_group_message(1,3,'STUDENT','Недоступно')
        with self.assertRaises(PermissionError): groups.group_chat(1,3)
        with self.assertRaises(PermissionError): groups.post_group_message(2,1,'STUDENT','Только объявления')
        groups.post_group_message(2,None,'TEACHER','Объявление')
        with self.assertRaises(ValueError): groups.post_group_message(3,None,'TEACHER','Закрыт')

    def test_group_message_validation(self):
        for args in [(1,1,'STUDENT',''),(1,1,'STUDENT','a'*4001),(1,1,'STUDENT','Hi','bad'),(1,1,'PARENT','Hi')]:
            with self.assertRaises(ValueError): groups.post_group_message(*args)

    def test_avatar_routes_require_authentication_and_same_origin(self):
        class Handler(avatars.AvatarMixin):
            def _auth(self): return None
            def _same_origin_write(self): return False
            def _json(self,status,body): self.response=(status,body)
        handler=Handler()
        self.assertTrue(handler.avatar_get('/api/profile/appearance',{}));self.assertEqual(handler.response[0],401)
        self.assertTrue(handler.avatar_post('/api/profile/avatar'));self.assertEqual(handler.response[0],403)

if __name__ == '__main__':
    try: unittest.main()
    finally: TMP.cleanup()
