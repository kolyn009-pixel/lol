"""Own-account language entry, never resolves by name or exposes family reports."""
from web_backend import self_study_access as access


def identities(telegram_id):
 import database
 if type(telegram_id) is not int or telegram_id<=0:return []
 result=[]
 if access.is_manager(telegram_id):result.append({'role':'teacher','account_id':telegram_id,'owner_id':telegram_id})
 for role,getter in [('student','get_user_by_telegram_id'),('parent','get_parent_by_telegram_id')]:
  lookup=getattr(database,getter,None);account=lookup(telegram_id) if lookup else None
  if account and account['active'] and access.is_member(int(account['id']),role):
   result.append({'role':role,'account_id':int(account['id']),'owner_id':access.study_identity(role,int(account['id']))})
 return result


def entry(telegram_id,role=None,view='today'):
 choices=identities(telegram_id)
 if not choices:return {'status':'denied','text':'Семейный доступ к языкам ещё не активирован. Войди в свой кабинет и открой персональное приглашение.'}
 if role is None and len(choices)>1:return {'status':'choose','roles':[x['role'] for x in choices],'text':'Выбери свой языковой профиль: результаты ролей хранятся отдельно.'}
 identity=next((x for x in choices if x['role']==role),None) if role else choices[0]
 if not identity:return {'status':'denied','text':'Этот языковой профиль недоступен.'}
 return entry_identity(identity,view)


def entry_identity(identity,view='today'):
 role=identity['role'];account_id=identity['account_id']
 if role=='teacher':
  if not access.is_manager(account_id):return {'status':'denied','text':'Языковой профиль недоступен.'}
 elif role not in ('student','parent') or not access.is_member(account_id,role):return {'status':'denied','text':'Языковой профиль недоступен.'}
 owner=account_id if role=='teacher' else access.study_identity(role,account_id)
 url='https://adeliatutor.ru/app/teacher.html?study=1' if role=='teacher' else 'https://adeliatutor.ru/app/self-study.html'+('?role=parent' if role=='parent' else '')
 from web_backend.self_study_placement import status
 placement=status(owner)
 if placement['pending']:text='Сначала пройди стартовые проверки выбранных языков в своём кабинете.'
 else:
  from web_backend.self_study import overview
  state=overview(owner);lines=[]
  for code,spec in state['profile']['languages'].items():
   if view=='cards':
    from web_backend.self_study_practice import practice
    p=practice(owner,code);lines.append(spec['name']+': к повторению '+str(p['due'])+' карточек.')
   else:lines.append(spec['name']+': '+str(spec['minutes'])+' мин по твоему бюджету.')
  text='\n'.join(lines)+'\nОткрой кабинет, чтобы продолжить. Пропуски не создают долгов.'
 return {'status':'ready','role':role,'url':url,'login_callback':{'teacher':'web_teacher_code','student':'web_student_code','parent':'web_parent_code'}[role],'text':text}
