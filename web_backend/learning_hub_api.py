"""Authenticated routes for learning records, material search and waiting slots."""
from web_backend import learning_hub as hub, learning_tools

GET_PATHS={f'/api/{role}/learning' for role in ('teacher','student','parent')} | {'/api/teacher/learning/waiting','/api/student/learning/materials','/api/teacher/learning/materials'}
GET_PATHS |= {'/api/teacher/learning/help','/api/student/learning/help','/api/teacher/learning/week'}

POST_PATHS={f'/api/teacher/learning/{action}' for action in ('summary','error','plan','offer')} | {f'/api/student/learning/{action}' for action in ('wait','wait/close','offer/respond')}
POST_PATHS |= {'/api/student/learning/help','/api/teacher/learning/help/close'}

class LearningHubMixin:
    def _learning_identity(self, role, requested=None):
        if role=='teacher':
            if not self._teacher():raise PermissionError('unauthorized')
            return int(requested) if requested is not None else None
        if role=='student':
            auth=self._student()
            if not auth:raise PermissionError('unauthorized')
            return int(auth['id'])
        auth=self._auth()
        if not auth or auth['role']!='parent':raise PermissionError('unauthorized')
        from web_backend.parent_portal import _assert_link
        return _assert_link(int(auth['id']),int(requested))

    def learning_get(self,path,q):
        role=path.split('/')[2]
        try:
            uid=self._learning_identity(role,q.get('user_id',[None])[0])
            if path.endswith('/help'):return self._json(200,{'items':learning_tools.list_help(uid if role=='student' else None)})
            if path.endswith('/week'):return self._json(200,learning_tools.week_summary())
            if path.endswith('/materials'):result={'items':hub.material_search(uid,q.get('q',[''])[0])}
            elif path.endswith('/waiting'):
                if q.get('start_at'):result={'items':hub.candidates(q['start_at'][0],q.get('duration',['60'])[0],q.get('subject',['PHYSICS'])[0])}
                else:result={'items':hub.waiting_overview()}
            else:result=hub.overview(uid,teacher=role=='teacher')
            return self._json(200,result)
        except PermissionError as exc:return self._json(401 if str(exc)=='unauthorized' else 404,{'error':str(exc)})
        except (TypeError,ValueError,KeyError) as exc:return self._json(400,{'error':str(exc) or 'invalid_request'})
        except Exception as exc:
            print('[learning-hub] GET error:',type(exc).__name__,flush=True)
            return self._json(500,{'error':'server_error'})

    def learning_post(self,path):
        if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
        role=path.split('/')[2]
        try:
            # Authenticate before parsing user input or touching learning records.
            self._learning_identity(role)
            data=self._body()
            if not isinstance(data,dict):return self._json(400,{'error':'invalid_json'})
            uid=self._learning_identity(role,data.get('user_id'))
            if path.endswith('/help/close'):return self._json(200,learning_tools.close_help(data.get('id')))
            if path.endswith('/help'):return self._json(200,learning_tools.request_help(uid,data))
            if path.endswith('/summary'):result=hub.save_summary(uid,data)
            elif path.endswith('/error'):result=hub.save_error(uid,data)
            elif path.endswith('/plan'):result=hub.save_plan(uid,data)
            elif path.endswith('/offer'):result=hub.offer(data.get('request_id'),data.get('start_at'),data.get('duration_minutes',60))
            elif path.endswith('/wait/close'):result=hub.close_wait(uid,data.get('request_id'))
            elif path.endswith('/offer/respond'):result=hub.respond_offer(uid,data.get('offer_id'),data.get('response'))
            else:result=hub.add_wait(uid,data)
            return self._json(200,result)
        except PermissionError as exc:return self._json(401 if str(exc)=='unauthorized' else 404,{'error':str(exc)})
        except (TypeError,ValueError,KeyError) as exc:return self._json(400,{'error':str(exc) or 'invalid_request'})
        except Exception as exc:
            print('[learning-hub] POST error:',type(exc).__name__,flush=True)
            return self._json(500,{'error':'server_error'})
