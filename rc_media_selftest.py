from __future__ import annotations
import json, os, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
os.chdir(ROOT)
tmp=Path(tempfile.mkdtemp(prefix="adelia_rc_media_"))
os.environ["ADELIA_MESSAGE_MEDIA_DIR"]=str(tmp/"media")

import database
database.set_test_mode(True)
database.DB_NAME=str(tmp/"media.db")
database.create_tables()

from web_backend import message_media, unified_messaging as um, message_delivery
from vk_adapter import channel_delivery, attachment_bridge

for mod in (database,message_media,um,message_delivery,channel_delivery,attachment_bridge):
    p=Path(mod.__file__).resolve()
    assert ROOT==p or ROOT in p.parents, f"wrong import root: {mod.__name__} -> {p}"

uid=database.add_telegram_user(990000003,"rc_media","RC Media",10,"EGE","PHYSICS")
c=database.connect()
c.execute("CREATE TABLE IF NOT EXISTS channel_identities(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,channel TEXT NOT NULL,external_id TEXT,enabled INTEGER DEFAULT 1)")
c.execute("INSERT INTO channel_identities(user_id,channel,external_id,enabled) VALUES(?,?,?,1)",(uid,"VK","222222"))
c.commit();c.close()

payload=b"ADELIA_RC_MEDIA_PAYLOAD"
media=message_media.store_bytes(uid,payload,"gate-photo.jpg","image/jpeg","photo",origin="WEB")
meta,data=message_media.read(media["token"])
assert data==payload and meta["sha256"]==media["sha256"]

mid=um.record_message(uid,"OUT","media",participant_type="STUDENT",sender_type="TEACHER",sender_id=1,origin_channel="WEB",content_type="PHOTO",attachment=media,status="SENT")
c=database.connect();row=c.execute("SELECT attachment_json FROM unified_messages WHERE id=?",(mid,)).fetchone();c.close()
assert message_media.attachment_items(json.loads(row["attachment_json"]))[0]["token"]==media["token"]

calls=[]
channel_delivery.telegram_chat=lambda uid:111111
channel_delivery.vk_peer=lambda uid:222222
def forbidden(*a,**k): raise AssertionError("text/network transport used")
channel_delivery.send_telegram=forbidden
channel_delivery.send_vk=forbidden
attachment_bridge._json_request=forbidden
attachment_bridge._bytes_request=forbidden
attachment_bridge._vk_api=forbidden
def tg(chat_id,content,filename,caption="",as_photo=False,content_type=None):
    calls.append(("TELEGRAM",content,filename,as_photo,content_type));return True
def vk(peer_id,content,filename,caption="",as_photo=False,content_type=None):
    calls.append(("VK",content,filename,as_photo,content_type));return True
attachment_bridge.telegram_send_bytes=tg
attachment_bridge.vk_send_bytes=vk
r=message_delivery.send_existing_message_channels(mid,["TELEGRAM","VK"])
assert r["status"]=="ok",r
assert {x[0] for x in calls}=={"TELEGRAM","VK"},calls
assert all(x[1]==payload and x[2]=="gate-photo.jpg" and x[3] and x[4]=="image/jpeg" for x in calls)

teacher_js=(ROOT/"web/teacher_messages_stage10.js").read_text()
student_js=(ROOT/"web/student_chat.js").read_text()
stage10=(ROOT/"web_backend/stage10_api.py").read_text()
api2=(ROOT/"web_backend/api_v2.py").read_text()
assert "FormData" in teacher_js and "/teacher/messages/upload" in teacher_js
assert "FormData" in student_js and "/student/message-media/upload" in student_js
assert "/api/teacher/messages/upload" in stage10
assert "/api/student/message-media/upload" in api2
print("RC MEDIA SELFTEST: OK")
print("imports=release durable=1 teacher_upload=1 student_upload=1 telegram=1 vk=1")
