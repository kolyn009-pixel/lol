"""Teacher-reviewed import of formulas from files.

Supported inputs: JSON, CSV, TXT/MD, DOCX and PDF. Imported content is staged
first and never published to formula_book until the teacher approves it.
"""
from __future__ import annotations
import csv, io, json, os, re, tempfile, zipfile
from xml.etree import ElementTree as ET
from database import connect, now_iso
from web_backend.formula_book import ensure_tables as ensure_formula_tables, create_formula
from web_backend.pdf_storage import extract_pdf_text

MAX_IMPORT_BYTES=int(os.getenv('ADELIA_FORMULA_IMPORT_MAX_BYTES',str(80*1024*1024)))
SUPPORTED={'.json','.csv','.txt','.md','.docx','.pdf'}
SCOPE_FIELDS=('education_level','course_min','course_max')


def ensure_tables():
    ensure_formula_tables();conn=connect();conn.executescript("""
    CREATE TABLE IF NOT EXISTS formula_import_jobs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      filename TEXT NOT NULL,
      file_type TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'DRAFT',
      source_text TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS formula_import_items(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      job_id INTEGER NOT NULL,
      source_order INTEGER NOT NULL,
      subject TEXT,
      section TEXT,
      topic TEXT,
      title TEXT,
      formula_latex TEXT,
      formula_plain TEXT,
      description TEXT,
      variables_json TEXT NOT NULL DEFAULT '[]',
      conditions TEXT,
      units TEXT,
      derivation TEXT,
      example TEXT,
      exam_note TEXT,
      grade_min INTEGER,
      grade_max INTEGER,
      education_level TEXT NOT NULL DEFAULT 'ALL',
      course_min INTEGER,
      course_max INTEGER,
      study_goal TEXT,
      tags_json TEXT NOT NULL DEFAULT '[]',
      confidence REAL NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'DRAFT',
      formula_id INTEGER,
      created_at TEXT NOT NULL,
      updated_at TEXT,
      FOREIGN KEY(job_id) REFERENCES formula_import_jobs(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_formula_import_job ON formula_import_items(job_id,status,source_order);
    """)
    cols={r['name'] for r in conn.execute('PRAGMA table_info(formula_import_items)').fetchall()}
    if 'education_level' not in cols:conn.execute("ALTER TABLE formula_import_items ADD COLUMN education_level TEXT NOT NULL DEFAULT 'ALL'")
    if 'course_min' not in cols:conn.execute('ALTER TABLE formula_import_items ADD COLUMN course_min INTEGER')
    if 'course_max' not in cols:conn.execute('ALTER TABLE formula_import_items ADD COLUMN course_max INTEGER')
    conn.commit();conn.close()


def _decode(data):
    for enc in ('utf-8-sig','utf-8','cp1251'):
        try:return data.decode(enc)
        except Exception:pass
    raise ValueError('unsupported_text_encoding')


def _docx_text(data):
    try:z=zipfile.ZipFile(io.BytesIO(data));raw=z.read('word/document.xml')
    except Exception:raise ValueError('invalid_docx')
    root=ET.fromstring(raw);ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}';out=[]
    for p in root.iter(ns+'p'):
        text=''.join((t.text or '') for t in p.iter(ns+'t')).strip()
        if text:out.append(text)
    return '\n'.join(out)


def _pdf_text(data):
    fd,path=tempfile.mkstemp(suffix='.pdf');os.close(fd)
    try:
        with open(path,'wb') as f:f.write(data)
        r=extract_pdf_text(path)
        if r['status']=='OCR_REQUIRED':raise ValueError('ocr_required')
        if r['status']!='OK':raise ValueError(str(r['status']).lower())
        return r['text']
    finally:
        try:os.unlink(path)
        except Exception:pass


def _int_or_none(v):
    if v in (None,''):return None
    return int(v)


def _clean_obj(obj,defaults=None):
    d={**(defaults or {}),**(obj or {})};vars_=d.get('variables_json',d.get('variables',[]));tags=d.get('tags_json',d.get('tags',[]))
    if isinstance(vars_,str):
        try:vars_=json.loads(vars_)
        except Exception:vars_=[x.strip() for x in vars_.split(';') if x.strip()]
    if isinstance(tags,str):
        try:tags=json.loads(tags)
        except Exception:tags=[x.strip() for x in tags.split(',') if x.strip()]
    level=str(d.get('education_level') or 'ALL').upper()
    if level not in {'ALL','SCHOOL','COLLEGE'}:level='ALL'
    out={
      'subject':str(d.get('subject') or '').upper() or None,'section':d.get('section'),'topic':d.get('topic'),'title':d.get('title'),
      'formula_latex':d.get('formula_latex') or d.get('latex') or d.get('formula'),'formula_plain':d.get('formula_plain') or d.get('plain'),
      'description':d.get('description'),'variables_json':json.dumps(vars_ or [],ensure_ascii=False),'conditions':d.get('conditions'),'units':d.get('units'),
      'derivation':d.get('derivation'),'example':d.get('example'),'exam_note':d.get('exam_note'),'grade_min':_int_or_none(d.get('grade_min')),
      'grade_max':_int_or_none(d.get('grade_max')),'education_level':level,'course_min':_int_or_none(d.get('course_min')),
      'course_max':_int_or_none(d.get('course_max')),'study_goal':d.get('study_goal'),'tags_json':json.dumps(tags or [],ensure_ascii=False)
    }
    if level=='SCHOOL':out['course_min']=out['course_max']=None
    if level=='COLLEGE':out['grade_min']=out['grade_max']=None
    return out


def _structured_json(text,defaults):
    raw=json.loads(text);rows=raw if isinstance(raw,list) else raw.get('formulas',[]) if isinstance(raw,dict) else []
    return [_clean_obj(x,defaults) for x in rows if isinstance(x,dict)]


def _structured_csv(text,defaults):return [_clean_obj(dict(r),defaults) for r in csv.DictReader(io.StringIO(text))]


def _text_candidates(text,defaults):
    items=[];section=defaults.get('section');topic=defaults.get('topic')
    for line in text.splitlines():
        s=line.strip()
        if not s:continue
        if s.startswith('#'):
            head=s.lstrip('#').strip()
            if s.startswith('##'):topic=head
            else:section=head
            continue
        m=re.match(r'^(?:(.+?)\s*[:—-]\s*)?([^=]{1,60}=.+)$',s)
        if not m:continue
        title=(m.group(1) or '').strip() or 'Формула';formula=m.group(2).strip();items.append(_clean_obj({'title':title,'formula_latex':formula,'formula_plain':formula,'section':section,'topic':topic},defaults))
    return items


def parse_file(data,filename,defaults=None):
    if not isinstance(data,(bytes,bytearray)) or not data:raise ValueError('empty_file')
    if len(data)>MAX_IMPORT_BYTES:raise ValueError('file_too_large')
    ext=os.path.splitext(str(filename or ''))[1].lower()
    if ext not in SUPPORTED:raise ValueError('unsupported_file_type')
    if ext=='.docx':text=_docx_text(bytes(data));items=_text_candidates(text,defaults or {})
    elif ext=='.pdf':text=_pdf_text(bytes(data));items=_text_candidates(text,defaults or {})
    else:
        text=_decode(bytes(data))
        if ext=='.json':items=_structured_json(text,defaults or {})
        elif ext=='.csv':items=_structured_csv(text,defaults or {})
        else:items=_text_candidates(text,defaults or {})
    return {'file_type':ext[1:].upper(),'text':text,'items':items}


def create_draft(data,filename,defaults=None):
    ensure_tables();parsed=parse_file(data,filename,defaults);now=now_iso();conn=connect();cur=conn.execute("INSERT INTO formula_import_jobs(filename,file_type,status,source_text,created_at,updated_at) VALUES(?,?,'DRAFT',?,?,?)",(str(filename),parsed['file_type'],parsed['text'][:2_000_000],now,now));jid=int(cur.lastrowid)
    sql="""INSERT INTO formula_import_items(job_id,source_order,subject,section,topic,title,formula_latex,formula_plain,description,variables_json,conditions,units,derivation,example,exam_note,grade_min,grade_max,education_level,course_min,course_max,study_goal,tags_json,confidence,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'DRAFT',?,?)"""
    for n,item in enumerate(parsed['items'],1):
        confidence=0.95 if parsed['file_type'] in {'JSON','CSV'} else 0.6
        conn.execute(sql,(jid,n,item['subject'],item['section'],item['topic'],item['title'],item['formula_latex'],item['formula_plain'],item['description'],item['variables_json'],item['conditions'],item['units'],item['derivation'],item['example'],item['exam_note'],item['grade_min'],item['grade_max'],item['education_level'],item['course_min'],item['course_max'],item['study_goal'],item['tags_json'],confidence,now,now))
    conn.commit();conn.close();return {'status':'ok','job_id':jid,'items':len(parsed['items']),'file_type':parsed['file_type']}


def draft(job_id):
    ensure_tables();conn=connect();job=conn.execute('SELECT id,filename,file_type,status,created_at FROM formula_import_jobs WHERE id=?',(int(job_id),)).fetchone();items=conn.execute('SELECT * FROM formula_import_items WHERE job_id=? ORDER BY source_order',(int(job_id),)).fetchall();conn.close();return {'job':dict(job) if job else None,'items':[dict(x) for x in items]}


def update_item(item_id,fields):
    allowed={'subject','section','topic','title','formula_latex','formula_plain','description','variables_json','conditions','units','derivation','example','exam_note','grade_min','grade_max','education_level','course_min','course_max','study_goal','tags_json','status'};pairs=[];vals=[]
    for k,v in (fields or {}).items():
        if k not in allowed:continue
        if k=='status':
            v=str(v).upper()
            if v not in {'DRAFT','APPROVED','REJECTED','IMPORTED'}:raise ValueError('invalid_status')
        if k in {'grade_min','grade_max','course_min','course_max'} and v not in (None,''):v=int(v)
        if k=='education_level':
            v=str(v or 'ALL').upper()
            if v not in {'ALL','SCHOOL','COLLEGE'}:raise ValueError('invalid_education_level')
        if k in {'variables_json','tags_json'} and not isinstance(v,str):v=json.dumps(v or [],ensure_ascii=False)
        pairs.append(k+'=?');vals.append(v)
    if not pairs:return {'status':'ok','changed':0}
    pairs.append('updated_at=?');vals.extend([now_iso(),int(item_id)]);conn=connect();cur=conn.execute('UPDATE formula_import_items SET '+','.join(pairs)+' WHERE id=?',vals);conn.commit();conn.close();return {'status':'ok','changed':int(cur.rowcount)}


def approve_item(item_id,value=True):
    ensure_tables();conn=connect();r=conn.execute('SELECT title,formula_latex,subject,education_level,course_min,course_max FROM formula_import_items WHERE id=?',(int(item_id),)).fetchone();conn.close()
    if not r:raise ValueError('item_not_found')
    if value and (not str(r['title'] or '').strip() or not str(r['formula_latex'] or '').strip() or not str(r['subject'] or '').strip()):raise ValueError('required_fields_missing')
    if value and str(r['education_level'] or 'ALL').upper()=='COLLEGE' and str(r['subject'] or '').upper()=='PHYSICS' and ((r['course_min'] is not None and int(r['course_min'])>2) or (r['course_max'] is not None and int(r['course_max'])>2)):raise ValueError('physics_college_course_out_of_range')
    return update_item(item_id,{'status':'APPROVED' if value else 'REJECTED'})


def commit(job_id):
    ensure_tables();jid=int(job_id);conn=connect();rows=conn.execute("SELECT * FROM formula_import_items WHERE job_id=? AND status='APPROVED' ORDER BY source_order",(jid,)).fetchall()
    if not rows:
        old=conn.execute("SELECT formula_id FROM formula_import_items WHERE job_id=? AND status='IMPORTED' AND formula_id IS NOT NULL ORDER BY source_order",(jid,)).fetchall();conn.close();return {'status':'ok','created':0,'formula_ids':[int(x['formula_id']) for x in old],'already_imported':bool(old)} if old else {'status':'nothing_approved','created':0,'formula_ids':[]}
    conn.close();made=[]
    for r in rows:
        fields={k:r[k] for k in ('subject','section','topic','title','formula_latex','formula_plain','description','variables_json','conditions','units','derivation','example','exam_note','grade_min','grade_max','education_level','course_min','course_max','study_goal','tags_json')};out=create_formula(fields);made.append((int(r['id']),int(out['id'])))
    conn=connect();now=now_iso()
    for iid,fid in made:conn.execute("UPDATE formula_import_items SET status='IMPORTED',formula_id=?,updated_at=? WHERE id=? AND status='APPROVED'",(fid,now,iid))
    left=conn.execute("SELECT COUNT(*) FROM formula_import_items WHERE job_id=? AND status IN ('DRAFT','APPROVED')",(jid,)).fetchone()[0];conn.execute('UPDATE formula_import_jobs SET status=?,updated_at=? WHERE id=?',('IMPORTED' if not left else 'REVIEW',now,jid));conn.commit();conn.close();return {'status':'ok','created':len(made),'formula_ids':[x[1] for x in made],'already_imported':False}
