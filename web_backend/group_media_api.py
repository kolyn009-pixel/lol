from urllib.parse import urlparse,parse_qs
from web_backend import group_visuals as visuals


class GroupMediaMixin:
    def do_GET(self):
        u=urlparse(self.path);q=parse_qs(u.query)
        if u.path.startswith('/api/visual/avatar/'):
            student=self._student();teacher=bool(self._teacher())
            try:data=visuals.image(u.path.rsplit('/',1)[-1],int(student['id']) if student else None,teacher)
            except (ValueError,PermissionError):return self._json(404,{'error':'avatar_not_found'})
            self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','private, no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        if u.path!='/api/teacher/group/chat':return super().do_GET()
        if not self._teacher():return self._json(401,{'error':'unauthorized'})
        try:return self._json(200,visuals.teacher_chat(q.get('group_id',['0'])[0]))
        except (ValueError,TypeError) as e:return self._json(409,{'error':str(e)})

    def do_POST(self):
        path=urlparse(self.path).path
        if path not in {'/api/student/avatar','/api/teacher/group/avatar','/api/teacher/group/chat'}:return super().do_POST()
        if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
        auth=self._student() if path=='/api/student/avatar' else self._teacher()
        if not auth:return self._json(401,{'error':'unauthorized'})
        body=self._body()
        if body is None:return self._json(400,{'error':'invalid_json'})
        try:
            if path=='/api/student/avatar':result=visuals.save_avatar('STUDENT',int(auth['id']),body)
            elif path.endswith('/avatar'):result=visuals.save_avatar('GROUP',body.get('group_id'),body)
            else:result=visuals.teacher_send(body.get('group_id'),auth['admin_telegram_id'],body.get('body'),body.get('client_id'))
            return self._json(200,result)
        except PermissionError as e:return self._json(403,{'error':str(e)})
        except (ValueError,TypeError) as e:return self._json(409,{'error':str(e)})
        except Exception as e:
            print('[web-api] group media error:',type(e).__name__,flush=True);return self._json(500,{'error':'server_error'})
