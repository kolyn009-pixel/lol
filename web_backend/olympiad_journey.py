"""Student-scoped olympiad preparation, linked resources and self/teacher results."""
from datetime import date
import json
from urllib.parse import urlparse
import database
from web_backend import olympiad_store as store

STEPS=('prepare','registered','qualifier','final')
AWARDS={'PARTICIPANT','PRIZE','WINNER'}

def ensure_schema():
    store.ensure_schema();c=database.connect()
    try:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS olympiad_journeys(
          user_id INTEGER NOT NULL,olympiad_id TEXT NOT NULL,steps_json TEXT NOT NULL,
          note TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL,PRIMARY KEY(user_id,olympiad_id));
        CREATE TABLE IF NOT EXISTS olympiad_resources(
          id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,olympiad_id TEXT NOT NULL,
          kind TEXT NOT NULL,title TEXT NOT NULL,url TEXT,reference_id INTEGER,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_olympiad_resources_owner ON olympiad_resources(user_id,olympiad_id);
        CREATE TABLE IF NOT EXISTS olympiad_results(
          id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,olympiad_id TEXT NOT NULL,
          stage TEXT NOT NULL,score REAL,total REAL,award TEXT NOT NULL,certificate_url TEXT,
          note TEXT NOT NULL,verified INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,
          UNIQUE(user_id,olympiad_id,stage));
        ''');c.commit()
    finally:c.close()


def user(c,uid):
    if not c.execute('SELECT id FROM users WHERE id=?',(int(uid),)).fetchone():raise ValueError('student_not_found')


def text(value,maximum,required=False):
    value=str(value or '').strip()
    if len(value)>maximum or required and not value:raise ValueError('invalid_text')
    return value


def https(value):
    value=text(value,2000)
    if not value:return ''
    p=urlparse(value)
    if p.scheme!='https' or not p.hostname or p.username or p.password:raise ValueError('https_url_required')
    return value


def save_progress(uid,oid,data):
    ensure_schema();steps=data.get('steps',[])
    if not isinstance(steps,list) or any(x not in STEPS for x in steps):raise ValueError('invalid_steps')
    c=database.connect()
    try:
        user(c,uid);store.catalog_item(c,oid)
        c.execute('''INSERT INTO olympiad_journeys VALUES(?,?,?,?,?) ON CONFLICT(user_id,olympiad_id)
          DO UPDATE SET steps_json=excluded.steps_json,note=excluded.note,updated_at=excluded.updated_at''',
          (int(uid),oid,json.dumps(sorted(set(steps))),text(data.get('note'),1000),store.stamp()));c.commit()
        return {'status':'ok'}
    finally:c.close()


def save_resource(uid,oid,data):
    ensure_schema();c=database.connect()
    try:
        user(c,uid);item=store.catalog_item(c,oid)
        if data.get('remove_id'):
            c.execute('DELETE FROM olympiad_resources WHERE id=? AND user_id=? AND olympiad_id=?',(int(data['remove_id']),int(uid),oid));c.commit();return {'status':'ok'}
        kind=data.get('kind');title=text(data.get('title'),180);url=None;ref=None
        if kind=='LINK':url=https(data.get('url'));title=text(title,180,True)
        elif kind=='FORMULA':
            ref=int(data['reference_id'])
            row=c.execute('SELECT title FROM formula_book WHERE id=? AND subject=? AND active=1',(ref,item['subject'])).fetchone()
            if not row:raise ValueError('formula_not_found')
            title=row['title']
        elif kind=='HOMEWORK':
            ref=int(data['reference_id']);row=c.execute('SELECT title FROM homework WHERE id=? AND user_id=?',(ref,int(uid))).fetchone()
            if not row:raise ValueError('homework_not_assigned_to_student')
            title=row['title']
        else:raise ValueError('invalid_resource')
        if kind=='LINK' and not url:raise ValueError('https_url_required')
        if c.execute('SELECT COUNT(*) FROM olympiad_resources WHERE user_id=? AND olympiad_id=?',(int(uid),oid)).fetchone()[0]>=100:raise ValueError('too_many_resources')
        cur=c.execute('INSERT INTO olympiad_resources(user_id,olympiad_id,kind,title,url,reference_id,created_at) VALUES(?,?,?,?,?,?,?)',
          (int(uid),oid,kind,title,url,ref,store.stamp()));c.commit();return {'status':'ok','id':cur.lastrowid}
    finally:c.close()


def save_result(uid,oid,data,teacher=False):
    ensure_schema();stage=text(data.get('stage'),100,True);award=data.get('award','PARTICIPANT')
    if award not in AWARDS:raise ValueError('invalid_award')
    def number(value):
        if value in (None,''):return None
        n=float(value)
        if not 0<=n<=1000000:raise ValueError('invalid_score')
        return n
    score=number(data.get('score'));total=number(data.get('total'))
    if total is not None and (total<=0 or score is not None and score>total):raise ValueError('invalid_score')
    c=database.connect()
    try:
        user(c,uid);store.catalog_item(c,oid)
        c.execute('''INSERT INTO olympiad_results(user_id,olympiad_id,stage,score,total,award,certificate_url,note,verified,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,olympiad_id,stage) DO UPDATE SET
          score=excluded.score,total=excluded.total,award=excluded.award,certificate_url=excluded.certificate_url,
          note=excluded.note,verified=excluded.verified,updated_at=excluded.updated_at''',
          (int(uid),oid,stage,score,total,award,https(data.get('certificate_url')),text(data.get('note'),1000),int(teacher and bool(data.get('verified'))),store.stamp()))
        c.commit();return {'status':'ok'}
    finally:c.close()


def overview(uid,oid=None):
    ensure_schema();c=database.connect()
    try:
        user(c,uid)
        results=[dict(r) for r in c.execute('''SELECT r.*,o.title olympiad_title,o.subject,o.season FROM olympiad_results r
          JOIN olympiad_catalog o ON o.id=r.olympiad_id WHERE r.user_id=? ORDER BY o.season DESC,r.updated_at DESC''',(int(uid),))]
        out={'results':results}
        if not oid:return out
        item=store.catalog_item(c,oid);row=c.execute('SELECT * FROM olympiad_journeys WHERE user_id=? AND olympiad_id=?',(int(uid),oid)).fetchone()
        out['progress']={**dict(row),'steps':json.loads(row['steps_json'])} if row else {'steps':[],'note':''}
        resources=[]
        for row in c.execute('SELECT * FROM olympiad_resources WHERE user_id=? AND olympiad_id=? ORDER BY id',(int(uid),oid)):
            x=dict(row)
            if x['kind']=='FORMULA':
                # Re-check visibility at read time: deactivated formulas disappear.
                tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                formula=c.execute('SELECT title,formula_plain,formula_latex,description FROM formula_book WHERE id=? AND active=1 AND subject=?',(x['reference_id'],item['subject'])).fetchone() if 'formula_book' in tables else None
                if not formula:continue
                x['formula']=dict(formula)
            if x['kind']=='HOMEWORK':
                row=c.execute('SELECT title,status,deadline FROM homework WHERE id=? AND user_id=?',(x['reference_id'],int(uid))).fetchone()
                if not row:continue
                x['homework']=dict(row)
            resources.append(x)
        out['resources']=resources
        return out
    finally:c.close()
