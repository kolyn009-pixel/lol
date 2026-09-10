"""Student finance facade over TutorBot's canonical payment rules.

The web/PWA/desktop clients use the same prices, discounts, promo validation,
payment rows, receipt rows and minute balance as Telegram/VK.
"""
from __future__ import annotations
import base64,os,re,secrets
from pathlib import Path
import database,payments
from core import minute_balance,event_center
RECEIPT_ROOT=Path(os.environ.get('ADELIA_WEB_RECEIPT_DIR','/opt/tutorbot/data/web_receipts'));MAX_RECEIPT_BYTES=8*1024*1024
_ALLOWED={'image/jpeg':('.jpg','PHOTO'),'image/png':('.png','PHOTO'),'application/pdf':('.pdf','DOCUMENT')}
def _user(user_id):
 row=database.get_user(int(user_id))
 if not row:raise PermissionError('student_not_found')
 return row
def _payment_owned(user_id,payment_id):
 row=database.get_payment(int(payment_id))
 if not row or int(row['user_id'])!=int(user_id):raise PermissionError('payment_not_found')
 return row
def _safe_payment(row):
 keys=row.keys() if hasattr(row,'keys') else [];return {'id':int(row['id']),'status':row['status'],'payment_type':row['payment_type'] if 'payment_type' in keys else None,'total_amount':int(row['total_amount'] or 0),'lessons_count':int(row['lessons_count'] or 0),'minutes_total':int(row['minutes_total'] or 0) if 'minutes_total' in keys else 0,'base_duration_minutes':int(row['base_duration_minutes'] or 0) if 'base_duration_minutes' in keys else 0,'hourly_rate':int(row['hourly_rate'] or 0) if 'hourly_rate' in keys else 0,'discount_percent':int(row['discount_percent'] or 0),'promo_code':row['promo_code'],'promo_discount_amount':int(row['promo_discount_amount'] or 0),'study_goal':row['study_goal'],'subject':row['subject'],'lesson_id':int(row['lesson_id']) if 'lesson_id' in keys and row['lesson_id'] else None,'created_at':row['created_at'],'confirmed_at':row['confirmed_at'] if 'confirmed_at' in keys else None}
def overview(user_id):
 user=_user(user_id);options=payments.get_purchase_nominals(user);balances=database.get_balance_by_nominal(int(user_id))
 try:total=payments.get_balance_breakdown(user)
 except Exception:total=minute_balance.get_balance(int(user_id))
 tariffs=[]
 for key,item in options.items():
  bal=balances.get(key,{'paid':0,'bonus':0,'total':0});tariffs.append({'selection_key':int(key),'program_id':item.get('program_id'),'study_goal':item['study_goal'],'subject':item['subject'],'hourly_rate':int(item['hourly_rate']),'duration':int(item['duration']),'nominal':int(item['nominal']),'balance':dict(bal)})
 waiting=payments.get_waiting_payment(int(user_id));return {'balance':{'paid':int(total.get('paid',0)),'bonus':int(total.get('bonus',0)),'total':int(total.get('total',0))},'tariffs':tariffs,'waiting_payment':_safe_payment(waiting) if waiting else None,'payment_method':payments.payment_method_text(),'discounts':[{'min':1,'max':3,'percent':0},{'min':4,'max':5,'percent':5},{'min':6,'max':9,'percent':10},{'min':10,'max':50,'percent':15}]}
def quote(user_id,selection_key,lessons_count,promo_code=None):
 user=_user(user_id);count=int(lessons_count)
 if count<1 or count>50:raise ValueError('invalid_lessons_count')
 options=payments.get_purchase_nominals(user);item=options.get(int(selection_key))
 if item is None:raise ValueError('tariff_unavailable')
 promo=database.normalize_promo_code(promo_code) if promo_code else None;text,result=payments.build_calculation_text(user,count,promo,price_per_lesson=int(item['nominal']),programs_text=payments.nominal_programs_text(item),hourly_rate=int(item['hourly_rate']),base_duration=int(item['duration']),program_id=item.get('program_id'));return {'lessons_count':count,'minutes_total':count*int(item['duration']),'duration':int(item['duration']),'hourly_rate':int(item['hourly_rate']),'nominal':int(item['nominal']),'study_goal':item['study_goal'],'subject':item['subject'],'promo_code':promo,'discount_percent':int(result.get('discount_percent') or 0),'promo_discount_amount':int(result.get('promo_discount') or result.get('promo_discount_amount') or 0),'total_amount':int(result.get('final_total') or result.get('total_amount') or result.get('total') or 0),'display_text':text}
def create_package_payment(user_id,selection_key,lessons_count,promo_code=None):
 user=_user(user_id);waiting=payments.get_waiting_payment(int(user_id))
 if waiting is not None and str(waiting['status']).upper()=='RECEIPT_SENT':raise ValueError('receipt_already_under_review')
 count=int(lessons_count)
 if count<1 or count>50:raise ValueError('invalid_lessons_count')
 options=payments.get_purchase_nominals(user);item=options.get(int(selection_key))
 if item is None:raise ValueError('tariff_unavailable')
 promo=database.normalize_promo_code(promo_code) if promo_code else None
 if promo:
  validation=database.validate_promo_code(promo,int(user_id))
  if not validation['valid']:raise ValueError(validation['reason'])
 payment_id=database.create_payment(user_id=int(user_id),study_goal=item['study_goal'],subject=item['subject'],lessons_count=count,price_per_lesson=int(item['nominal']),promo_code=promo,minutes_total=count*int(item['duration']),base_duration_minutes=int(item['duration']),hourly_rate=int(item['hourly_rate']),program_id=item.get('program_id'));return {'status':'ok','payment':_safe_payment(database.get_payment(payment_id)),'payment_method':payments.payment_method_text()}
def create_lesson_payment(user_id,lesson_id,promo_code=None):
 lesson=payments.get_lesson_for_payment(int(lesson_id),int(user_id));promo=database.normalize_promo_code(promo_code) if promo_code else None
 if promo:
  validation=database.validate_promo_code(promo,int(user_id))
  if not validation['valid']:raise ValueError(validation['reason'])
 existing=database.get_payment_for_lesson(int(lesson_id));payment_id=int(existing['id']) if existing else int(database.create_lesson_payment(int(lesson_id),promo_code=promo));return {'status':'ok','payment':_safe_payment(database.get_payment(payment_id)),'payment_method':payments.payment_method_text(),'lesson_start':lesson['start_time']}
def history(user_id,limit=30):return [_safe_payment(row) for row in database.get_user_payments(int(user_id),max(1,min(int(limit),100))) if str(row['payment_type'] or '').upper()!='BONUS']
def attach_receipt(user_id,payment_id,filename,mime_type,content_b64):
 payment=_payment_owned(user_id,payment_id)
 if str(payment['status']).upper()=='PAID':raise ValueError('payment_already_paid')
 mime=str(mime_type or '').lower().strip()
 if mime not in _ALLOWED:raise ValueError('unsupported_receipt_type')
 try:raw=base64.b64decode(str(content_b64 or ''),validate=True)
 except Exception:raise ValueError('invalid_receipt_data') from None
 if not raw or len(raw)>MAX_RECEIPT_BYTES:raise ValueError('receipt_too_large')
 if mime=='application/pdf' and not raw.startswith(b'%PDF-'):raise ValueError('receipt_content_mismatch')
 if mime=='image/png' and not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('receipt_content_mismatch')
 if mime=='image/jpeg' and not raw.startswith(b'\xff\xd8\xff'):raise ValueError('receipt_content_mismatch')
 ext,file_type=_ALLOWED[mime];RECEIPT_ROOT.mkdir(parents=True,exist_ok=True);token=secrets.token_urlsafe(24);safe_name=re.sub(r'[^A-Za-z0-9._-]+','_',str(filename or 'receipt'))[:80];path=RECEIPT_ROOT/f'{int(user_id)}_{int(payment_id)}_{token}{ext}';path.write_bytes(raw)
 try:os.chmod(path,0o600)
 except OSError:pass
 receipt_id=database.add_receipt(payment_id=int(payment_id),user_id=int(user_id),file_id=str(path),file_type=file_type,source_platform='WEB')
 if receipt_id is not None:
  try:
   from web_backend import receipt_cloud_archive
   receipt_cloud_archive.enqueue(int(receipt_id))
  except Exception:pass
 user=_user(user_id)
 try:event_center.push('PAYMENT_RECEIPT',f"Новый чек: {user['name']}",f"Платёж #{int(payment_id)} · {int(payment['total_amount'] or 0):,} ₽".replace(',',' '),'ACTION','payment',int(payment_id),f'payment_receipt:{int(payment_id)}')
 except Exception:pass
 return {'status':'ok','payment_id':int(payment_id),'receipt_id':int(receipt_id) if receipt_id is not None else None,'filename':safe_name,'archive_status':'PENDING' if receipt_id is not None else 'UNTRACKED'}
