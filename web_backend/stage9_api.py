"""Stage 9 API routes and authentication for the parent cabinet."""
from __future__ import annotations
from web_backend.parent_portal import dashboard,student,schedule
from web_backend.parent_auth import consume_parent_login_code
from web_backend.web_sessions import SESSION_TTL,create_session
from web_backend.payment_hub import parent_hub,parent_pay_nearest,parent_create_package,parent_quote_package,parent_attach_receipt
from web_backend import api as v1
from web_backend import parent_messages

class Stage9Mixin:
    def _parent(self):
        auth=self._auth()
        return auth if auth and auth.get('role')=='parent' else None

    def stage9_get(self,path,q):
        if not path.startswith('/api/parent/'):return False
        auth=self._parent()
        if not auth:return self._json(401,{'error':'unauthorized'})
        pid=int(auth['id'])
        try:
            if path=='/api/parent/messages/students':return self._json(200,parent_messages.students(pid))
            if path=='/api/parent/messages':
                return self._json(200,parent_messages.thread(pid,int(q.get('student_id',['0'])[0]),q.get('limit',[100])[0]))
            if path=='/api/parent/dashboard':
                item=dashboard(pid);return self._json(200,item) if item else self._json(404,{'error':'parent_not_found'})
            if path=='/api/parent/student':
                item=student(pid,int(q.get('id',['0'])[0]));return self._json(200,item) if item else self._json(404,{'error':'student_not_found'})
            if path=='/api/parent/schedule':
                uid=q.get('student_id',[None])[0];return self._json(200,{'items':schedule(pid,int(uid) if uid not in (None,'') else None,q.get('days',[45])[0],q.get('limit',[120])[0])})
            if path=='/api/parent/finance/hub':
                uid=q.get('student_id',[None])[0]
                return self._json(200,parent_hub(pid,int(uid) if uid not in (None,'') else None))
        except PermissionError:return self._json(404,{'error':'student_not_found'})
        except (TypeError,ValueError):return self._json(400,{'error':'invalid_request'})
        except Exception as exc:print('[web-api] parent GET error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return False

    def stage9_post(self,path):
        if path=='/api/auth/parent/code':
            if not v1._allowed(self.client_address[0]):return self._json(429,{'error':'too_many_attempts'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:result=consume_parent_login_code(body.get('code'))
            except Exception as exc:
                print('[web-api] parent auth error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
            if result.get('status')!='ok':return self._json(401,{'error':result.get('status','invalid_code')})
            entity=result['parent'];token=create_session('parent',int(entity['id']),SESSION_TTL)
            return self._json(200,{'ok':True,'parent':entity},token)
        if path in {'/api/parent/messages/send','/api/parent/messages/read'}:
            auth=self._parent()
            if not auth:return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if not isinstance(body,dict):return self._json(400,{'error':'invalid_json'})
            try:
                pid=int(auth['id']);uid=int(body.get('student_id') or 0)
                result=(parent_messages.send(pid,uid,body.get('text')) if path.endswith('/send')
                        else parent_messages.mark_parent_read(pid,uid))
                return self._json(200,result)
            except PermissionError:return self._json(404,{'error':'student_not_found'})
            except (TypeError,ValueError) as exc:return self._json(400,{'error':str(exc) or 'invalid_request'})
            except Exception as exc:print('[web-api] parent messages POST error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
        if not path.startswith('/api/parent/finance/'):return False
        auth=self._parent()
        if not auth:return self._json(401,{'error':'unauthorized'})
        body=self._body()
        if body is None:return self._json(400,{'error':'invalid_json'})
        pid=int(auth['id'])
        try:
            uid=int(body.get('student_id') or 0)
            if path=='/api/parent/finance/pay-nearest':
                return self._json(200,parent_pay_nearest(pid,uid,body.get('promo_code')))
            if path=='/api/parent/finance/package/quote':
                return self._json(200,parent_quote_package(pid,uid,body.get('selection_key'),body.get('lessons_count'),body.get('promo_code')))
            if path=='/api/parent/finance/package':
                return self._json(200,parent_create_package(pid,uid,body.get('selection_key'),body.get('lessons_count'),body.get('promo_code')))
            if path=='/api/parent/finance/receipt':
                return self._json(200,parent_attach_receipt(pid,uid,body.get('payment_id'),body.get('filename'),body.get('mime_type'),body.get('content_b64')))
        except PermissionError:return self._json(404,{'error':'student_not_found'})
        except (TypeError,ValueError) as exc:return self._json(400,{'error':str(exc) or 'invalid_request'})
        except Exception as exc:print('[web-api] parent finance POST error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return False
