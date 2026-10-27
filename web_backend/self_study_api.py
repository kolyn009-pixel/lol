"""All identities come from the signed-in teacher session, never the payload."""
from web_backend import self_study
from web_backend import self_study_access as access
from web_backend import self_study_practice as practice

ROOT='/api/teacher/self-study'
GET_PATHS={ROOT,ROOT+'/lesson',ROOT+'/practice',ROOT+'/checkpoint/status',ROOT+'/checkpoint',ROOT+'/scenes',ROOT+'/entry',ROOT+'/access'}
POST_PATHS={ROOT+'/profile',ROOT+'/draft',ROOT+'/submit',ROOT+'/review/answer',ROOT+'/review/rate',
            ROOT+'/checkpoint/start',ROOT+'/checkpoint/draft',ROOT+'/checkpoint/submit',ROOT+'/speech/feedback',ROOT+'/scenes/save',ROOT+'/entry/submit',ROOT+'/access/invite',ROOT+'/access/revoke',ROOT+'/access/accept'}

GET_PATHS |= {p.replace('/teacher/','/student/') for p in list(GET_PATHS)}
POST_PATHS |= {p.replace('/teacher/','/student/') for p in list(POST_PATHS)}
GET_PATHS |= {p.replace('/teacher/','/parent/') for p in list(GET_PATHS) if '/teacher/' in p}
POST_PATHS |= {p.replace('/teacher/','/parent/') for p in list(POST_PATHS) if '/teacher/' in p}

class SelfStudyMixin:
    def self_study_route(self,path,query=None,write=False):
        role=path.split('/')[2]
        student=role in ('student','parent')
        if role=='parent':
            auth=getattr(self,'_auth',lambda:None)()
            if not auth or auth.get('role')!='parent':auth=None
        else:auth=(getattr(self,'_student',lambda:None)() if student else self._teacher())
        path=path.replace('/api/'+role+'/','/api/teacher/',1)
        if not auth:
            return self._json(401,{'error':'unauthorized'})
        if write and not self._same_origin_write():
            return self._json(403,{'error':'cross_origin_forbidden'})
        try:
            owner=int(auth['admin_telegram_id'] if 'admin_telegram_id' in auth else auth['id'])
            if owner<=0:raise ValueError('invalid_request')
            if path==ROOT+'/access/accept':
                if not student or not write:return self._json(403,{'error':'invalid_family_invite'})
                data=self._body()
                if not isinstance(data,dict):return self._json(400,{'error':'invalid_json'})
                return self._json(200,access.accept(owner,data,role))
            if student:
                if not access.is_member(owner,role):raise PermissionError('family_access_required')
                owner=access.study_identity(role,owner)
            elif not access.is_manager(owner):raise PermissionError('family_owner_required')
            if not write:
                q=query or {}
                if path==ROOT+'/access':payload=access.overview(owner)
                elif path==ROOT+'/entry':
                    from web_backend.self_study_entry import get
                    payload=get(owner)
                elif path==ROOT+'/lesson':payload=self_study.get_lesson(owner,q.get('id',[''])[0])
                elif path==ROOT+'/practice':payload=practice.practice(owner,q.get('language',['en'])[0])
                elif path==ROOT+'/checkpoint/status':payload=practice.checkpoint_status(owner,q.get('language',['en'])[0])
                elif path==ROOT+'/checkpoint':payload=practice.get_checkpoint(owner,int(q.get('id',['0'])[0]))
                elif path==ROOT:payload=self_study.overview(owner)
                elif path==ROOT+'/scenes':
                    from web_backend.self_study_scenes import list_scenes
                    payload=list_scenes(owner,q.get('language',['en'])[0])
                else:return self._json(404,{'error':'not_found'})
            else:
                data=self._body()
                if not isinstance(data,dict):
                    return self._json(400,{'error':'invalid_json'})
                if path==ROOT+'/access/invite':payload=access.issue(owner,data)
                elif path==ROOT+'/access/revoke':payload=access.revoke(owner,data)
                elif path==ROOT+'/entry/submit':
                    from web_backend.self_study_entry import submit
                    payload=submit(owner,data)
                elif path==ROOT+'/profile':payload=self_study.save_profile(owner,data)
                elif path==ROOT+'/draft':payload=self_study.save_draft(owner,data)
                elif path==ROOT+'/submit':payload=self_study.submit(owner,data)
                elif path==ROOT+'/review/answer':payload=practice.answer_card(owner,data)
                elif path==ROOT+'/review/rate':payload=practice.rate_card(owner,data)
                elif path==ROOT+'/checkpoint/start':payload=practice.start_checkpoint(owner,data)
                elif path==ROOT+'/checkpoint/draft':payload=practice.save_checkpoint(owner,data)
                elif path==ROOT+'/checkpoint/submit':payload=practice.save_checkpoint(owner,data,complete=True)
                elif path==ROOT+'/speech/feedback':
                    from web_backend.self_study_feedback import feedback
                    payload=feedback(owner,data)
                elif path==ROOT+'/scenes/save':
                    from web_backend.self_study_scenes import save_scene
                    payload=save_scene(owner,data)
                else:return self._json(404,{'error':'not_found'})
            return self._json(200,payload)
        except PermissionError as exc:
            return self._json(403,{'error':str(exc) if str(exc) in {'family_access_required','family_owner_required','invalid_family_invite'} else 'family_access_required'})
        except (ValueError,TypeError,KeyError) as exc:
            # Known validation codes only; no user answers or provider details in logs.
            allowed={'invalid_language','lesson_not_found','invalid_answers','answer_all_questions',
                     'invalid_request_id','request_conflict','invalid_daily_minutes',
                     'invalid_target_dates','invalid_target_date','invalid_id','invalid_version',
                     'card_not_found','stale_review','card_not_due','invalid_rating','review_not_found',
                     'checkpoint_not_found','no_new_checkpoints','checkpoint_not_due','checkpoint_finished',
                     'invalid_family_account','diagnostic_incomplete','invalid_transcript','feedback_consent_required','invalid_scene','invalid_scene_time',
                     'invalid_scene_phrases','scene_not_found'}
            error=str(exc)
            return self._json(400,{'error':error if error in allowed else 'invalid_request'})
        except RuntimeError as exc:
            code=str(exc)
            if code in {'ai_not_configured','ai_unavailable','ai_invalid_response','feedback_rate_limited'}:
                return self._json(429 if code=='feedback_rate_limited' else 503,{'error':code})
            return self._json(500,{'error':'server_error'})
        except Exception as exc:
            print('[self-study]',type(exc).__name__,flush=True)
            return self._json(500,{'error':'server_error'})
