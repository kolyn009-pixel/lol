"""High-level PDF library/import workflow used by the teacher web API."""
from web_backend.pdf_storage import save_pdf, save_pdf_stream, extract_pdf_text, remove_file
from web_backend.library import create_material, add_material_to_collection
from web_backend.pdf_import import create_import_draft, draft, update_item, approve_item, commit_job
from database import connect, now_iso


def _ensure_hash_column():
    conn=connect()
    cols={row['name'] for row in conn.execute('PRAGMA table_info(materials)').fetchall()}
    if 'sha256' not in cols:
        conn.execute('ALTER TABLE materials ADD COLUMN sha256 TEXT')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_materials_sha256 ON materials(sha256)')
    conn.commit();conn.close()


def _existing_by_hash(digest):
    if not digest:return None
    _ensure_hash_column();conn=connect();row=conn.execute("SELECT id,title,original_filename,size_bytes FROM materials WHERE active=1 AND sha256=? ORDER BY id DESC LIMIT 1",(str(digest),)).fetchone()
    if not row:conn.close();return None
    job=conn.execute("SELECT id,status FROM pdf_import_jobs WHERE material_id=? ORDER BY id DESC LIMIT 1",(int(row['id']),)).fetchone();conn.close()
    return {'material_id':int(row['id']),'title':row['title'],'original_filename':row['original_filename'],'size_bytes':row['size_bytes'],'job_id':int(job['id']) if job else None,'job_status':job['status'] if job else None}


def _finish(saved,title=None,subject=None,grade=None,study_goal=None,section=None,topic=None,collection_id=None):
    duplicate=_existing_by_hash(saved.get('sha256'))
    if duplicate:
        remove_file(saved['path'])
        if collection_id:add_material_to_collection(int(collection_id),int(duplicate['material_id']))
        return {'status':'DUPLICATE','duplicate':True,**duplicate}
    try:
        extracted=extract_pdf_text(saved['path'])
        mid=create_material(title or saved['original_filename'],description='PDF-сборник',subject=subject,grade_min=grade,grade_max=grade,material_type='PDF',file_path=saved['path'],original_filename=saved['original_filename'],mime_type=saved['mime_type'],size_bytes=saved['size_bytes'],tags=['pdf','task-source'])
        _ensure_hash_column();conn=connect();conn.execute('UPDATE materials SET sha256=?,updated_at=? WHERE id=?',(saved.get('sha256'),now_iso(),int(mid)));conn.commit();conn.close()
        if collection_id:add_material_to_collection(int(collection_id),mid)
        if extracted['status']!='OK':return {'status':extracted['status'],'material_id':mid,'pages':extracted['pages'],'method':extracted['method'],'size_bytes':saved['size_bytes']}
        job=create_import_draft(extracted['text'],source_filename=saved['original_filename'],material_id=mid,collection_id=collection_id,page_count=extracted['pages'],extraction_method=extracted['method'],defaults={'subject':subject,'grade':grade,'study_goal':study_goal,'section':section,'topic':topic})
        return {**job,'material_id':mid,'pages':extracted['pages'],'method':extracted['method'],'size_bytes':saved['size_bytes']}
    except Exception:
        try:
            if 'mid' not in locals():remove_file(saved['path'])
        finally:raise


def upload_collection(data,filename,**meta):return _finish(save_pdf(data,filename),**meta)
def upload_collection_stream(stream,filename,**meta):return _finish(save_pdf_stream(stream,filename),**meta)
def get_review(job_id):return draft(int(job_id))
def edit_review_item(item_id,fields):update_item(int(item_id),**(fields or {}));return {'status':'ok'}
def set_review_item(item_id,approved):approve_item(int(item_id),bool(approved));return {'status':'ok','approved':bool(approved)}
def publish_review(job_id):return commit_job(int(job_id))
