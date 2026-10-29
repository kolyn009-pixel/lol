"""Role-scoped olympiad endpoints; no arbitrary recipient or fetch URL input."""
from web_backend import olympiad_store as store

GET_PATHS={f'/api/{r}/olympiads' for r in ('teacher','student')}
GET_PATHS|={'/api/teacher/olympiads/history'}
POST_PATHS={f'/api/{r}/olympiads/subscribe' for r in ('teacher','student')}
POST_PATHS|={f'/api/teacher/olympiads/{x}' for x in ('recommend','event','review')}


def available_channels(role,uid):
    result=['WEB']
    try:
        from web_backend import web_push
        if web_push.status({'role':role,'id':uid,'admin_telegram_id':uid}).get('subscriptions',0):result.append('PUSH')
    except Exception:pass
    from vk_adapter import channel_delivery as delivery
    if role=='teacher':
        if delivery.BOT_TOKEN:result.append('TELEGRAM')
    else:
        if delivery.BOT_TOKEN and delivery.telegram_chat(uid):result.append('TELEGRAM')
        try:
            import os
            if os.getenv('VK_TOKEN','').strip() and delivery.vk_peer(uid):result.append('VK')
        except Exception:pass
    return result


class OlympiadMixin:
    def _olympiad_owner(self,path):
        role=path.split('/')[2]
        auth=self._teacher() if role=='teacher' else self._student()
        if not auth:raise PermissionError('unauthorized')
        return role,int(auth.get('admin_telegram_id',auth.get('id'))) if role=='teacher' else int(auth['id'])

    def olympiad_get(self,path,q):
        try:
            role,uid=self._olympiad_owner(path)
            if path.endswith('/history'):
                import database,json
                store.ensure_schema();c=database.connect()
                try:
                    rows=c.execute('SELECT * FROM olympiad_event_history WHERE event_id=? ORDER BY id DESC LIMIT 30',(q.get('event_id',[''])[0],)).fetchall()
                    result={'items':[{**dict(r),'before':json.loads(r['before_json'] or 'null'),'after':json.loads(r['after_json'])} for r in rows]}
                finally:c.close()
            else:
                result=store.overview(role,uid,q.get('user_id',[None])[0] if role=='teacher' else None)
                result['available_channels']=available_channels(role,uid)
            return self._json(200,result)
        except PermissionError:return self._json(401,{'error':'unauthorized'})
        except (ValueError,TypeError):return self._json(400,{'error':'invalid_request'})
        except Exception as exc:
            print('[olympiads] GET:',type(exc).__name__,flush=True)
            return self._json(500,{'error':'server_error'})

    def olympiad_post(self,path):
        try:
            role,uid=self._olympiad_owner(path)
            if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
            data=self._body()
            if not isinstance(data,dict):raise ValueError('invalid_json')
            oid=str(data.get('olympiad_id') or '')
            if path.endswith('/subscribe'):
                channels=data.get('channels')
                available=available_channels(role,uid)
                if not isinstance(channels,list) or any(x not in available for x in channels):raise ValueError('channel_not_available')
                result=store.subscribe(role,uid,oid,channels)
            elif path.endswith('/recommend'):
                result=store.recommend(int(data['user_id']),oid,data.get('note'),bool(data.get('goal')),bool(data.get('remove')))
            elif path.endswith('/event'):
                result=store.save_event(oid,data.get('event') or {},manual=True)
            else:
                import database
                store.ensure_schema();c=database.connect()
                try:
                    c.execute('UPDATE olympiad_sources SET review_required=0 WHERE url=?',(str(data.get('source_url') or ''),));c.commit()
                finally:c.close()
                result={'status':'ok'}
            return self._json(200,result)
        except PermissionError:return self._json(401,{'error':'unauthorized'})
        except (ValueError,TypeError,KeyError) as exc:return self._json(400,{'error':str(exc)[:100]})
        except Exception as exc:
            print('[olympiads] POST:',type(exc).__name__,flush=True)
            return self._json(500,{'error':'server_error'})
