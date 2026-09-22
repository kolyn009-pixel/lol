"""Teacher Web API for Adelia-first unified conversations."""
from __future__ import annotations
from database import connect
from web_backend import unified_messaging as um
from web_backend.message_delivery import send_teacher_reply,send_existing_message_channels
from web_backend.message_read_sync import mark_conversation_read
from web_backend import message_media


def _channel_map(user_ids):
    ids=sorted({int(x) for x in user_ids if x is not None})
    if not ids:return {}
    marks=','.join('?' for _ in ids);conn=connect()
    telegram={int(r['id']) for r in conn.execute(f"SELECT id FROM users WHERE id IN ({marks}) AND telegram_id IS NOT NULL",ids).fetchall()}
    vk={int(r['user_id']) for r in conn.execute(f"SELECT DISTINCT user_id FROM channel_identities WHERE user_id IN ({marks}) AND channel='VK' AND enabled=1",ids).fetchall()}
    conn.close();return {uid:{'telegram':uid in telegram,'vk':uid in vk} for uid in ids}


def _conversation_items(limit,unread_only=False):
    items=um.conversations(limit,unread_only);channels=_channel_map(i.get('student_id') for i in items)
    for item in items:
        item['channels']=channels.get(int(item['student_id']),{'telegram':False,'vk':False})
    return items


class Stage10Mixin:
    def stage10_get(self,path,q):
        if path.startswith('/api/message-media/'):
            auth=self._auth()
            if not auth:return self._json(401,{'error':'unauthorized'})
            token=path.rsplit('/',1)[-1]
            try:
                meta,data=message_media.read(token)
                role=str(auth.get('role') or '')
                if role=='student' and int(auth.get('id') or 0)!=int(meta.get('student_id') or 0):return self._json(403,{'error':'forbidden'})
                if role not in {'student','teacher'}:return self._json(403,{'error':'forbidden'})
                self.send_response(200);self.send_header('Content-Type',str(meta.get('mime') or 'application/octet-stream'));self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','private, max-age=86400');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data);return
            except (ValueError,FileNotFoundError):return self._json(404,{'error':'media_not_found'})
            except Exception as exc:print('[stage10] message media GET error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
        if not path.startswith('/api/teacher/messages'):return False
        if not self._teacher():return self._json(401,{'error':'unauthorized'})
        try:
            if path=='/api/teacher/messages':
                unread=str(q.get('unread',['0'])[0]).lower() in {'1','true','yes'}
                return self._json(200,{'items':_conversation_items(q.get('limit',[100])[0],unread)})
            if path=='/api/teacher/messages/student':
                uid=int(q.get('user_id',['0'])[0])
                conn=connect()
                user=conn.execute("SELECT id,name,active FROM users WHERE id=? LIMIT 1",(uid,)).fetchone()
                conn.close()
                if not user or not int(user['active'] or 0):return self._json(404,{'error':'student_not_found'})
                conv=um.conversation(uid,'STUDENT',None)
                channels=_channel_map([uid]).get(uid,{'telegram':False,'vk':False})
                return self._json(200,{'conversation':{'id':int(conv['id']),'student_id':uid,'name':user['name'],'channels':channels,'unread':0,'last_body':''}})
            if path=='/api/teacher/messages/history':
                cid=int(q.get('conversation_id',['0'])[0])
                return self._json(200,{'items':list(reversed(um.history(cid,q.get('limit',[100])[0])))})
        except (TypeError,ValueError):return self._json(400,{'error':'invalid_request'})
        except Exception as exc:print('[stage10] teacher messages GET error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
        return self._json(404,{'error':'not_found'})

    def _stage10_upload(self,student_id,origin='WEB'):
        form=self._multipart();item=form['file'] if form is not None and 'file' in form else None
        if item is None or not getattr(item,'filename',None):raise ValueError('file_required')
        data=item.file.read(message_media.MAX_BYTES+1)
        if len(data)>message_media.MAX_BYTES:raise ValueError('media_too_large')
        mime=getattr(item,'type',None) or 'application/octet-stream'
        kind='photo' if str(mime).lower().startswith('image/') else 'document'
        return message_media.store_bytes(int(student_id),data,item.filename,mime,kind,origin=origin)

    def stage10_post(self,path):
        if not path.startswith('/api/teacher/messages'):return False
        teacher=self._teacher()
        if not teacher:return self._json(401,{'error':'unauthorized'})
        if path=='/api/teacher/messages/upload':
            try:
                form=self._multipart()
                item=form['file'] if form is not None and 'file' in form else None
                if item is None or not getattr(item,'filename',None):raise ValueError('file_required')
                uid=int(form.getfirst('user_id','0'))
                data=item.file.read(message_media.MAX_BYTES+1)
                if len(data)>message_media.MAX_BYTES:raise ValueError('media_too_large')
                mime=getattr(item,'type',None) or 'application/octet-stream'
                kind='photo' if str(mime).lower().startswith('image/') else 'document'
                return self._json(200,{'attachment':message_media.store_bytes(uid,data,item.filename,mime,kind,origin='WEB')})
            except ValueError as exc:return self._json(413 if str(exc)=='media_too_large' else 400,{'error':str(exc),'max_bytes':message_media.MAX_BYTES})
            except Exception as exc:print('[stage10] teacher media upload error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
        body=self._body()
        if body is None:return self._json(400,{'error':'invalid_json'})
        try:
            if path=='/api/teacher/messages/send':
                tid=teacher.get('id') if hasattr(teacher,'get') else None
                # Normal Send is Adelia-only. External channels require the explicit action below.
                result=send_teacher_reply(int(body.get('user_id')),body.get('text'),[],tid,body.get('attachment'))
                return self._json(200,result)
            if path=='/api/teacher/messages/send-external':
                result=send_existing_message_channels(int(body.get('message_id')),body.get('channels'))
                return self._json(200,result) if result['status']=='ok' else self._json(502,result)
            if path=='/api/teacher/messages/read':
                return self._json(200,mark_conversation_read(int(body.get('conversation_id'))))
        except ValueError as exc:return self._json(400,{'error':str(exc)})
        except Exception as exc:print('[stage10] teacher messages POST error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
        return self._json(404,{'error':'not_found'})
