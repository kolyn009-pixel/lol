"""Avatar decoding, ownership and canonical group chat against isolated SQLite."""
import base64
from io import BytesIO
from pathlib import Path
import struct
import sys
import unittest
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
import group_workspace_selftest as base
import database
from web_backend import group_visuals as visuals,group_workspace as groups
from web_backend.group_media_api import GroupMediaMixin


def png(extra=b'',size=2):
    def chunk(kind,payload):return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
    raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))
    if extra:raw+=chunk(b'tEXt',extra)
    return raw+chunk(b'IDAT',zlib.compress((b'\0'+b'\x99\x66\xbb\xff'*size)*size))+chunk(b'IEND',b'')


class Media(base.Groups):
    def setUp(self):super().setUp();visuals.ensure_schema()

    def test_png_metadata_removed_and_bomb_and_svg_rejected(self):
        cleaned=visuals.png_image(base64.b64encode(png(b'Private camera metadata')).decode())
        self.assertNotIn(b'Private camera',cleaned)
        for data in [b'<svg onload="evil()"/>',png(size=193),png()[:-1],png()+b'bad']:
            with self.assertRaises(ValueError):visuals.png_image(base64.b64encode(data).decode())

    def test_student_photo_visible_to_owner_teacher_and_shared_group_only(self):
        photo=visuals.save_avatar('STUDENT',1,{'png':base64.b64encode(png()).decode()});token=photo['avatar_value'].rsplit('/',1)[-1]
        self.assertTrue(visuals.image(token,1));self.assertTrue(visuals.image(token,teacher=True))
        for viewer in (None,2,3):
            with self.assertRaises(PermissionError):visuals.image(token,viewer)
        groups.join(self.token,1);groups.join(self.token,2)
        self.assertTrue(visuals.image(token,2))
        with self.assertRaises(PermissionError):visuals.image(token,3)

    def test_group_icon_and_student_preset_survive_settings_updates(self):
        visuals.save_avatar('GROUP',self.gid,{'avatar_value':'group_03'})
        groups.update(self.gid,{**self.group,'name':'Другое название'})
        self.assertEqual(groups.settings(self.gid)['group']['avatar_value'],'group_03')
        for preset in ['student_avatar_01','student_avatar_10','adelia_01']:
            self.assertEqual(visuals.save_avatar('STUDENT',1,{'avatar_value':preset})['avatar_value'],preset)
        with self.assertRaises(ValueError):visuals.save_avatar('STUDENT',1,{'avatar_value':'https://external.invalid/photo'})

    def test_photo_replacement_has_one_blob_and_invalid_upload_keeps_photo(self):
        first=visuals.save_avatar('STUDENT',1,{'png':base64.b64encode(png()).decode()})
        with self.assertRaises(ValueError):visuals.save_avatar('STUDENT',1,{'png':'not an image'})
        self.assertTrue(visuals.image(first['avatar_value'].rsplit('/',1)[-1],1))
        second=visuals.save_avatar('STUDENT',1,{'png':base64.b64encode(png()).decode()})
        self.assertNotEqual(first['avatar_value'],second['avatar_value'])
        c=database.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM profile_avatar_images').fetchone()[0],1);c.close()

    def test_teacher_chat_uses_existing_student_room_and_retry_is_idempotent(self):
        result=visuals.teacher_send(self.gid,999,'Здравствуйте!','a'*32)
        self.assertEqual(visuals.teacher_send(self.gid,999,'Здравствуйте!','a'*32)['message_id'],result['message_id'])
        c=database.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM group_chat_messages').fetchone()[0],1)
        c.execute("INSERT INTO group_chat_messages(group_id,sender_user_id,sender_role,body,created_at) VALUES(?,1,'STUDENT','Добрый день!',?)",(self.gid,database.now_iso()));c.commit();c.close()
        items=visuals.teacher_chat(self.gid)['items'];self.assertEqual(len(items),2);self.assertTrue(items[0]['mine']);self.assertFalse(items[1]['mine'])
        with self.assertRaisesRegex(ValueError,'message_key_conflict'):visuals.teacher_send(self.gid,999,'Другой текст','a'*32)
        with database.connect() as c:c.execute("UPDATE study_groups SET chat_mode='CLOSED' WHERE id=?",(self.gid,))
        with self.assertRaisesRegex(ValueError,'group_chat_closed'):visuals.teacher_send(self.gid,999,'Проверка','b'*32)

    def test_routes_auth_and_student_identity_comes_from_session(self):
        class Base:
            def do_GET(self):return 'delegated'
            def do_POST(self):return 'delegated'
        class Handler(GroupMediaMixin,Base):
            def _json(self,s,b):return s,b
            def _same_origin_write(self):return True
            def _student(self):return None
            def _teacher(self):return None
            def _body(self):return {'avatar_value':'student_avatar_03','user_id':2}
        h=Handler();h.path='/api/student/avatar';self.assertEqual(h.do_POST()[0],401)
        h._student=lambda:{'id':1};self.assertEqual(h.do_POST()[0],200)
        c=database.connect();self.assertEqual(c.execute('SELECT user_id FROM student_social_profiles').fetchone()[0],1);c.close()
        h.path='/api/teacher/group/chat';self.assertEqual(h.do_POST()[0],401)
        h.path='/api/health';self.assertEqual(h.do_GET(),'delegated')


if __name__=='__main__':unittest.main()
