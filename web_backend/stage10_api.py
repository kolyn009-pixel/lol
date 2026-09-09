"""Teacher Web API for Stage 10 unified conversations."""
from __future__ import annotations
from web_backend import unified_messaging as um
from web_backend.message_delivery import send_teacher_reply


class Stage10Mixin:
    def stage10_get(self,path,q):
        if not path.startswith('/api/teacher/messages'):return False
        if not self._teacher():return self._json(401,{'error':'unauthorized'})
        try:
            if path=='/api/teacher/messages':
                return self._json(200,{'items':um.conversations(q.get('limit',[100])[0],str(q.get('unread',['0'])[0]).lower() in {'1','true','yes'})})
            if path=='/api/teacher/messages/history':
                cid=int(q.get('conversation_id',['0'])[0])
                return self._json(200,{'items':list(reversed(um.history(cid,q.get('limit',[100])[0])))})
        except (TypeError,ValueError):return self._json(400,{'error':'invalid_request'})
        except Exception as exc:print('[stage10] teacher messages GET error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return self._json(404,{'error':'not_found'})

    def stage10_post(self,path):
        if not path.startswith('/api/teacher/messages'):return False
        if not self._teacher():return self._json(401,{'error':'unauthorized'})
        body=self._body()
        if body is None:return self._json(400,{'error':'invalid_json'})
        try:
            if path=='/api/teacher/messages/send':
                teacher=self._teacher() or {}
                tid=teacher.get('telegram_id') if hasattr(teacher,'get') else None
                result=send_teacher_reply(int(body.get('user_id')),body.get('text'),body.get('channels'),tid)
                return self._json(200,result) if result['status']=='ok' else self._json(502,result)
            if path=='/api/teacher/messages/read':
                return self._json(200,um.mark_read(int(body.get('conversation_id'))))
        except ValueError as exc:return self._json(400,{'error':str(exc)})
        except Exception as exc:print('[stage10] teacher messages POST error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return self._json(404,{'error':'not_found'})
