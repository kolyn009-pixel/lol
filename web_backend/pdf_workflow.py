"""High-level PDF library/import workflow used by the teacher web API."""
from web_backend.pdf_storage import save_pdf, extract_pdf_text, remove_file
from web_backend.library import create_material, add_material_to_collection
from web_backend.pdf_import import create_import_draft, draft, update_item, approve_item, commit_job


def upload_collection(data,filename,title=None,subject=None,grade=None,study_goal=None,section=None,topic=None,collection_id=None):
    saved=save_pdf(data,filename)
    try:
        extracted=extract_pdf_text(saved['path'])
        mid=create_material(title or saved['original_filename'],description='PDF-сборник',subject=subject,grade_min=grade,grade_max=grade,material_type='PDF',file_path=saved['path'],original_filename=saved['original_filename'],mime_type=saved['mime_type'],size_bytes=saved['size_bytes'],tags=['pdf','task-source'])
        if collection_id:add_material_to_collection(int(collection_id),mid)
        if extracted['status']!='OK':return {'status':extracted['status'],'material_id':mid,'pages':extracted['pages'],'method':extracted['method']}
        job=create_import_draft(extracted['text'],source_filename=saved['original_filename'],material_id=mid,collection_id=collection_id,page_count=extracted['pages'],extraction_method=extracted['method'],defaults={'subject':subject,'grade':grade,'study_goal':study_goal,'section':section,'topic':topic})
        return {**job,'material_id':mid,'pages':extracted['pages'],'method':extracted['method']}
    except Exception:
        # File remains only if a material record was successfully created. Before that,
        # clean it up so failed uploads do not fill storage.
        try:
            if 'mid' not in locals():remove_file(saved['path'])
        finally:
            raise


def get_review(job_id):return draft(int(job_id))

def edit_review_item(item_id,fields):update_item(int(item_id),**(fields or {}));return {'status':'ok'}

def set_review_item(item_id,approved):approve_item(int(item_id),bool(approved));return {'status':'ok','approved':bool(approved)}

def publish_review(job_id):return commit_job(int(job_id))
