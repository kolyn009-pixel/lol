"""Narrow routes layered over the existing API, retaining all existing auth flows."""
from urllib.parse import urlparse, parse_qs
from web_backend import group_workspace as groups


class GroupWorkspaceMixin:
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path not in {'/api/public/group-invite','/api/teacher/group/settings','/api/group-onboarding/status'}:
            return super().do_GET()
        try:
            if u.path == '/api/teacher/group/settings':
                if not self._teacher(): return self._json(401,{'error':'unauthorized'})
                result = groups.settings(q.get('id',['0'])[0])
            elif u.path == '/api/group-onboarding/status':
                result = groups.onboarding_status(q.get('token',[''])[0])
            else:
                result = groups.preview(q.get('invite',[''])[0])
            return self._json(200,result)
        except (ValueError,TypeError) as exc:
            return self._json(409,{'error':str(exc)})
        except Exception as exc:
            print('[web-api] group workspace GET:',type(exc).__name__,flush=True)
            return self._json(500,{'error':'server_error'})

    def do_POST(self):
        path = urlparse(self.path).path
        routes = {'/api/teacher/group/settings','/api/teacher/group/invite',
                  '/api/student/group/invite/join','/api/group-onboarding/start',
                  '/api/group-onboarding/region','/api/group-onboarding/complete'}
        if path not in routes: return super().do_POST()
        if not self._same_origin_write(): return self._json(403,{'error':'cross_origin_forbidden'})
        if path.startswith('/api/teacher/') and not self._teacher():
            return self._json(401,{'error':'unauthorized'})
        student = self._student() if path == '/api/student/group/invite/join' else None
        if path == '/api/student/group/invite/join' and not student:
            return self._json(401,{'error':'unauthorized'})
        if path.startswith('/api/group-onboarding/'):
            from web_backend import api as v1
            if not v1._allowed(self.client_address[0]): return self._json(429,{'error':'too_many_attempts'})
        body = self._body()
        if body is None: return self._json(400,{'error':'invalid_json'})
        try:
            if path == '/api/teacher/group/settings': result = groups.update(body.get('group_id'),body)
            elif path == '/api/teacher/group/invite': result = {'invite_path':groups.invitation(body.get('group_id'),body.get('rotate') is True)}
            elif path == '/api/student/group/invite/join': result = groups.join(body.get('invite'),int(student['id']))
            elif path.endswith('/start'): result = groups.onboarding_start(body)
            elif path.endswith('/region'): result = groups.onboarding_region(body)
            else:
                result = groups.onboarding_complete(body)
                return self._json(200,{k:v for k,v in result.items() if k != 'session_token'},cookie=result['session_token'])
            return self._json(200,result)
        except PermissionError as exc: return self._json(403,{'error':str(exc)})
        except (ValueError,TypeError) as exc: return self._json(409,{'error':str(exc)})
        except Exception as exc:
            print('[web-api] group workspace POST:',type(exc).__name__,flush=True)
            return self._json(500,{'error':'server_error'})
