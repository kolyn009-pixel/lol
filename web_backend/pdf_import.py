"""PDF -> teacher-reviewed task-bank import pipeline.

Parsed answers never reach students directly. Every item must be explicitly
approved and valid before it can be published to task_bank.
"""
import re
from database import connect,now_iso
from web_backend.library import ensure_tables as ensure_library_tables,add_task
VALID_STATUSES={'DRAFT','APPROVED','REJECTED','IMPORTED'}

def ensure_tables():
 ensure_library_tables();conn=connect();conn.executescript("""CREATE TABLE IF NOT EXISTS pdf_import_jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,material_id INTEGER,collection_id INTEGER,source_filename TEXT,status TEXT NOT NULL DEFAULT 'DRAFT',page_count INTEGER,extraction_method TEXT,raw_text TEXT,created_at TEXT NOT NULL,updated_at TEXT);CREATE TABLE IF NOT EXISTS pdf_import_items(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER NOT NULL,source_order INTEGER NOT NULL,task_number TEXT,title TEXT,statement TEXT NOT NULL,answer TEXT,solution TEXT,page_number INTEGER,subject TEXT,grade INTEGER,study_goal TEXT,section TEXT,topic TEXT,difficulty INTEGER DEFAULT 2,confidence REAL DEFAULT 0,status TEXT NOT NULL DEFAULT 'DRAFT',task_bank_id INTEGER,created_at TEXT NOT NULL,updated_at TEXT);CREATE INDEX IF NOT EXISTS idx_pdf_import_items_job ON pdf_import_items(job_id,status,source_order);""");conn.commit();conn.close()
def _split_answer_block(text):
 m=re.search(r'(?im)^\s*(ответы|ответ|ключи|ответы к заданиям)\s*[:.]?\s*$',text);return(text[:m.start()],text[m.end():]) if m else(text,'')
def _answers_map(block):
 out={}
 for line in block.splitlines():
  for n,a in re.findall(r'(\d+[а-яa-z]?)\s*[.)\-:]\s*([^;]+?)(?=\s+\d+[а-яa-z]?\s*[.)\-:]|$)',line.strip(),flags=re.I):out[n.lower()]=a.strip()
 return out
def _page_for(text,pos):
 page=1
 for m in re.finditer(r'(?m)^\[\[PAGE\s+(\d+)\]\]\s*$',text[:pos]):page=int(m.group(1))
 return page
def parse_collection_text(text):
 raw=str(text or '');body,answer_block=_split_answer_block(raw);answers=_answers_map(answer_block);pattern=re.compile(r'(?ms)^\s*(\d+[а-яa-z]?)\s*[.)]\s+(.+?)(?=^\s*\d+[а-яa-z]?\s*[.)]\s+|\Z)');items=[]
 for order,m in enumerate(pattern.finditer(body),1):
  number=m.group(1);statement=re.sub(r'(?m)^\s*\[\[PAGE\s+\d+\]\]\s*$','',m.group(2));statement=re.sub(r'\n{3,}','\n\n',statement).strip()
  if len(statement)>=4:items.append({'source_order':order,'task_number':number,'statement':statement,'answer':answers.get(number.lower()),'page_number':_page_for(body,m.start()),'confidence':0.9 if number.lower() in answers else 0.7})
 return items
def create_import_draft(text,source_filename=None,material_id=None,collection_id=None,page_count=None,extraction_method='TEXT',defaults=None):
 ensure_tables();defaults=defaults or {};items=parse_collection_text(text);conn=connect();now=now_iso();cur=conn.execute("INSERT INTO pdf_import_jobs(material_id,collection_id,source_filename,status,page_count,extraction_method,raw_text,created_at,updated_at) VALUES(?,?,?,'DRAFT',?,?,?,?,?)",(int(material_id) if material_id else None,int(collection_id) if collection_id else None,source_filename,int(page_count) if page_count else None,str(extraction_method),str(text),now,now));job=int(cur.lastrowid)
 for x in items:conn.execute("INSERT INTO pdf_import_items(job_id,source_order,task_number,statement,answer,page_number,subject,grade,study_goal,section,topic,difficulty,confidence,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'DRAFT',?,?)",(job,x['source_order'],x['task_number'],x['statement'],x.get('answer'),x.get('page_number'),defaults.get('subject'),defaults.get('grade'),defaults.get('study_goal'),defaults.get('section'),defaults.get('topic'),int(defaults.get('difficulty') or 2),x['confidence'],now,now))
 conn.commit();conn.close();return {'status':'ok','job_id':job,'items':len(items),'answers_found':sum(1 for x in items if x.get('answer'))}
def draft(job_id):
 ensure_tables();conn=connect();job=conn.execute('SELECT id,material_id,collection_id,source_filename,status,page_count,extraction_method,created_at FROM pdf_import_jobs WHERE id=?',(int(job_id),)).fetchone();rows=conn.execute('SELECT * FROM pdf_import_items WHERE job_id=? ORDER BY source_order',(int(job_id),)).fetchall();conn.close();return {'job':dict(job) if job else None,'items':[dict(r) for r in rows]}
def update_item(item_id,**fields):
 allowed={'task_number','title','statement','answer','solution','page_number','subject','grade','study_goal','section','topic','difficulty','status'};pairs=[];values=[]
 for k,v in fields.items():
  if k not in allowed:continue
  if k=='status':
   v=str(v).upper()
   if v not in VALID_STATUSES:raise ValueError('invalid_status')
  if k=='grade' and v not in (None,''):
   v=int(v)
   if not 1<=v<=11:raise ValueError('invalid_grade')
  if k=='difficulty' and v not in (None,''):
   v=int(v)
   if not 1<=v<=5:raise ValueError('invalid_difficulty')
  if k=='statement' and not str(v or '').strip():raise ValueError('statement_required')
  pairs.append(k+'=?');values.append(v)
 if not pairs:return
 ensure_tables();conn=connect();pairs.append('updated_at=?');values.extend([now_iso(),int(item_id)]);cur=conn.execute('UPDATE pdf_import_items SET '+','.join(pairs)+' WHERE id=?',values);conn.commit();conn.close()
 if cur.rowcount!=1:raise ValueError('item_not_found')
def approve_item(item_id,approved=True):
 if approved:
  ensure_tables();conn=connect();row=conn.execute('SELECT statement,subject FROM pdf_import_items WHERE id=?',(int(item_id),)).fetchone();conn.close()
  if not row:raise ValueError('item_not_found')
  if not str(row['statement'] or '').strip():raise ValueError('statement_required')
  if not str(row['subject'] or '').strip():raise ValueError('subject_required')
 update_item(item_id,status='APPROVED' if approved else 'REJECTED');return {'status':'ok','item_id':int(item_id),'approved':bool(approved)}
def commit_job(job_id):
 ensure_tables();job_id=int(job_id);conn=connect();job=conn.execute('SELECT * FROM pdf_import_jobs WHERE id=?',(job_id,)).fetchone()
 if not job:conn.close();return {'status':'not_found'}
 rows=conn.execute("SELECT * FROM pdf_import_items WHERE job_id=? AND status='APPROVED' ORDER BY source_order",(job_id,)).fetchall()
 if not rows:
  imported=conn.execute("SELECT task_bank_id FROM pdf_import_items WHERE job_id=? AND status='IMPORTED' AND task_bank_id IS NOT NULL ORDER BY source_order",(job_id,)).fetchall();conn.close()
  if imported:return {'status':'ok','created':0,'task_ids':[int(r['task_bank_id']) for r in imported],'already_imported':True}
  return {'status':'nothing_approved','created':0,'task_ids':[],'already_imported':False}
 conn.close();invalid=[int(r['id']) for r in rows if not str(r['statement'] or '').strip() or not str(r['subject'] or '').strip()]
 if invalid:return {'status':'invalid_approved_items','item_ids':invalid,'created':0,'task_ids':[]}
 created=[]
 for row in rows:
  tid=add_task(row['subject'],row['statement'],row['grade'],row['study_goal'],row['section'],row['topic'],job['collection_id'],job['source_filename'],row['task_number'],row['title'],row['answer'],row['solution'],row['difficulty'] or 2,['pdf-import']);created.append((int(row['id']),tid))
 conn=connect();now=now_iso()
 for iid,tid in created:conn.execute("UPDATE pdf_import_items SET status='IMPORTED',task_bank_id=?,updated_at=? WHERE id=? AND status='APPROVED'",(tid,now,iid))
 remaining=conn.execute("SELECT COUNT(*) FROM pdf_import_items WHERE job_id=? AND status IN ('DRAFT','APPROVED')",(job_id,)).fetchone()[0];conn.execute('UPDATE pdf_import_jobs SET status=?,updated_at=? WHERE id=?',('IMPORTED' if not remaining else 'REVIEW',now,job_id));conn.commit();conn.close();return {'status':'ok','created':len(created),'task_ids':[x[1] for x in created],'already_imported':False}
