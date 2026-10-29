"""Hourly reminders, daily official-source checks and leased per-channel delivery.

Systemd runs one worker; the process lock also prevents overlapping manual runs.
External transports are at-least-once across a crash after remote acceptance.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timedelta,timezone
import fcntl
import json
import os
from pathlib import Path
import database
from web_backend import olympiad_store as store,olympiad_sources as sources


def claim(limit=40):
    c=database.connect();at=store.stamp();cutoff=store.stamp(store.now()-timedelta(minutes=15))
    try:
        c.execute('BEGIN IMMEDIATE')
        ids=[r['id'] for r in c.execute("""SELECT id FROM olympiad_delivery_outbox WHERE attempts<8
          AND next_at<=? AND (status='PENDING' OR (status='CLAIMED' AND claimed_at<?)) ORDER BY id LIMIT ?""",(at,cutoff,limit))]
        out=[]
        for i in ids:
            c.execute("UPDATE olympiad_delivery_outbox SET status='CLAIMED',claimed_at=? WHERE id=?",(at,i))
            out.append(dict(c.execute('''SELECT d.*,n.role,n.entity_id,n.olympiad_id,n.text,n.dedupe_key,n.created_at
              FROM olympiad_delivery_outbox d JOIN olympiad_notices n ON n.id=d.notice_id WHERE d.id=?''',(i,)).fetchone()))
        c.commit();return out
    finally:c.close()


def deliver(item):
    c=database.connect()
    try:
        sub=c.execute('SELECT channels_json FROM olympiad_subscriptions WHERE role=? AND entity_id=? AND olympiad_id=?',
                      (item['role'],item['entity_id'],item['olympiad_id'])).fetchone()
        if not sub or item['channel'] not in json.loads(sub['channels_json']):return 'SKIPPED'
        key=item['dedupe_key'].split(':')
        if len(key)>4 and key[2]=='remind':
            event=c.execute('SELECT revision,status FROM olympiad_events WHERE id=?',(key[3],)).fetchone()
            if not event or event['revision']!=int(key[4]) or event['status']!='CONFIRMED':return 'SKIPPED'
            if store.now()-datetime.fromisoformat(item['created_at'])>timedelta(hours=12):return 'SKIPPED'
    finally:c.close()
    from vk_adapter import channel_delivery as delivery
    role=item['role'];uid=item['entity_id'];channel=item['channel']
    url='https://adeliatutor.ru/'+('app/teacher.html' if role=='teacher' else 'app/')+'?olympiads=1'
    text=item['text']+'\n\nАделия: '+url
    if channel=='TELEGRAM':
        ok=delivery.send_telegram_chat(uid,text) if role=='teacher' else delivery.send_telegram(uid,text)
    elif channel=='VK' and role=='student':
        ok=delivery.send_vk(uid,text)
    elif channel=='PUSH':
        from web_backend import web_push
        result=web_push.send(role,uid,'Олимпиады · Аделия',item['text'],url,'olympiad-'+str(item['notice_id']))
        ok=result.get('sent',0)>0 and result.get('failed',0)==0
    else:return 'SKIPPED'
    return 'SENT' if ok else 'PENDING'


def process(delivery=deliver):
    out=[]
    for item in claim():
        try:
            status=delivery(item);error=None if status in {'SENT','SKIPPED'} else 'transport_not_delivered'
        except Exception as exc:
            status='PENDING';error=type(exc).__name__
        attempts=item['attempts']+1
        if status=='PENDING' and attempts>=8:status='FAILED'
        c=database.connect()
        try:
            c.execute('''UPDATE olympiad_delivery_outbox SET status=?,attempts=?,next_at=?,claimed_at=NULL,last_error=?
              WHERE id=? AND status='CLAIMED' AND claimed_at=?''',
              (status,attempts,store.stamp(store.now()+timedelta(minutes=min(240,2**attempts))),error,item['id'],item['claimed_at']))
            c.commit()
        finally:c.close()
        out.append({'id':item['id'],'channel':item['channel'],'status':status})
    return out


def run(force=False):
    sources.seed()
    c=database.connect()
    try:r=c.execute('SELECT checked_at FROM olympiad_sources WHERE url=?',(sources.REGISTRY,)).fetchone()
    finally:c.close()
    refresh=force or not r or not r['checked_at'] or store.now()-datetime.fromisoformat(r['checked_at'])>=timedelta(hours=24)
    report=sources.refresh() if refresh else None
    return {'refresh':report,'reminders':store.enqueue_reminders(),'deliveries':process()}


def main():
    p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');args=p.parse_args()
    lock_path=os.getenv('ADELIA_OLYMPIAD_LOCK','/run/adelia-olympiads.lock')
    with open(lock_path,'a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        print(json.dumps(run(args.refresh),ensure_ascii=False))


if __name__=='__main__':main()
