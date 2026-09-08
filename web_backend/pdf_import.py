"""PDF -> reviewable task-bank import pipeline.

Extraction is deliberately staged: extracted tasks/answers are never published
directly to students. Teacher reviews the parsed draft first, then commits it to
task_bank where answers remain private.

The extractor accepts already extracted PDF text. A deployment adapter may use
PyMuPDF/pdftotext for digital PDFs and OCR only as a fallback for scanned pages.
"""
import json
import re
from database import connect, now_iso
from web_backend.library import ensure_tables as ensure_library_tables, add_task


def ensure_tables():
    ensure_library_tables();conn=connect();conn.executescript("""
    CREATE TABLE IF NOT EXISTS pdf_import_jobs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,material_id INTEGER,collection_id INTEGER,
      source_filename TEXT,status TEXT NOT NULL DEFAULT 'DRAFT',page_count INTEGER,
      extraction_method TEXT,raw_text TEXT,created_at TEXT NOT NULL,updated_at TEXT,
      FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE SET NULL,
      FOREIGN KEY(collection_id) REFERENCES material_collections(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS pdf_import_items(
      id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER NOT NULL,source_order INTEGER NOT NULL,
      task_number TEXT,title TEXT,statement TEXT NOT NULL,answer TEXT,solution TEXT,page_number INTEGER,
      subject TEXT,grade INTEGER,study_goal TEXT,section TEXT,topic TEXT,difficulty INTEGER DEFAULT 2,
      confidence REAL DEFAULT 0,status TEXT NOT NULL DEFAULT 'DRAFT',task_bank_id INTEGER,created_at TEXT NOT NULL,updated_at TEXT,
      FOREIGN KEY(job_id) REFERENCES pdf_import_jobs(id) ON DELETE CASCADE,
      FOREIGN KEY(task_bank_id) REFERENCES task_bank(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_pdf_import_items_job ON pdf_import_items(job_id,status,source_order);
    """);conn.commit();conn.close()


def _split_answer_block(text):
    # Common Russian workbook headings. We keep answer text teacher-only.
    m=re.search(r'(?im)^\s*(ответы|ответ|ключи|ответы к заданиям)\s*[:.]?\s*$',text)
    return (text[:m.start()],text[m.end():]) if m else (text,'')


def _answers_map(block):
    out={}
    for line in block.splitlines():
        for n,a in re.findall(r'(\d+[а-яa-z]?)\s*[.)\-:]\s*([^;]+?)(?=\s+\d+[а-яa-z]?\s*[.)\-:]|$)',line.strip(),flags=re.I):
            out[n.lower()]=a.strip()
    return out


def parse_collection_text(text):
    """Conservative parser for numbered tasks. Returns drafts for teacher review."""
    body,answer_block=_split_answer_block(str(text or ''));answers=_answers_map(answer_block)
    pattern=re.compile(r'(?ms)^\s*(\d+[а-яa-z]?)\s*[.)]\s+(.+?)(?=^\s*\d+[а-яa-z]?\s*[.)]\s+|\Z)')
    items=[]
    for order,m in enumerate(pattern.finditer(body),1):
        number=m.group(1);statement=re.sub(r'\n{3,}','\n\n',m.group(2).strip())
        if len(statement)<4:continue
        items.append({'source_order':order,'task_number':number,'statement':statement,'answer':answers.get(number.lower()),'confidence':0.9 if number.lower() in answers else 0.7})
    return items


def create_import_draft(text,source_filename=None,material_id=None,collection_id=None,page_count=None,extraction_method='TEXT',defaults=None):
    ensure_tables();defaults=defaults or {};items=parse_collection_text(text);conn=connect();now=now_iso();cur=conn.execute("""INSERT INTO pdf_import_jobs(material_id,collection_id,source_filename,status,page_count,extraction_method,raw_text,created_at,updated_at) VALUES(?,?,?,'DRAFT',?,?,?,?,?)""",(int(material_id) if material_id else None,int(collection_id) if collection_id else None,source_filename,int(page_count) if page_count else None,str(extraction_method),str(text),now,now));job=int(cur.lastrowid)
    for x in items:
        conn.execute("""INSERT INTO pdf_import_items(job_id,source_order,task_number,statement,answer,subject,grade,study_goal,section,topic,difficulty,confidence,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'DRAFT',?,?)""",(job,x['source_order'],x['task_number'],x['statement'],x.get('answer'),defaults.get('subject'),defaults.get('grade'),defaults.get('study_goal'),defaults.get('section'),defaults.get('topic'),int(defaults.get('difficulty') or 2),x['confidence'],now,now))
    conn.commit();conn.close();return {'status':'ok','job_id':job,'items':len(items),'answers_found':sum(1 for x in items if x.get('answer'))}


def draft(job_id):
    ensure_tables();conn=connect();job=conn.execute("SELECT id,material_id,collection_id,source_filename,status,page_count,extraction_method,created_at FROM pdf_import_jobs WHERE id=?",(int(job_id),)).fetchone();rows=conn.execute("SELECT * FROM pdf_import_items WHERE job_id=? ORDER BY source_order",(int(job_id),)).fetchall();conn.close();return {'job':dict(job) if job else None,'items':[dict(r) for r in rows]}


def update_item(item_id,**fields):
    allowed={'task_number','title','statement','answer','solution','page_number','subject','grade','study_goal','section','topic','difficulty','status'};pairs=[];values=[]
    for k,v in fields.items():
        if k in allowed:pairs.append(k+'=?');values.append(v)
    if not pairs:return
    ensure_tables();conn=connect();pairs.append('updated_at=?');values.append(now_iso());values.append(int(item_id));conn.execute('UPDATE pdf_import_items SET '+','.join(pairs)+' WHERE id=?',values);conn.commit();conn.close()


def commit_job(job_id):
    """Publish reviewed drafts into task_bank. Answers remain teacher-only."""
    ensure_tables();conn=connect();job=conn.execute("SELECT * FROM pdf_import_jobs WHERE id=?",(int(job_id),)).fetchone()
    if not job:conn.close();return {'status':'not_found'}
    rows=conn.execute("SELECT * FROM pdf_import_items WHERE job_id=? AND status IN ('DRAFT','APPROVED') ORDER BY source_order",(int(job_id),)).fetchall();conn.close();created=[]
    for row in rows:
        if not row['statement'] or not row['subject']:continue
        tid=add_task(row['subject'],row['statement'],row['grade'],row['study_goal'],row['section'],row['topic'],job['collection_id'],job['source_filename'],row['task_number'],row['title'],row['answer'],row['solution'],row['difficulty'] or 2,['pdf-import'])
        created.append((int(row['id']),tid))
    conn=connect();now=now_iso()
    for iid,tid in created:conn.execute("UPDATE pdf_import_items SET status='IMPORTED',task_bank_id=?,updated_at=? WHERE id=?",(tid,now,iid))
    conn.execute("UPDATE pdf_import_jobs SET status='IMPORTED',updated_at=? WHERE id=?",(now,int(job_id)));conn.commit();conn.close();return {'status':'ok','created':len(created),'task_ids':[x[1] for x in created]}
