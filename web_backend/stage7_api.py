"""Stage 7 API mixin: formula handbook, favorites and reviewed file imports."""
from __future__ import annotations
import education_profile
from web_backend.formula_book import list_formulas,formula_detail,facets,set_favorite,create_formula,update_formula
from web_backend.formula_import import MAX_IMPORT_BYTES,create_draft,draft as import_draft,update_item as update_import_item,approve_item,commit as commit_import

def _truth(value,default=True):
    if value is None:return default
    if isinstance(value,bool):return value
    return str(value).strip().lower() in {'1','true','yes','on'}

def _browse_profile(q,profile):
    own_type=str(profile.get('type') or 'SCHOOL').upper();own_level=int(profile.get('level') or 0) or None
    requested=str(q.get('education_level',[own_type])[0] or own_type).upper()
    if requested not in {'SCHOOL','COLLEGE'}:requested=own_type
    raw=q.get('level',[None])[0]
    try:level=int(raw) if raw not in (None,'') else (own_level if requested==own_type else None)
    except Exception:level=None
    if requested=='SCHOOL' and level is not None and not 1<=level<=11:level=None
    if requested=='COLLEGE' and level is not None and not 1<=level<=4:level=None
    return requested,level

def _level_filter(items,kind,level):
    if level is None:return items
    if kind=='SCHOOL':return [x for x in items if (x.get('grade_min') is None or int(x['grade_min'])<=level) and (x.get('grade_max') is None or int(x['grade_max'])>=level)]
    return [x for x in items if (x.get('course_min') is None or int(x['course_min'])<=level) and (x.get('course_max') is None or int(x['course_max'])>=level]

class Stage7Mixin:
    def stage7_get(self,path,q):
        if path=='/api/student/formulas':
            a=self._student()
            if not a:return self._json(401,{'error':'unauthorized'})
            try:
                profile=education_profile.get(int(a['id']));kind,level=_browse_profile(q,profile)
                items=list_formulas(int(a['id']),q.get('subject',[None])[0],q.get('section',[None])[0],q.get('topic',[None])[0],q.get('q',[None])[0],str(q.get('favorites',['0'])[0]).lower() in {'1','true','yes'},q.get('limit',[300])[0],kind)
                items=_level_filter(items,kind,level)
                return self._json(200,{'items':items,'facets':facets(),'education':profile,'browse':{'education_level':kind,'level':level}})
            except Exception as exc:print('[web-api] student formulas error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/student/formula':
            a=self._student()
            if not a:return self._json(401,{'error':'unauthorized'})
            try:item=formula_detail(int(q.get('id',['0'])[0]),int(a['id']))
            except Exception:item=None
            return self._json(200,item) if item else self._json(404,{'error':'formula_not_found'})
        if path=='/api/teacher/formulas':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:return self._json(200,{'items':list_formulas(None,q.get('subject',[None])[0],q.get('section',[None])[0],q.get('topic',[None])[0],q.get('q',[None])[0],False,q.get('limit',[500])[0],q.get('education_level',[None])[0]),'facets':facets()})
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
                r=set_favorite(int(body.get('formula_id')),int(a['id']),_truth(body.get('favorite'),True));return self._json(200,r) if r.get('status')=='ok' else self._json(404,{'error':r.get('status')})
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
                defaults={'subject':fv('subject'),'section':fv('section'),'topic':fv('topic'),'study_goal':fv('study_goal'),'grade_min':fv('grade_min'),'grade_max':fv('grade_max'),'education_level':fv('education_level'),'course_min':fv('course_min'),'course_max':fv('course_max')}
                r=create_draft(data,f.filename,defaults);return self._json(200,r)
            except ValueError as exc:return self._json(400,{'error':str(exc)})
            except Exception as exc:print('[web-api] formula import upload error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path in {'/api/teacher/formula-import/item','/api/teacher/formula-import/item/status','/api/teacher/formula-import/commit'}:
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                if path.endswith('/item'):r=update_import_item(int(body.get('item_id')),body.get('fields') or {})
                elif path.endswith('/item/status'):r=approve_item(int(body.get('item_id')),_truth(body.get('approved'),True))
                else:r=commit_import(int(body.get('job_id')))
                return self._json(200,r) if r.get('status')=='ok' else self._json(409,{'error':r.get('status')})
            except ValueError as exc:return self._json(400,{'error':str(exc)})
            except Exception as exc:print('[web-api] formula import error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return False
