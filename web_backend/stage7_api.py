"""Stage 7 API mixin: formula handbook, favorites and reviewed file imports."""
from __future__ import annotations
from urllib.parse import parse_qs
from web_backend.formula_book import list_formulas,formula_detail,facets,set_favorite,create_formula,update_formula
from web_backend.formula_import import MAX_IMPORT_BYTES,create_draft,draft as import_draft,update_item as update_import_item,approve_item,commit as commit_import

class Stage7Mixin:
    def stage7_get(self,path,q):
        if path=='/api/student/formulas':
            a=self._student()
            if not a:return self._json(401,{'error':'unauthorized'})
            try:
                items=list_formulas(int(a['id']),q.get('subject',[None])[0],q.get('section',[None])[0],q.get('topic',[None])[0],q.get('q',[None])[0],str(q.get('favorites',['0'])[0]).lower() in {'1','true','yes'},q.get('limit',[300])[0]);return self._json(200,{'items':items,'facets':facets()})
            except Exception as exc:print('[web-api] student formulas error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/student/formula':
            a=self._student()
            if not a:return self._json(401,{'error':'unauthorized'})
            try:item=formula_detail(int(q.get('id',['0'])[0]),int(a['id']))
            except Exception:item=None
            return self._json(200,item) if item else self._json(404,{'error':'formula_not_found'})
        if path=='/api/teacher/formulas':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:return self._json(200,{'items':list_formulas(None,q.get('subject',[None])[0],q.get('section',[None])[0],q.get('topic',[None])[0],q.get('q',[None])[0],False,q.get('limit',[500])[0]),'facets':facets()})
            except Exception as exc:print('[web-api] teacher formulas error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/formula':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:item=formula_detail(int(q.get('id',['0'])[0]))
            except Exception:item=None
            return self._json(200,item) if item else self._json(404,{'error':'formula_not_found'})
        if path=='/api/teacher/formula-import':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:return self._json(200,import_draft(int(q.get('id',['0'])[0])))
            except Exception as exc:return self._json(400,{'error':str(exc)})
        return False

    def stage7_post(self,path):
        if path=='/api/student/formula/favorite':
            a=self._student()
            if not a:return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=set_favorite(int(body.get('formula_id')),int(a['id']),bool(body.get('favorite',True)));return self._json(200,r) if r.get('status')=='ok' else self._json(404,{'error':r.get('status')})
            except Exception:return self._json(400,{'error':'invalid_request'})
        if path in {'/api/teacher/formula','/api/teacher/formula/update'}:
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=create_formula(body) if path.endswith('/formula') else update_formula(int(body.get('id')),body.get('fields') or {})
                return self._json(200,r) if r.get('status')=='ok' else self._json(404 if r.get('status')=='not_found' else 400,{'error':r.get('status')})
            except ValueError as exc:return self._json(400,{'error':str(exc)})
            except Exception as exc:print('[web-api] formula mutation error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/formula-import/upload':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:
                form=self._multipart();f=form['file'] if form is not None and 'file' in form else None
                if f is None or not getattr(f,'filename',None):return self._json(400,{'error':'file_required'})
                data=f.file.read(MAX_IMPORT_BYTES+1)
                if len(data)>MAX_IMPORT_BYTES:return self._json(413,{'error':'file_too_large','max_bytes':MAX_IMPORT_BYTES})
                def fv(name,default=None):
                    try:
                        v=form.getfirst(name,default);return v if v not in ('',None) else default
                    except Exception:return default
                defaults={'subject':fv('subject'),'section':fv('section'),'topic':fv('topic'),'study_goal':fv('study_goal'),'grade_min':fv('grade_min'),'grade_max':fv('grade_max')}
                r=create_draft(data,f.filename,defaults);return self._json(200,r)
            except ValueError as exc:return self._json(400,{'error':str(exc)})
            except Exception as exc:print('[web-api] formula import upload error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path in {'/api/teacher/formula-import/item','/api/teacher/formula-import/item/status','/api/teacher/formula-import/commit'}:
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                if path.endswith('/item'):r=update_import_item(int(body.get('item_id')),body.get('fields') or {})
                elif path.endswith('/item/status'):r=approve_item(int(body.get('item_id')),bool(body.get('approved',True)))
                else:r=commit_import(int(body.get('job_id')))
                return self._json(200,r) if r.get('status')=='ok' else self._json(409,{'error':r.get('status')})
            except ValueError as exc:return self._json(400,{'error':str(exc)})
            except Exception as exc:print('[web-api] formula import error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return False
