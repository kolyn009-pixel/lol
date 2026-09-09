"""Stage 9 API routes for the parent cabinet."""
from __future__ import annotations
from web_backend.parent_portal import dashboard,student,schedule

class Stage9Mixin:
    def stage9_get(self,path,q):
        if not path.startswith('/api/parent/'):return False
        auth=getattr(self,'_parent',lambda:None)()
        if not auth:return self._json(401,{'error':'unauthorized'})
        pid=int(auth['id'])
        try:
            if path=='/api/parent/dashboard':
                item=dashboard(pid);return self._json(200,item) if item else self._json(404,{'error':'parent_not_found'})
            if path=='/api/parent/student':
                item=student(pid,int(q.get('id',['0'])[0]));return self._json(200,item) if item else self._json(404,{'error':'student_not_found'})
            if path=='/api/parent/schedule':
                uid=q.get('student_id',[None])[0];return self._json(200,{'items':schedule(pid,int(uid) if uid not in (None,'') else None,q.get('days',[45])[0],q.get('limit',[120])[0])})
        except PermissionError:return self._json(404,{'error':'student_not_found'})
        except (TypeError,ValueError):return self._json(400,{'error':'invalid_request'})
        except Exception as exc:print('[web-api] parent GET error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return False
