"""Private append-only scene journal; user reports are not test scores."""
from datetime import timedelta
import json
from uuid import UUID
from database import connect
from learning.language_program import RESOURCES
from web_backend import self_study_practice as practice


def ensure_schema():
    practice.ensure_schema();conn=connect()
    try:
        conn.executescript('''CREATE TABLE IF NOT EXISTS personal_study_scenes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,owner_id INTEGER NOT NULL,request_id TEXT NOT NULL,
          resource_id TEXT NOT NULL,language TEXT NOT NULL,season INTEGER NOT NULL,episode INTEGER NOT NULL,
          start_seconds INTEGER NOT NULL,end_seconds INTEGER NOT NULL,summary TEXT NOT NULL,
          comprehension TEXT NOT NULL,phrases TEXT NOT NULL,created_at TEXT NOT NULL,
          UNIQUE(owner_id,request_id));
          CREATE INDEX IF NOT EXISTS idx_personal_scenes ON personal_study_scenes(owner_id,language,id);''')
        conn.commit()
    finally:conn.close()


def resource(resource_id):
    item=next((x for x in RESOURCES if x['id']==resource_id and x.get('study_tasks')),None)
    if not item:raise ValueError('invalid_scene')
    return item


def validate(data):
    item=resource(data.get('resource_id'))
    for key in ('season','episode'):
        if type(data.get(key)) is not int or not 1<=data[key]<=999:raise ValueError('invalid_scene')
    start,end=data.get('start_seconds'),data.get('end_seconds')
    if type(start) is not int or type(end) is not int or start<0 or not start<end<=86400 or end-start>900:
        raise ValueError('invalid_scene_time')
    summary=data.get('summary','')
    if not isinstance(summary,str) or len(summary)>1500:raise ValueError('invalid_scene')
    comprehension=data.get('comprehension')
    if comprehension not in ('little','gist','details'):raise ValueError('invalid_scene')
    phrases=data.get('phrases',[])
    if not isinstance(phrases,list) or len(phrases)>3:raise ValueError('invalid_scene_phrases')
    clean=[]
    for p in phrases:
        if not isinstance(p,dict):raise ValueError('invalid_scene_phrases')
        front,back=p.get('expression'),p.get('meaning')
        if any(not isinstance(s,str) or not s.strip() or len(s)>200 for s in (front,back)):
            raise ValueError('invalid_scene_phrases')
        if front.strip().casefold() in {x['expression'].casefold() for x in clean}:raise ValueError('invalid_scene_phrases')
        clean.append({'expression':front.strip(),'meaning':back.strip()})
    req=data.get('request_id')
    try:UUID(req)
    except (ValueError,TypeError,AttributeError):raise ValueError('invalid_request_id') from None
    return item,{'resource_id':item['id'],'season':data['season'],'episode':data['episode'],
                 'start_seconds':start,'end_seconds':end,'summary':summary.strip(),
                 'comprehension':comprehension,'phrases':clean},req


def _record(row):
    item=dict(row);item.pop('owner_id',None);item.pop('request_id',None)
    item['phrases']=json.loads(item['phrases']);return item


def list_scenes(owner,language):
    practice._lang(language);ensure_schema();conn=connect()
    try:return {'items':[_record(r) for r in conn.execute('SELECT * FROM personal_study_scenes WHERE owner_id=? AND language=? ORDER BY id DESC LIMIT 100',(owner,language))],
                'note':'Понимание — твоя самооценка. Записи просмотра не повышают результат контрольных работ.'}
    finally:conn.close()


def get_scene(owner,scene_id):
    ensure_schema();conn=connect()
    try:
        row=conn.execute('SELECT * FROM personal_study_scenes WHERE owner_id=? AND id=?',(owner,scene_id)).fetchone()
        if not row:raise ValueError('scene_not_found')
        return _record(row)
    finally:conn.close()


def save_scene(owner,data):
    item,clean,req=validate(data);ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        old=conn.execute('SELECT * FROM personal_study_scenes WHERE owner_id=? AND request_id=?',(owner,req)).fetchone()
        if old:
            record=_record(old)
            if any(record[k]!=v for k,v in clean.items()):raise ValueError('request_conflict')
            return {'status':'saved','scene':record}
        cursor=conn.execute('''INSERT INTO personal_study_scenes
          (owner_id,request_id,resource_id,language,season,episode,start_seconds,end_seconds,summary,comprehension,phrases,created_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(owner,req,item['id'],item['language'],clean['season'],clean['episode'],
          clean['start_seconds'],clean['end_seconds'],clean['summary'],clean['comprehension'],json.dumps(clean['phrases'],ensure_ascii=False),practice.stamp()))
        sid=cursor.lastrowid;due=(practice.clock()+timedelta(days=1)).isoformat(timespec='seconds')
        for i,p in enumerate(clean['phrases']):
            conn.execute('''INSERT INTO personal_study_cards
              (owner_id,language,lesson_id,source,source_key,prompt,answer,explanation,due_at)
              VALUES(?,?,?,'scene',?,?,?,?,?)''',(owner,item['language'],'scene:'+str(sid),str(i),p['meaning'],p['expression'],
              'Выражение и перевод добавлены тобой из сцены. Их точность автоматически не проверена.',due))
        row=conn.execute('SELECT * FROM personal_study_scenes WHERE id=?',(sid,)).fetchone()
        conn.commit();return {'status':'saved','scene':_record(row)}
    except Exception:conn.rollback();raise
    finally:conn.close()
