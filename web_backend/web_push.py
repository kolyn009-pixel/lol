"""Web Push subscriptions and delivery for Adelia PWA.

Secrets are provided only through environment variables:
 ADELIA_VAPID_PUBLIC_KEY  - URL-safe base64 public key for PushManager
 ADELIA_VAPID_PRIVATE_KEY - PEM, escaped PEM, DER key, or PEM file path accepted by pywebpush
 ADELIA_VAPID_SUBJECT     - mailto: or https: contact (default site URL)
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import database


def _now():
    return datetime.now().isoformat(timespec='seconds')


def public_key():
    return str(os.getenv('ADELIA_VAPID_PUBLIC_KEY') or '').strip()


def private_key():
    value=str(os.getenv('ADELIA_VAPID_PRIVATE_KEY') or '').strip()
    if not value:
        return ''
    # Preferred production format is an absolute path to a protected PEM file.
    if os.path.isfile(value):
        return value
    # Backwards compatibility: early Adelia deployments stored a PEM in an env
    # file with literal "\\n" separators. Convert that representation to PEM.
    if '-----BEGIN' in value and '\\n' in value:
        return value.replace('\\n','\n')
    return value


def subject():
    return str(os.getenv('ADELIA_VAPID_SUBJECT') or 'https://adeliatutor.ru').strip()


def configured():
    if not public_key() or not private_key():
        return False
    try:
        import pywebpush  # noqa:F401
        return True
    except Exception:
        return False


def ensure_schema():
    conn=database.connect()
    conn.execute('''CREATE TABLE IF NOT EXISTS web_push_subscriptions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        endpoint TEXT NOT NULL UNIQUE,
        p256dh TEXT NOT NULL,
        auth TEXT NOT NULL,
        user_agent TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_success_at TEXT,
        last_error TEXT
    )''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_web_push_owner ON web_push_subscriptions(role,entity_id,enabled)')
    conn.commit();conn.close()


def _owner(session):
    if not session:
        raise PermissionError('unauthorized')
    role=str(session.get('role') or '').lower().strip()
    entity_id=session.get('id')
    if role not in {'student','teacher','parent'} or entity_id in (None,''):
        raise PermissionError('unsupported_session')
    return role,int(entity_id)


def subscribe(session,subscription,user_agent=None):
    role,entity_id=_owner(session)
    if not isinstance(subscription,dict):
        raise ValueError('invalid_subscription')
    endpoint=str(subscription.get('endpoint') or '').strip()
    keys=subscription.get('keys') or {}
    p256dh=str(keys.get('p256dh') or '').strip();auth=str(keys.get('auth') or '').strip()
    if not endpoint.startswith('https://') or not p256dh or not auth:
        raise ValueError('invalid_subscription')
    now=_now();ensure_schema();conn=database.connect()
    conn.execute('''INSERT INTO web_push_subscriptions(role,entity_id,endpoint,p256dh,auth,user_agent,enabled,created_at,updated_at,last_error)
                    VALUES(?,?,?,?,?,?,1,?,?,NULL)
                    ON CONFLICT(endpoint) DO UPDATE SET role=excluded.role,entity_id=excluded.entity_id,p256dh=excluded.p256dh,auth=excluded.auth,user_agent=excluded.user_agent,enabled=1,updated_at=excluded.updated_at,last_error=NULL''',
                 (role,entity_id,endpoint,p256dh,auth,str(user_agent or '')[:500],now,now))
    conn.commit();row=conn.execute('SELECT id FROM web_push_subscriptions WHERE endpoint=?',(endpoint,)).fetchone();conn.close()
    return {'status':'ok','subscription_id':int(row['id'])}


def unsubscribe(session,endpoint):
    role,entity_id=_owner(session);endpoint=str(endpoint or '').strip();ensure_schema();conn=database.connect()
    cur=conn.execute('UPDATE web_push_subscriptions SET enabled=0,updated_at=? WHERE role=? AND entity_id=? AND endpoint=?',(_now(),role,entity_id,endpoint))
    conn.commit();conn.close();return {'status':'ok','updated':int(cur.rowcount or 0)}


def status(session):
    role,entity_id=_owner(session);ensure_schema();conn=database.connect()
    row=conn.execute('SELECT COUNT(*) c FROM web_push_subscriptions WHERE role=? AND entity_id=? AND enabled=1',(role,entity_id)).fetchone();conn.close()
    return {'configured':configured(),'public_key_present':bool(public_key()),'subscriptions':int(row['c'] or 0)}


def _subscription_info(row):
    return {'endpoint':row['endpoint'],'keys':{'p256dh':row['p256dh'],'auth':row['auth']}}


def send(role,entity_id,title,body,url='/app/',tag=None,data=None):
    """Send a notification to every active device for an authenticated entity."""
    if not configured():
        return {'status':'not_configured','sent':0,'failed':0}
    from pywebpush import WebPushException, webpush
    ensure_schema();conn=database.connect();rows=conn.execute('SELECT * FROM web_push_subscriptions WHERE role=? AND entity_id=? AND enabled=1',(str(role),int(entity_id))).fetchall()
    payload=json.dumps({'title':str(title or 'Аделия'),'body':str(body or ''),'url':str(url or '/app/'),'tag':str(tag or 'adelia'),'data':data or {}},ensure_ascii=False)
    sent=0;failed=0;now=_now()
    for row in rows:
        try:
            webpush(subscription_info=_subscription_info(row),data=payload,vapid_private_key=private_key(),vapid_claims={'sub':subject()})
            conn.execute('UPDATE web_push_subscriptions SET last_success_at=?,last_error=NULL,updated_at=? WHERE id=?',(now,now,int(row['id'])));sent+=1
        except WebPushException as exc:
            failed+=1;code=getattr(getattr(exc,'response',None),'status_code',None);detail=str(exc).replace('\n',' ')[:220];err=f'{type(exc).__name__}:{code or ""}:{detail}'[:300]
            disable=code in {404,410}
            conn.execute('UPDATE web_push_subscriptions SET enabled=?,last_error=?,updated_at=? WHERE id=?',(0 if disable else 1,err,now,int(row['id'])))
        except Exception as exc:
            failed+=1;detail=str(exc).replace('\n',' ')[:240];err=f'{type(exc).__name__}:{detail}'[:300]
            conn.execute('UPDATE web_push_subscriptions SET last_error=?,updated_at=? WHERE id=?',(err,now,int(row['id'])))
    conn.commit();conn.close();return {'status':'ok','sent':sent,'failed':failed}


def send_test(session):
    role,entity_id=_owner(session)
    target='/teacher/' if role=='teacher' else ('/app/parent/' if role=='parent' else '/app/')
    return send(role,entity_id,'Аделия 💜','Уведомления работают. Теперь важные события смогут приходить даже когда приложение закрыто.',target,'adelia-test')
