"""Stage 8 pricing core integrated with TutorBot's existing pricing model.

The website can edit tariffs, but lesson rows remain immutable snapshots: changing
a tariff never rewrites historical lesson.price/hourly_rate values.
"""
from __future__ import annotations
import json
from database import connect, now_iso, get_user

TARIFF_META={
 'SCHOOL_PHYSICS_5_8':('Школьная физика · 5–8 класс','PHYSICS','SCHOOL','SCHOOL',5,8),
 'SCHOOL_PHYSICS_9_11':('Школьная физика · 9–11 класс','PHYSICS','SCHOOL','SCHOOL',9,11),
 'SCHOOL_CHEMISTRY_5_8':('Школьная химия · 5–8 класс','CHEMISTRY','SCHOOL','SCHOOL',5,8),
 'SCHOOL_CHEMISTRY_9_11':('Школьная химия · 9–11 класс','CHEMISTRY','SCHOOL','SCHOOL',9,11),
 'OGE_PHYSICS':('ОГЭ · физика','PHYSICS','SCHOOL','OGE',8,9),
 'OGE_CHEMISTRY':('ОГЭ · химия','CHEMISTRY','SCHOOL','OGE',8,9),
 'EGE_PHYSICS':('ЕГЭ · физика','PHYSICS','SCHOOL','EGE',10,11),
 'OLYMPIAD_PHYSICS':('Олимпиадная физика','PHYSICS','SCHOOL','OLYMPIAD',None,None),
 'COLLEGE_PHYSICS':('Колледж · физика','PHYSICS','COLLEGE','COLLEGE',None,None),
}
TARIFF_KEYS=set(TARIFF_META)
LEGACY_RATE_FIELDS={
 'SCHOOL_PHYSICS_5_8':'school_physics_rate','SCHOOL_PHYSICS_9_11':'school_physics_rate',
 'SCHOOL_CHEMISTRY_5_8':'school_chemistry_rate','SCHOOL_CHEMISTRY_9_11':'school_chemistry_rate',
 'OGE_PHYSICS':'oge_physics_rate','OGE_CHEMISTRY':'oge_chemistry_rate',
 'EGE_PHYSICS':'ege_physics_rate','OLYMPIAD_PHYSICS':'olympiad_physics_rate',
}

def ensure_tables():
 conn=connect();conn.executescript("""
 CREATE TABLE IF NOT EXISTS price_catalog(tariff_key TEXT PRIMARY KEY,title TEXT NOT NULL,subject TEXT NOT NULL,education_type TEXT NOT NULL,study_goal TEXT,amount INTEGER NOT NULL,currency TEXT NOT NULL DEFAULT 'RUB',duration_minutes INTEGER NOT NULL DEFAULT 60,active INTEGER NOT NULL DEFAULT 1,updated_at TEXT,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS student_price_overrides(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,tariff_key TEXT NOT NULL,amount INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1,note TEXT,created_at TEXT NOT NULL,updated_at TEXT,UNIQUE(user_id,tariff_key),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
 CREATE TABLE IF NOT EXISTS package_plans(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT NOT NULL UNIQUE,title TEXT NOT NULL,lessons_count INTEGER NOT NULL,discount_percent REAL NOT NULL DEFAULT 0,fixed_total INTEGER,tariff_key TEXT,active INTEGER NOT NULL DEFAULT 1,sort_order INTEGER NOT NULL DEFAULT 100,created_at TEXT NOT NULL,updated_at TEXT);
 CREATE TABLE IF NOT EXISTS pricing_history(id INTEGER PRIMARY KEY AUTOINCREMENT,entity_type TEXT NOT NULL,entity_key TEXT NOT NULL,old_value TEXT,new_value TEXT,changed_at TEXT NOT NULL,source TEXT NOT NULL DEFAULT 'WEB');
 CREATE INDEX IF NOT EXISTS idx_student_price_override ON student_price_overrides(user_id,tariff_key,active);
 CREATE INDEX IF NOT EXISTS idx_package_active ON package_plans(active,sort_order,id);
 """)
 try:rows=conn.execute('SELECT rate_key,hourly_rate,title,subject,study_goal,active FROM price_settings').fetchall()
 except Exception:rows=[]
 now=now_iso()
 for r in rows:
  key=str(r['rate_key'] or '').upper()
  if key not in TARIFF_KEYS:continue
  meta=TARIFF_META[key]
  conn.execute("INSERT OR IGNORE INTO price_catalog(tariff_key,title,subject,education_type,study_goal,amount,duration_minutes,active,created_at,updated_at) VALUES(?,?,?,?,?,?,60,?,?,?)",(key,r['title'] or meta[0],r['subject'] or meta[1],meta[2],r['study_goal'] or meta[3],int(r['hourly_rate'] or 0),int(r['active'] if r['active'] is not None else 1),now,now))
 conn.commit();conn.close()

def _money(v):
 try:v=int(v)
 except Exception:raise ValueError('invalid_amount')
 if v<=0 or v>1_000_000:raise ValueError('invalid_amount')
 return v

def _key(v):
 k=str(v or '').strip().upper()
 if k not in TARIFF_KEYS:raise ValueError('invalid_tariff_key')
 return k

def _history(kind,key,old,new,source='WEB'):
 conn=connect();conn.execute('INSERT INTO pricing_history(entity_type,entity_key,old_value,new_value,changed_at,source) VALUES(?,?,?,?,?,?)',(kind,str(key),json.dumps(old,ensure_ascii=False) if old is not None else None,json.dumps(new,ensure_ascii=False) if new is not None else None,now_iso(),source));conn.commit();conn.close()

def list_prices():
 ensure_tables();conn=connect();rows=conn.execute('SELECT * FROM price_catalog WHERE tariff_key IN (%s)'%(','.join('?' for _ in TARIFF_KEYS)),tuple(sorted(TARIFF_KEYS))).fetchall();found={r['tariff_key']:dict(r) for r in rows};conn.close()
 # Return all supported tariff slots even before a price is configured. This is
 # especially important for college physics, which has no legacy default rate.
 out=[]
 for key,meta in TARIFF_META.items():
  out.append(found.get(key) or {'tariff_key':key,'title':meta[0],'subject':meta[1],'education_type':meta[2],'study_goal':meta[3],'amount':None,'currency':'RUB','duration_minutes':60,'active':0,'configured':False})
 return out

def set_price(tariff_key,amount,title=None,subject=None,education_type=None,study_goal=None,duration_minutes=60,active=True,source='WEB'):
 ensure_tables();key=_key(tariff_key);amount=_money(amount);duration=int(duration_minutes or 60)
 if duration<15 or duration>300:raise ValueError('invalid_duration')
 meta=TARIFF_META[key];now=now_iso();conn=connect();old=conn.execute('SELECT * FROM price_catalog WHERE tariff_key=?',(key,)).fetchone();previous=dict(old) if old else None
 conn.execute("INSERT INTO price_catalog(tariff_key,title,subject,education_type,study_goal,amount,duration_minutes,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(tariff_key) DO UPDATE SET title=excluded.title,subject=excluded.subject,education_type=excluded.education_type,study_goal=excluded.study_goal,amount=excluded.amount,duration_minutes=excluded.duration_minutes,active=excluded.active,updated_at=excluded.updated_at",(key,title or meta[0],subject or meta[1],education_type or meta[2],study_goal if study_goal is not None else meta[3],amount,duration,1 if active else 0,now,now))
 if key!='COLLEGE_PHYSICS':
  try:
   cur=conn.execute('UPDATE price_settings SET hourly_rate=?,active=?,title=?,updated_at=? WHERE rate_key=?',(amount,1 if active else 0,title or meta[0],now,key))
   if cur.rowcount==0:conn.execute('INSERT OR IGNORE INTO price_settings(rate_key,study_goal,subject,grade_min,grade_max,hourly_rate,title,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(key,meta[3],meta[1],meta[4],meta[5],amount,title or meta[0],1 if active else 0,now,now))
  except Exception:pass
 conn.commit();row=dict(conn.execute('SELECT * FROM price_catalog WHERE tariff_key=?',(key,)).fetchone());conn.close();_history('CATALOG',key,previous,row,source);return {'status':'ok','price':row}

def list_overrides(user_id=None):
 ensure_tables();conn=connect();params=[];where=''
 if user_id is not None:where=' WHERE o.user_id=? ';params.append(int(user_id))
 rows=conn.execute('SELECT o.*,u.name FROM student_price_overrides o JOIN users u ON u.id=o.user_id'+where+' ORDER BY u.name,o.tariff_key',params).fetchall();conn.close();return [dict(r) for r in rows]

def set_override(user_id,tariff_key,amount,note=None,active=True,source='WEB'):
 ensure_tables();uid=int(user_id);key=_key(tariff_key);amount=_money(amount)
 if not get_user(uid):raise ValueError('student_not_found')
 conn=connect();old=conn.execute('SELECT * FROM student_price_overrides WHERE user_id=? AND tariff_key=?',(uid,key)).fetchone();now=now_iso();conn.execute("INSERT INTO student_price_overrides(user_id,tariff_key,amount,active,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,tariff_key) DO UPDATE SET amount=excluded.amount,active=excluded.active,note=excluded.note,updated_at=excluded.updated_at",(uid,key,amount,1 if active else 0,str(note or '').strip() or None,now,now));conn.commit();row=dict(conn.execute('SELECT * FROM student_price_overrides WHERE user_id=? AND tariff_key=?',(uid,key)).fetchone());conn.close();_history('STUDENT_OVERRIDE',f'{uid}:{key}',dict(old) if old else None,row,source);return {'status':'ok','override':row}

def delete_override(user_id,tariff_key,source='WEB'):
 ensure_tables();uid=int(user_id);key=_key(tariff_key);conn=connect();old=conn.execute('SELECT * FROM student_price_overrides WHERE user_id=? AND tariff_key=?',(uid,key)).fetchone();conn.execute('DELETE FROM student_price_overrides WHERE user_id=? AND tariff_key=?',(uid,key));conn.commit();conn.close();_history('STUDENT_OVERRIDE',f'{uid}:{key}',dict(old) if old else None,None,source);return {'status':'ok'}

def tariff_for(user_id,study_goal=None,subject=None,grade=None,education_type=None):
 user=get_user(int(user_id))
 if not user:raise ValueError('student_not_found')
 def val(name,default=None):return user[name] if name in user.keys() else default
 education=str(education_type or val('education_type','SCHOOL') or 'SCHOOL').upper();subject=str(subject or val('main_subject','PHYSICS') or 'PHYSICS').upper();goal=str(study_goal or val('study_goal','SCHOOL') or 'SCHOOL').upper();grade=int(grade or val('grade',11) or 11)
 if subject not in {'PHYSICS','CHEMISTRY'}:raise ValueError('subject_not_supported')
 if education=='COLLEGE':
  if subject!='PHYSICS':raise ValueError('college_subject_not_supported')
  course=val('course',None)
  if course not in (None,'') and int(course)>2:raise ValueError('physics_college_course_out_of_range')
  return 'COLLEGE_PHYSICS'
 if goal=='EGE':
  if subject!='PHYSICS':raise ValueError('ege_subject_not_supported')
  return 'EGE_PHYSICS'
 if goal=='OGE':return 'OGE_CHEMISTRY' if subject=='CHEMISTRY' else 'OGE_PHYSICS'
 if goal=='OLYMPIAD':
  if subject!='PHYSICS':raise ValueError('olympiad_subject_not_supported')
  return 'OLYMPIAD_PHYSICS'
 band='5_8' if grade<=8 else '9_11';return f'SCHOOL_{subject}_{band}'

def _legacy_rate(user,key):
 field=LEGACY_RATE_FIELDS.get(key)
 if not field or field not in user.keys():return None
 v=user[field];return int(v) if v not in (None,'') else None

def quote(user_id,tariff_key=None,duration_minutes=60,study_goal=None,subject=None,grade=None,education_type=None):
 ensure_tables();uid=int(user_id);user=get_user(uid)
 if not user:raise ValueError('student_not_found')
 key=_key(tariff_key) if tariff_key else tariff_for(uid,study_goal,subject,grade,education_type);duration=int(duration_minutes or 60);conn=connect();override=conn.execute('SELECT amount FROM student_price_overrides WHERE user_id=? AND tariff_key=? AND active=1',(uid,key)).fetchone();catalog=conn.execute('SELECT amount,duration_minutes FROM price_catalog WHERE tariff_key=? AND active=1',(key,)).fetchone();legacy_setting=conn.execute('SELECT hourly_rate FROM price_settings WHERE rate_key=? AND active=1',(key,)).fetchone() if key!='COLLEGE_PHYSICS' else None;conn.close()
 if override:base=int(override['amount']);source='STUDENT_OVERRIDE';base_duration=60
 elif catalog:base=int(catalog['amount']);source='CATALOG';base_duration=int(catalog['duration_minutes'] or 60)
 elif legacy_setting:base=int(legacy_setting['hourly_rate']);source='PRICE_SETTINGS';base_duration=60
 else:
  legacy=_legacy_rate(user,key)
  if legacy is None:raise ValueError('price_not_configured')
  base=legacy;source='LEGACY_USER_RATE';base_duration=60
 total=round(base*duration/base_duration);return {'status':'ok','user_id':uid,'tariff_key':key,'amount':int(total),'currency':'RUB','duration_minutes':duration,'source':source,'base_amount':base,'base_duration_minutes':base_duration}

def lesson_snapshot(user_id,duration_minutes,study_goal=None,subject=None,grade=None,education_type=None):
 q=quote(user_id,None,duration_minutes,study_goal,subject,grade,education_type);return {'hourly_rate':round(q['amount']*60/max(int(duration_minutes),1)),'price':q['amount'],'tariff_key':q['tariff_key'],'price_source':q['source']}

def list_packages():
 ensure_tables();conn=connect();rows=conn.execute('SELECT * FROM package_plans ORDER BY active DESC,sort_order,id').fetchall();conn.close();return [dict(r) for r in rows if not r['tariff_key'] or str(r['tariff_key']).upper() in TARIFF_KEYS]

def save_package(code,title,lessons_count,discount_percent=0,fixed_total=None,tariff_key=None,active=True,sort_order=100,source='WEB'):
 ensure_tables();code=str(code or '').strip().upper().replace(' ','_')
 if not code:raise ValueError('code_required')
 count=int(lessons_count);discount=float(discount_percent or 0)
 if count<2 or count>100:raise ValueError('invalid_lessons_count')
 if discount<0 or discount>80:raise ValueError('invalid_discount')
 fixed=_money(fixed_total) if fixed_total not in (None,'') else None;key=_key(tariff_key) if tariff_key else None;now=now_iso();conn=connect();old=conn.execute('SELECT * FROM package_plans WHERE code=?',(code,)).fetchone();conn.execute("INSERT INTO package_plans(code,title,lessons_count,discount_percent,fixed_total,tariff_key,active,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET title=excluded.title,lessons_count=excluded.lessons_count,discount_percent=excluded.discount_percent,fixed_total=excluded.fixed_total,tariff_key=excluded.tariff_key,active=excluded.active,sort_order=excluded.sort_order,updated_at=excluded.updated_at",(code,str(title or '').strip() or code,count,discount,fixed,key,1 if active else 0,int(sort_order or 100),now,now));conn.commit();row=dict(conn.execute('SELECT * FROM package_plans WHERE code=?',(code,)).fetchone());conn.close();_history('PACKAGE',code,dict(old) if old else None,row,source);return {'status':'ok','package':row}

def package_quote(user_id,code,tariff_key=None,duration_minutes=60):
 ensure_tables();conn=connect();p=conn.execute('SELECT * FROM package_plans WHERE code=? AND active=1',(str(code).strip().upper(),)).fetchone();conn.close()
 if not p:raise ValueError('package_not_found')
 key=tariff_key or p['tariff_key'];one=quote(user_id,key,duration_minutes) if key else quote(user_id,None,duration_minutes);total=int(p['fixed_total']) if p['fixed_total'] is not None else round(one['amount']*int(p['lessons_count'])*(1-float(p['discount_percent'] or 0)/100));return {'status':'ok','code':p['code'],'title':p['title'],'lessons_count':int(p['lessons_count']),'lesson_amount':one['amount'],'total_amount':int(total),'discount_percent':float(p['discount_percent'] or 0),'tariff_key':one['tariff_key'],'currency':'RUB','source':one['source']}

def history(limit=200):
 ensure_tables();conn=connect();rows=conn.execute('SELECT * FROM pricing_history ORDER BY id DESC LIMIT ?',(max(1,min(int(limit),1000)),)).fetchall();conn.close();return [dict(r) for r in rows]
