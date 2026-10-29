"""Explicit VK language commands; verified existing channel links, private peers only."""
import random
from web_backend.self_study_bot import entry_identity
from web_backend import self_study_access as access


def intercept(app,message):
 raw=str((message or {}).get('text') or '').strip().lower()
 parts=raw.split()
 if not parts or parts[0] not in ('/languages','/language_today','/language_cards'):return False
 sender=int(message.get('from_id') or 0);peer=int(message.get('peer_id') or sender)
 if sender<=0 or peer!=sender:return True
 from . import service,teacher_service
 choices=[];tid=teacher_service.is_teacher(sender)
 if tid and access.is_manager(int(tid)):choices.append({'role':'teacher','account_id':int(tid)})
 student=service.linked_user(sender)
 if student and student['active'] and access.is_member(int(student['id']),'student'):choices.append({'role':'student','account_id':int(student['id'])})
 requested=parts[1] if len(parts)>1 else None
 identity=next((x for x in choices if x['role']==requested),None) if requested else choices[0] if len(choices)==1 else None
 if not choices:text='Семейный языковой доступ для связанного профиля не активирован. Для родительского профиля используй сайт или Telegram: отдельной привязки родителей VK здесь пока нет.'
 elif not identity:text='Выбери свой профиль командой /languages teacher или /languages student.'
 else:
  result=entry_identity(identity,'cards' if parts[0]=='/language_cards' else 'today')
  text=result['text']+('\n'+result['url'] if result.get('url') else '')
 app.api('messages.send',peer_id=peer,random_id=random.randint(1,2000000000),message=text)
 return True
