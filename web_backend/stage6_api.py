"""Stage 6 API mixin: library management, large PDF upload and protected delivery."""
from __future__ import annotations
from web_backend.pdf_storage import MAX_PDF_BYTES
from web_backend.pdf_workflow import upload_collection_stream
from web_backend.material_delivery import resolve_teacher,resolve_student,send as send_material
from web_backend.library_stage6 import overview,collection_detail,update_material,update_collection,update_task
from web_backend.library import create_collection,add_task

class Stage6Mixin:
    def stage6_get(self,path,q):
        if path=='/api/student/material/file':
            a=self._student()
            if not a:return self._json(401,{'error':'unauthorized'})
            try:item=resolve_student(int(q.get('id',['0'])[0]),int(a['id']))
            except Exception:item=None
            if not item:return self._json(404,{'error':'material_not_found'})
            send_material(self,item,inline=True);return True
        if path=='/api/teacher/material/file':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:item=resolve_teacher(int(q.get('id',['0'])[0]))
            except Exception:item=None
            if not item:return self._json(404,{'error':'material_not_found'})
            send_material(self,item,inline=True);return True
        if path=='/api/teacher/library/overview':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            return self._json(200,overview(q.get('q',[None])[0],q.get('subject',[None])[0]))
        if path=='/api/teacher/library/collection/detail':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:item=collection_detail(int(q.get('id',['0'])[0]))
            except Exception:item=None
            return self._json(200,item) if item else self._json(404,{'error':'collection_not_found'})
        return False

    def stage6_post(self,path):
        if path in {'/api/teacher/pdf-import/upload','/api/teacher/pdf-import/upload-stream'}:
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:
                form=self._multipart();file_item=form['file'] if form is not None and 'file' in form else None
                if file_item is None or not getattr(file_item,'filename',None):return self._json(400,{'error':'file_required'})
                def fv(name,default=None):
                    try:
                        v=form.getfirst(name,default);return v if v not in ('',None) else default
                    except Exception:return default
                grade=fv('grade');collection_id=fv('collection_id')
                r=upload_collection_stream(file_item.file,file_item.filename,title=fv('title'),subject=fv('subject'),grade=int(grade) if grade else None,study_goal=fv('study_goal'),section=fv('section'),topic=fv('topic'),collection_id=int(collection_id) if collection_id else None)
                return self._json(200,r)
            except ValueError as exc:return self._json(413 if str(exc)=='file_too_large' else 400,{'error':str(exc),'max_bytes':MAX_PDF_BYTES})
            except Exception as exc:print('[web-api] PDF stream upload error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path in {'/api/teacher/library/collection','/api/teacher/library/task'}:
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                if path.endswith('/collection'):
                    title=str(body.get('title') or '').strip()
                    if not title:return self._json(400,{'error':'title_required'})
                    grade=body.get('grade')
                    if grade not in (None,''):
                        grade=int(grade)
                        if not 1<=grade<=11:return self._json(400,{'error':'invalid_grade'})
                    cid=create_collection(title,body.get('description') or '',body.get('subject'),grade,body.get('collection_type') or 'BOOK')
                    return self._json(200,{'status':'ok','id':cid})
                statement=str(body.get('statement') or '').strip();subject=str(body.get('subject') or '').strip().upper()
                if not statement:return self._json(400,{'error':'statement_required'})
                if not subject:return self._json(400,{'error':'subject_required'})
                grade=body.get('grade')
                if grade not in (None,''):
                    grade=int(grade)
                    if not 1<=grade<=11:return self._json(400,{'error':'invalid_grade'})
                difficulty=int(body.get('difficulty') or 2)
                if not 1<=difficulty<=5:return self._json(400,{'error':'invalid_difficulty'})
                tid=add_task(subject,statement,grade,body.get('study_goal'),body.get('section'),body.get('topic'),body.get('collection_id'),body.get('source_label'),body.get('task_number'),body.get('title'),body.get('answer'),body.get('solution'),difficulty,body.get('tags') or [])
                return self._json(200,{'status':'ok','id':tid})
            except (TypeError,ValueError) as exc:return self._json(400,{'error':str(exc) or 'invalid_request'})
            except Exception as exc:print('[web-api] library create error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path in {'/api/teacher/library/material/update','/api/teacher/library/collection/update','/api/teacher/library/task/update'}:
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                if path.endswith('/material/update'):r=update_material(int(body.get('id')),body.get('fields') or {})
                elif path.endswith('/collection/update'):r=update_collection(int(body.get('id')),body.get('fields') or {})
                else:r=update_task(int(body.get('id')),body.get('fields') or {})
                return self._json(200,r) if r.get('status')=='ok' else self._json(400,{'error':r.get('status')})
            except (TypeError,ValueError) as exc:return self._json(400,{'error':str(exc) or 'invalid_request'})
            except Exception as exc:print('[web-api] library update error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return False
