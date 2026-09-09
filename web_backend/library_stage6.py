"""Stage 6 teacher library management for materials, collections, tasks and PDF imports."""
from __future__ import annotations
import json
from database import connect, now_iso
from web_backend.library import ensure_tables as ensure_library_tables
from web_backend.pdf_import import ensure_tables as ensure_pdf_tables


def ensure_tables():
    ensure_library_tables();ensure_pdf_tables()


def overview(search=None,subject=None,limit=300):
    ensure_tables();q=str(search or '').strip().lower();subject=str(subject or '').strip().upper() or None;conn=connect();params=[];where=['m.active=1']
    if subject:where.append('m.subject=?');params.append(subject)
    if q:
        like='%'+q+'%';where.append("(LOWER(m.title) LIKE ? OR LOWER(COALESCE(m.description,'')) LIKE ? OR LOWER(COALESCE(m.tags_json,'')) LIKE ?)");params += [like,like,like]
    materials=conn.execute(f"SELECT m.*, (SELECT COUNT(*) FROM homework_material_links h WHERE h.material_id=m.id) homework_uses,(SELECT COUNT(*) FROM material_access a WHERE a.material_id=m.id) grants FROM materials m WHERE {' AND '.join(where)} ORDER BY m.updated_at DESC,m.id DESC LIMIT ?",(*params,int(limit))).fetchall()
    cp=[];cw=['c.active=1']
    if subject:cw.append('c.subject=?');cp.append(subject)
    if q:cw.append("(LOWER(c.title) LIKE ? OR LOWER(COALESCE(c.description,'')) LIKE ?)");cp += ['%'+q+'%','%'+q+'%']
    collections=conn.execute(f"SELECT c.*, (SELECT COUNT(*) FROM collection_materials cm WHERE cm.collection_id=c.id) material_count,(SELECT COUNT(*) FROM task_bank t WHERE t.collection_id=c.id AND t.active=1) task_count FROM material_collections c WHERE {' AND '.join(cw)} ORDER BY c.updated_at DESC,c.id DESC LIMIT ?",(*cp,int(limit))).fetchall()
    tp=[];tw=['t.active=1']
    if subject:tw.append('t.subject=?');tp.append(subject)
    if q:
        like='%'+q+'%';tw.append("(LOWER(COALESCE(t.title,'')) LIKE ? OR LOWER(t.statement) LIKE ? OR LOWER(COALESCE(t.topic,'')) LIKE ? OR LOWER(COALESCE(t.source_label,'')) LIKE ?)");tp += [like,like,like,like]
    tasks=conn.execute(f"SELECT t.*,c.title collection_title,(SELECT COUNT(*) FROM homework_task_links h WHERE h.task_id=t.id) homework_uses FROM task_bank t LEFT JOIN material_collections c ON c.id=t.collection_id WHERE {' AND '.join(tw)} ORDER BY t.updated_at DESC,t.id DESC LIMIT ?",(*tp,int(limit))).fetchall()
    jobs=conn.execute("SELECT j.id,j.material_id,j.collection_id,j.source_filename,j.status,j.page_count,j.extraction_method,j.created_at,j.updated_at,(SELECT COUNT(*) FROM pdf_import_items i WHERE i.job_id=j.id) item_count,(SELECT COUNT(*) FROM pdf_import_items i WHERE i.job_id=j.id AND i.status='APPROVED') approved_count,(SELECT COUNT(*) FROM pdf_import_items i WHERE i.job_id=j.id AND i.status='IMPORTED') imported_count FROM pdf_import_jobs j ORDER BY j.id DESC LIMIT 30").fetchall()
    stats=conn.execute("SELECT (SELECT COUNT(*) FROM materials WHERE active=1) materials,(SELECT COUNT(*) FROM material_collections WHERE active=1) collections,(SELECT COUNT(*) FROM task_bank WHERE active=1) tasks,(SELECT COUNT(*) FROM pdf_import_jobs WHERE status NOT IN ('IMPORTED','CANCELLED')) pdf_pending").fetchone();conn.close()
    return {'stats':dict(stats),'materials':[dict(x) for x in materials],'collections':[dict(x) for x in collections],'tasks':[dict(x) for x in tasks],'pdf_jobs':[dict(x) for x in jobs]}


def update_material(material_id,fields):
    ensure_tables();allowed={'title','description','subject','grade_min','grade_max','material_type','external_url','tags_json','active'};return _update('materials',material_id,fields,allowed)

def update_collection(collection_id,fields):
    ensure_tables();allowed={'title','description','subject','grade','collection_type','active'};return _update('material_collections',collection_id,fields,allowed)

def update_task(task_id,fields):
    ensure_tables();allowed={'collection_id','subject','grade','study_goal','section','topic','source_label','task_number','title','statement','answer','solution','difficulty','tags_json','active'};return _update('task_bank',task_id,fields,allowed)

def _update(table,row_id,fields,allowed):
    fields=fields or {};pairs=[];vals=[]
    for k,v in fields.items():
        if k not in allowed:continue
        if k in {'grade','grade_min','grade_max','difficulty','collection_id','active'} and v not in (None,''):
            v=int(v)
        if k=='difficulty' and v is not None and not 1<=v<=5:return {'status':'invalid_difficulty'}
        if k in {'grade','grade_min','grade_max'} and v is not None and not 1<=v<=14:return {'status':'invalid_grade'}
        if k=='tags_json' and not isinstance(v,str):v=json.dumps(v or [],ensure_ascii=False)
        if k in {'title','statement'} and not str(v or '').strip():return {'status':f'{k}_required'}
        pairs.append(k+'=?');vals.append(v)
    if not pairs:return {'status':'ok','changed':0}
    pairs.append('updated_at=?');vals.extend([now_iso(),int(row_id)]);conn=connect();cur=conn.execute(f"UPDATE {table} SET {','.join(pairs)} WHERE id=?",vals);conn.commit();conn.close();return {'status':'ok','changed':int(cur.rowcount),'id':int(row_id)}

def collection_detail(collection_id):
    ensure_tables();conn=connect();c=conn.execute('SELECT * FROM material_collections WHERE id=?',(int(collection_id),)).fetchone()
    if not c:conn.close();return None
    mats=conn.execute("SELECT m.*,cm.sort_order FROM collection_materials cm JOIN materials m ON m.id=cm.material_id WHERE cm.collection_id=? ORDER BY cm.sort_order,cm.id",(int(collection_id),)).fetchall();tasks=conn.execute("SELECT * FROM task_bank WHERE collection_id=? AND active=1 ORDER BY topic,difficulty,id",(int(collection_id),)).fetchall();conn.close();return {'collection':dict(c),'materials':[dict(x) for x in mats],'tasks':[dict(x) for x in tasks]}
