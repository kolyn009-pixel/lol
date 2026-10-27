"""All identities come from the signed-in teacher session, never the payload."""
from web_backend import self_study

ROOT='/api/teacher/self-study'
GET_PATHS={ROOT,ROOT+'/lesson'}
POST_PATHS={ROOT+'/profile',ROOT+'/draft',ROOT+'/submit'}


class SelfStudyMixin:
    def self_study_route(self,path,query=None,write=False):
        auth=self._teacher()
        if not auth:
            return self._json(401,{'error':'unauthorized'})
        if write and not self._same_origin_write():
            return self._json(403,{'error':'cross_origin_forbidden'})
        try:
            owner=int(auth['admin_telegram_id'] if 'admin_telegram_id' in auth else auth['id'])
            if not write:
                payload=(self_study.get_lesson(owner,(query or {}).get('id',[''])[0])
                         if path==ROOT+'/lesson' else self_study.overview(owner))
            else:
                data=self._body()
                if not isinstance(data,dict):
                    return self._json(400,{'error':'invalid_json'})
                if path==ROOT+'/profile':payload=self_study.save_profile(owner,data)
                elif path==ROOT+'/draft':payload=self_study.save_draft(owner,data)
                elif path==ROOT+'/submit':payload=self_study.submit(owner,data)
                else:return self._json(404,{'error':'not_found'})
            return self._json(200,payload)
        except (ValueError,TypeError,KeyError) as exc:
            # Known validation codes only; no user answers or provider details in logs.
            allowed={'invalid_language','lesson_not_found','invalid_answers','answer_all_questions',
                     'invalid_request_id','request_conflict','invalid_daily_minutes',
                     'invalid_target_dates','invalid_target_date'}
            error=str(exc)
            return self._json(400,{'error':error if error in allowed else 'invalid_request'})
        except Exception as exc:
            print('[self-study]',type(exc).__name__,flush=True)
            return self._json(500,{'error':'server_error'})
