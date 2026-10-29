"""Olympiad calendar: independent, additive tables in the shared database.

All instants are aware UTC; date-only intervals use inclusive calendar dates in
Europe/Moscow. Unpublished dates are NULL, never guessed from the previous year.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import database

TZ = ZoneInfo('Europe/Moscow')
KINDS = {'REGISTRATION', 'QUALIFIER', 'FINAL', 'RESULTS', 'APPEAL'}
CHANNELS = {'WEB', 'PUSH', 'TELEGRAM', 'VK'}


def now():
    return datetime.now(timezone.utc)


def stamp(value=None):
    return (value or now()).astimezone(timezone.utc).isoformat(timespec='seconds')


def season(value=None):
    d = (value or now()).astimezone(TZ)
    y = d.year if d.month >= 8 else d.year - 1
    return f'{y}/{y+1}'


def identity(year, number, subject):
    return f'{year.replace("/", "-")}-{int(number)}-{subject.lower()}'


def ensure_schema():
    c = database.connect()
    try:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS olympiad_catalog(
          id TEXT PRIMARY KEY,season TEXT NOT NULL,registry_number INTEGER NOT NULL,
          title TEXT NOT NULL,subject TEXT NOT NULL,level INTEGER NOT NULL,
          official_url TEXT NOT NULL,registry_url TEXT NOT NULL,
          grade_min INTEGER,grade_max INTEGER,grade_source TEXT,
          registry_checked_at TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS olympiad_sources(
          url TEXT PRIMARY KEY,adapter TEXT NOT NULL DEFAULT 'review',content_hash TEXT,
          checked_at TEXT,changed_at TEXT,error TEXT,review_required INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS olympiad_source_links(
          olympiad_id TEXT NOT NULL,url TEXT NOT NULL,PRIMARY KEY(olympiad_id,url));
        CREATE TABLE IF NOT EXISTS olympiad_events(
          id TEXT PRIMARY KEY,olympiad_id TEXT NOT NULL,stage_key TEXT NOT NULL,
          title TEXT NOT NULL,kind TEXT NOT NULL,start_at TEXT,end_at TEXT,
          precision TEXT NOT NULL,status TEXT NOT NULL,format TEXT NOT NULL,
          source_url TEXT NOT NULL,evidence TEXT NOT NULL DEFAULT '',checked_at TEXT NOT NULL,
          revision INTEGER NOT NULL DEFAULT 1,manual INTEGER NOT NULL DEFAULT 0,
          UNIQUE(olympiad_id,stage_key));
        CREATE TABLE IF NOT EXISTS olympiad_event_history(
          id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL,
          revision INTEGER NOT NULL,before_json TEXT,after_json TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS olympiad_subscriptions(
          role TEXT NOT NULL,entity_id INTEGER NOT NULL,olympiad_id TEXT NOT NULL,
          channels_json TEXT NOT NULL,created_at TEXT NOT NULL,
          PRIMARY KEY(role,entity_id,olympiad_id));
        CREATE TABLE IF NOT EXISTS olympiad_recommendations(
          user_id INTEGER NOT NULL,olympiad_id TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',
          goal INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,
          PRIMARY KEY(user_id,olympiad_id));
        CREATE TABLE IF NOT EXISTS olympiad_notices(
          id INTEGER PRIMARY KEY AUTOINCREMENT,dedupe_key TEXT NOT NULL UNIQUE,
          role TEXT NOT NULL,entity_id INTEGER NOT NULL,olympiad_id TEXT NOT NULL,
          text TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS olympiad_delivery_outbox(
          id INTEGER PRIMARY KEY AUTOINCREMENT,notice_id INTEGER NOT NULL,channel TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'PENDING',attempts INTEGER NOT NULL DEFAULT 0,
          next_at TEXT NOT NULL,claimed_at TEXT,last_error TEXT,
          UNIQUE(notice_id,channel));
        CREATE INDEX IF NOT EXISTS idx_olympiad_notices_owner ON olympiad_notices(role,entity_id,id);
        CREATE INDEX IF NOT EXISTS idx_olympiad_delivery_pending ON olympiad_delivery_outbox(status,next_at);
        ''')
        c.commit()
    finally:
        c.close()


def catalog_item(c, oid):
    row = c.execute('SELECT * FROM olympiad_catalog WHERE id=?', (str(oid),)).fetchone()
    if not row:
        raise ValueError('olympiad_not_found')
    return dict(row)


def upsert_catalog(items, checked=None, authoritative=False):
    ensure_schema()
    at = stamp(checked)
    c = database.connect()
    try:
        if authoritative:
            years={x['season'] for x in items}
            if len(years)!=1:raise ValueError('invalid_registry_season')
            year=next(iter(years))
            prior=c.execute('SELECT COUNT(*) FROM olympiad_catalog WHERE season=? AND active=1',(year,)).fetchone()[0]
            if len(items)<max(15,int(prior*.8)):
                raise ValueError('registry_incomplete_needs_review')
        for x in items:
            c.execute('''INSERT INTO olympiad_catalog
              (id,season,registry_number,title,subject,level,official_url,registry_url,
               grade_min,grade_max,grade_source,registry_checked_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
              title=excluded.title,level=excluded.level,official_url=excluded.official_url,
              registry_url=excluded.registry_url,registry_checked_at=excluded.registry_checked_at,active=1''',
              (x['id'], x['season'], x['registry_number'], x['title'], x['subject'], x['level'],
               x['official_url'], x['registry_url'], x.get('grade_min'), x.get('grade_max'), x.get('grade_source'), at))
        if authoritative:
            ids=[x['id'] for x in items]
            c.execute('UPDATE olympiad_catalog SET active=0 WHERE season=? AND id NOT IN ('+','.join('?' for _ in ids)+')',(year,*ids))
        c.commit()
    finally:
        c.close()


def event_boundary(value, precision, end=False):
    if not value:
        return None
    if precision == 'DATE':
        d = date.fromisoformat(value)
        return datetime.combine(d + (timedelta(days=1) if end else timedelta()), time.min, TZ)
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError('timezone_required')
    return dt


def validate_event(data):
    value = {k: str(data.get(k) or '').strip() for k in
             ('stage_key','title','kind','precision','status','format','source_url','evidence')}
    if not 1 <= len(value['stage_key']) <= 80 or not 1 <= len(value['title']) <= 180:
        raise ValueError('invalid_stage')
    if value['kind'] not in KINDS or value['precision'] not in {'DATE','TIME'}:
        raise ValueError('invalid_stage')
    if value['status'] not in {'CONFIRMED','TENTATIVE','UNKNOWN','CANCELLED'}:
        raise ValueError('invalid_status')
    if value['format'] not in {'ONLINE','OFFLINE','MIXED','UNKNOWN'}:
        raise ValueError('invalid_format')
    for k in ('start_at','end_at'):
        raw = data.get(k)
        value[k] = str(raw).strip() if raw else None
        if value[k]:
            event_boundary(value[k], value['precision'])
    if value['status'] in {'UNKNOWN','CANCELLED'}:
        value['start_at'] = value['end_at'] = None
    if value['status'] in {'CONFIRMED','TENTATIVE'} and not (value['start_at'] or value['end_at']):
        raise ValueError('date_required')
    start = event_boundary(value['start_at'], value['precision'])
    end = event_boundary(value['end_at'], value['precision'], True)
    if start and end and end <= start:
        raise ValueError('invalid_interval')
    if len(value['evidence']) > 1000:
        raise ValueError('evidence_too_long')
    return value


def _notice(c, role, uid, oid, key, text, channels, at):
    cur = c.execute('''INSERT OR IGNORE INTO olympiad_notices
        (dedupe_key,role,entity_id,olympiad_id,text,created_at) VALUES(?,?,?,?,?,?)''',
        (f'{role}:{uid}:{key}', role, uid, oid, text[:3500], at))
    if cur.rowcount:
        for channel in channels:
            if channel != 'WEB':
                c.execute('INSERT OR IGNORE INTO olympiad_delivery_outbox(notice_id,channel,next_at) VALUES(?,?,?)',
                          (cur.lastrowid, channel, at))


def describe_date(event):
    def fmt(x):
        if not x:
            return ''
        if event['precision'] == 'DATE':
            return date.fromisoformat(x).strftime('%d.%m.%Y')
        return datetime.fromisoformat(x).astimezone(TZ).strftime('%d.%m.%Y %H:%M МСК')
    if event['status'] == 'CANCELLED':
        return 'Отменён'
    values = list(dict.fromkeys(filter(None, (fmt(event.get('start_at')), fmt(event.get('end_at'))))))
    return ' — '.join(values) or 'Дата не объявлена'


def save_event(oid, data, manual=False, checked=None, notify=True):
    ensure_schema()
    at = stamp(checked)
    v = validate_event(data)
    from web_backend.olympiad_sources import allowed_event_url
    c = database.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        item = catalog_item(c, oid)
        if not allowed_event_url(v['source_url'], item):
            raise ValueError('official_source_required')
        eid = hashlib.sha256(f"{oid}:{v['stage_key']}".encode()).hexdigest()[:24]
        oldrow = c.execute('SELECT * FROM olympiad_events WHERE id=?', (eid,)).fetchone()
        old = dict(oldrow) if oldrow else None
        if manual and old and data.get('expected_revision') != old['revision']:
            raise ValueError('stage_changed_reload')
        # A reviewed correction is never silently overwritten by an automatic parser.
        if old and old['manual'] and not manual:
            return {'status':'manual_preserved','id':eid}
        changed = old is None or any(old[k] != v[k] for k in v if k != 'evidence')
        revision = (old['revision'] + int(changed)) if old else 1
        c.execute('''INSERT INTO olympiad_events
          (id,olympiad_id,stage_key,title,kind,start_at,end_at,precision,status,format,source_url,evidence,checked_at,revision,manual)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
          title=excluded.title,kind=excluded.kind,start_at=excluded.start_at,end_at=excluded.end_at,
          precision=excluded.precision,status=excluded.status,format=excluded.format,
          source_url=excluded.source_url,evidence=excluded.evidence,checked_at=excluded.checked_at,
          revision=excluded.revision,manual=excluded.manual''',
          (eid, oid, v['stage_key'], v['title'], v['kind'], v['start_at'], v['end_at'], v['precision'],
           v['status'], v['format'], v['source_url'], v['evidence'], at, revision, int(manual)))
        if changed:
            c.execute('INSERT INTO olympiad_event_history(event_id,revision,before_json,after_json,created_at) VALUES(?,?,?,?,?)',
                      (eid,revision,json.dumps(old,ensure_ascii=False) if old else None,json.dumps(v,ensure_ascii=False),at))
            if notify:
                label = 'Расписание изменилось' if old else 'Опубликован этап'
                text = f"🏆 {item['title']} · {item['subject']}\n{label}: {v['title']}\n{describe_date(v)}"
                if old:
                    text += '\nРанее: ' + describe_date(old)
                if v['status'] == 'TENTATIVE':
                    text += '\nПредварительный график'
                text += '\n' + v['source_url']
                for s in c.execute('SELECT * FROM olympiad_subscriptions WHERE olympiad_id=?', (oid,)):
                    _notice(c,s['role'],s['entity_id'],oid,f'event:{eid}:{revision}',text,json.loads(s['channels_json']),at)
        c.commit()
        return {'status':'ok','id':eid,'changed':changed,'revision':revision}
    finally:
        c.close()


def subscribe(role, uid, oid, channels):
    if role not in {'teacher','student'} or not isinstance(channels,list) or any(x not in CHANNELS for x in channels):
        raise ValueError('invalid_channels')
    ensure_schema()
    c = database.connect()
    try:
        catalog_item(c, oid)
        if channels:
            c.execute('''INSERT INTO olympiad_subscriptions VALUES(?,?,?,?,?)
              ON CONFLICT(role,entity_id,olympiad_id) DO UPDATE SET channels_json=excluded.channels_json''',
              (role,int(uid),oid,json.dumps(sorted(set(channels)|{'WEB'})),stamp()))
        else:
            c.execute('DELETE FROM olympiad_subscriptions WHERE role=? AND entity_id=? AND olympiad_id=?',(role,int(uid),oid))
        c.commit()
        return {'status':'ok'}
    finally:
        c.close()


def recommend(uid, oid, note='', goal=False, remove=False):
    ensure_schema()
    note = str(note or '').strip()
    if len(note) > 1000:
        raise ValueError('note_too_long')
    c = database.connect()
    try:
        catalog_item(c,oid)
        if not c.execute('SELECT id FROM users WHERE id=? AND active=1',(int(uid),)).fetchone():
            raise ValueError('student_not_found')
        if remove:
            c.execute('DELETE FROM olympiad_recommendations WHERE user_id=? AND olympiad_id=?',(int(uid),oid))
        else:
            c.execute('''INSERT INTO olympiad_recommendations VALUES(?,?,?,?,?)
              ON CONFLICT(user_id,olympiad_id) DO UPDATE SET note=excluded.note,goal=excluded.goal''',
              (int(uid),oid,note,int(bool(goal)),stamp()))
        c.commit()
        return {'status':'ok'}
    finally:
        c.close()


def overview(role, uid, student_id=None):
    ensure_schema()
    c = database.connect()
    try:
        target = int(student_id) if role=='teacher' and student_id else int(uid) if role=='student' else None
        recs = {r['olympiad_id']:dict(r) for r in c.execute('SELECT * FROM olympiad_recommendations WHERE user_id=?',(target,))} if target else {}
        subs = {r['olympiad_id']:json.loads(r['channels_json']) for r in c.execute('SELECT * FROM olympiad_subscriptions WHERE role=? AND entity_id=?',(role,int(uid)))}
        items=[]
        for r in c.execute('SELECT * FROM olympiad_catalog WHERE season=? AND active=1 ORDER BY title,subject',(season(),)):
            x=dict(r)
            x['events']=[dict(e) for e in c.execute('SELECT * FROM olympiad_events WHERE olympiad_id=? ORDER BY COALESCE(start_at,end_at,\'9999\'),id',(x['id'],))]
            x['sources']=[dict(s) for s in c.execute('SELECT s.* FROM olympiad_sources s JOIN olympiad_source_links l ON l.url=s.url WHERE l.olympiad_id=?',(x['id'],))]
            x['channels']=subs.get(x['id'],[])
            x['recommendation']=recs.get(x['id'])
            items.append(x)
        notices=[dict(r) for r in c.execute('SELECT * FROM olympiad_notices WHERE role=? AND entity_id=? ORDER BY id DESC LIMIT 40',(role,int(uid)))]
        deliveries=[dict(r) for r in c.execute('''SELECT d.id,d.channel,d.status,d.attempts,d.last_error,n.created_at
          FROM olympiad_delivery_outbox d JOIN olympiad_notices n ON n.id=d.notice_id
          WHERE n.role=? AND n.entity_id=? ORDER BY d.id DESC LIMIT 40''',(role,int(uid)))]
        result={'items':items,'notices':notices,'deliveries':deliveries,'season':season(),'server_time':stamp(),'timezone':'Europe/Moscow'}
        registry=c.execute("SELECT checked_at,error FROM olympiad_sources WHERE url='https://rsr-olymp.ru/'").fetchone()
        result['registry_status']=dict(registry) if registry else None
        if role=='teacher':
            result['students']=[dict(r) for r in c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name')]
        return result
    finally:
        c.close()


def enqueue_reminders(current=None):
    ensure_schema()
    current = current or now()
    at=stamp(current)
    c=database.connect()
    count=0
    try:
        rows=c.execute('''SELECT e.*,o.title olympiad_title,s.role,s.entity_id,s.channels_json,s.created_at subscribed_at
          FROM olympiad_events e JOIN olympiad_catalog o ON o.id=e.olympiad_id
          JOIN olympiad_subscriptions s ON s.olympiad_id=e.olympiad_id
          WHERE e.status='CONFIRMED' AND o.season=? AND o.active=1
          AND NOT EXISTS(SELECT 1 FROM olympiad_sources src WHERE src.url=e.source_url
                         AND (src.error IS NOT NULL OR src.review_required=1))''',(season(current),)).fetchall()
        for row in rows:
            e=dict(row)
            if current-datetime.fromisoformat(e['checked_at'])>timedelta(days=3):
                continue
            for boundary in ('start_at','end_at'):
                value=e[boundary]
                if not value:
                    continue
                # Date-only reminders are at 09:00 Moscow; no invented event time.
                target=event_boundary(value,e['precision'])
                if e['precision']=='DATE':
                    target=target.replace(hour=9)
                if target<=current:
                    continue
                for days in (7,1):
                    due=target-timedelta(days=days)
                    if not (due<=current<due+timedelta(hours=12)):
                        continue
                    if datetime.fromisoformat(e['subscribed_at'])>due:
                        continue
                    label='Начало' if boundary=='start_at' else 'Окончание / крайний срок'
                    text=f"🏆 {e['olympiad_title']}\n{e['title']}\n{label} через {days} дн.\n{describe_date(e)}\n{e['source_url']}"
                    before=c.total_changes
                    _notice(c,e['role'],e['entity_id'],e['olympiad_id'],f"remind:{e['id']}:{e['revision']}:{boundary}:{days}",text,json.loads(e['channels_json']),at)
                    count+=int(c.total_changes>before)
        c.commit()
        return count
    finally:
        c.close()
