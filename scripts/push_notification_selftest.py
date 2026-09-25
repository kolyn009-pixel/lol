#!/usr/bin/env python3
"""Isolated notification regression test: PWA subscription backend + delivery payloads + frontend/desktop wiring."""
from pathlib import Path
import json, os, sqlite3, sys, tempfile, types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def need(path,*markers):
    text=(ROOT/path).read_text(encoding='utf-8')
    for marker in markers:
        assert marker in text,(str(path),marker)
    return text

need(Path('web/pwa.js'),
     "desktop_uses_native_notifications",
     "PushManager",
     "/api/push/subscribe",
     "/api/push/test",
     "serviceWorkerReady")
need(Path('web/parent/pwa.js'),
     "PushManager",
     "/api/push/subscribe",
     "navigator.serviceWorker.register")
for path in ('web/service-worker.js','web/parent/service-worker.js','web/teacher-service-worker.js'):
    need(Path(path),"addEventListener('push'","showNotification","notificationclick")
need(Path('web/teacher_dashboard_week.js'),
     'updateDashboardState',
     'setInterval(()=>fetchDash().then(syncDesktopState)',
     'unreadMessages',
     'activeHomework',
     'unpaidAmount')
need(Path('desktop/desktop_ux.js'),
     "Notification.isSupported()",
     "title:'Скоро занятие'",
     "title:'Новое сообщение в Аделии'",
     "title:'ДЗ ждёт проверки'",
     "title:'Оплата требует внимания'")
need(Path('desktop/main.js'),'backgroundThrottling:false')

import database
from web_backend import web_push

tmp=tempfile.NamedTemporaryFile(prefix='adelia-push-',suffix='.db',delete=False)
tmp.close()
def connect():
    conn=sqlite3.connect(tmp.name)
    conn.row_factory=sqlite3.Row
    return conn
database.connect=connect
web_push.database.connect=connect

os.environ['ADELIA_VAPID_PUBLIC_KEY']='test-public'
os.environ['ADELIA_VAPID_PRIVATE_KEY']='test-private'
os.environ['ADELIA_VAPID_SUBJECT']='https://adeliatutor.ru'
sent=[]
class WebPushException(Exception):
    pass
def fake_webpush(**kwargs):
    sent.append(json.loads(kwargs['data']))
fake=types.ModuleType('pywebpush')
fake.WebPushException=WebPushException
fake.webpush=fake_webpush
sys.modules['pywebpush']=fake

web_push.ensure_schema()
routes={'student':'/app/','parent':'/app/parent/','teacher':'/teacher/'}
for index,(role,target) in enumerate(routes.items(),1):
    endpoint=f'https://push.example.test/device-{index}'
    subscription={'endpoint':endpoint,'keys':{'p256dh':'p256','auth':'auth'}}
    session={'role':role,'id':100+index}
    saved=web_push.subscribe(session,subscription,'AdeliaSelftest/1')
    assert saved['status']=='ok'
    state=web_push.status(session)
    assert state['subscriptions']==1 and state['configured']
    result=web_push.send_test(session)
    assert result['sent']==1 and result['failed']==0,result
    payload=sent[-1]
    assert payload['url']==target,(role,payload)
    assert payload['title']=='Аделия 💜'
    assert 'закрыто' in payload['body']
    off=web_push.unsubscribe(session,endpoint)
    assert off['updated']==1
    assert web_push.status(session)['subscriptions']==0

try: os.unlink(tmp.name)
except OSError: pass
print('PUSH_NOTIFICATION_SELFTEST=PASS')
