"""Stage 8 pricing core.

Prices are resolved at booking/quote time. Existing lesson.price values are never
rewritten when a tariff changes, so historical accounting stays immutable.
"""
from __future__ import annotations
import json
from database import connect, now_iso, get_user

TARIFF_KEYS={
    'SCHOOL_PHYSICS','SCHOOL_CHEMISTRY','OGE_PHYSICS','OGE_CHEMISTRY',
    'EGE_PHYSICS','OLYMPIAD_PHYSICS','COLLEGE_PHYSICS'
}
LEGACY_RATE_FIELDS={
    'SCHOOL_PHYSICS':'school_physics_rate',
    'SCHOOL_CHEMISTRY':'school_chemistry_rate',
    'OGE_PHYSICS':'oge_physics_rate',
    'OGE_CHEMISTRY':'oge_chemistry_rate',
    'EGE_PHYSICS':'ege_physics_rate',
    'OLYMPIAD_PHYSICS':'olympiad_physics_rate',
}


def ensure_tables():
    conn=connect();conn.executescript("""
    CREATE TABLE IF NOT EXISTS price_catalog(
      tariff_key TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      subject TEXT NOT NULL,
      education_type TEXT NOT NULL,
      study_goal TEXT,
      amount INTEGER NOT NULL,
      currency TEXT NOT NULL DEFAULT 'RUB',
      duration_minutes INTEGER NOT NULL DEFAULT 60,
      active INTEGER NOT NULL DEFAULT 1,
      updated_at TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS student_price_overrides(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      tariff_key TEXT NOT NULL,
      amount INTEGER NOT NULL,
      active INTEGER NOT NULL DEFAULT 1,
      note TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT,
      UNIQUE(user_id,tariff_key),
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS package_plans(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT NOT NULL UNIQUE,
      title TEXT NOT NULL,
      lessons_count INTEGER NOT NULL,
      discount_percent REAL NOT NULL DEFAULT 0,
      fixed_total INTEGER,
      tariff_key TEXT,
      active INTEGER NOT NULL DEFAULT 1,
      sort_order INTEGER NOT NULL DEFAULT 100,
      created_at TEXT NOT NULL,
      updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS pricing_history(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      entity_type TEXT NOT NULL,
      entity_key TEXT NOT NULL,
      old_value TEXT,
      new_value TEXT,
      changed_at TEXT NOT NULL,
      source TEXT NOT NULL DEFAULT 'WEB'
    );
    CREATE INDEX IF NOT EXISTS idx_student_price_override ON student_price_overrides(user_id,tariff_key,active);
    CREATE INDEX IF NOT EXISTS idx_package_active ON package_plans(active,sort_order,id);
    """);conn.commit();conn.close()


def _money(value):
    try:value=int(value)
    except Exception:raise ValueError('invalid_amount')
    if value<0 or value>1_000_000:raise ValueError('invalid_amount')
    return value


def _key(value):
    key=str(value or '').strip().upper()
    if key not in TARIFF_KEYS:raise ValueError('invalid_tariff_key')
    return key


def _history(kind,key,old,new,source='WEB'):
    conn=connect();conn.execute('INSERT INTO pricing_history(entity_type,entity_key,old_value,new_value,changed_at,source) VALUES(?,?,?,?,?,?)',(kind,str(key),json.dumps(old,ensure_ascii=False) if old is not None else None,json.dumps(new,ensure_ascii=False) if new is not None else None,now_iso(),source));conn.commit();conn.close()


def list_prices():
    ensure_tables();conn=connect();rows=conn.execute('SELECT * FROM price_catalog ORDER BY education_type,subject,study_goal,tariff_key').fetchall();conn.close();return [dict(r) for r in rows]


def set_price(tariff_key,amount,title=None,subject=None,education_type=None,study_goal=None,duration_minutes=60,active=True,source='WEB'):
    ensure_tables();key=_key(tariff_key);amount=_money(amount);duration=int(duration_minutes or 60)
    if duration<15 or duration>300:raise ValueError('invalid_duration')
    conn=connect();old=conn.execute('SELECT * FROM price_catalog WHERE tariff_key=?',(key,)).fetchone();now=now_iso()
    if old:
        previous=dict(old);conn.execute('UPDATE price_catalog SET amount=?,title=COALESCE(?,title),subject=COALESCE(?,subject),education_type=COALESCE(?,education_type),study_goal=?,duration_minutes=?,active=?,updated_at=? WHERE tariff_key=?',(amount,title,subject,education_type,study_goal,duration,1 if active else 0,now,key))
    else:
        previous=None
        defaults={
          'SCHOOL_PHYSICS':('Школьная физика','PHYSICS','SCHOOL',None),'SCHOOL_CHEMISTRY':('Школьная химия','CHEMISTRY','SCHOOL',None),
          'OGE_PHYSICS':('ОГЭ по физике','PHYSICS','SCHOOL','OGE'),'OGE_CHEMISTRY':('ОГЭ по химии','CHEMISTRY','SCHOOL','OGE'),
          'EGE_PHYSICS':('ЕГЭ по физике','PHYSICS','SCHOOL','EGE'),'OLYMPIAD_PHYSICS':('Олимпиадная физика','PHYSICS','SCHOOL','OLYMPIAD'),
          'COLLEGE_PHYSICS':('Физика — колледж','PHYSICS','COLLEGE','COLLEGE')}
        d=defaults[key];conn.execute('INSERT INTO price_catalog(tariff_key,title,subject,education_type,study_goal,amount,duration_minutes,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(key,title or d[0],subject or d[1],education_type or d[2],study_goal if study_goal is not None else d[3],amount,duration,1 if active else 0,now,now))
    conn.commit();row=dict(conn.execute('SELECT * FROM price_catalog WHERE tariff_key=?',(key,)).fetchone());conn.close();_history('CATALOG',key,previous,row,source);return {'status':'ok','price':row}


def list_overrides(user_id=None):
    ensure_tables();conn=connect();params=[];where=''
    if user_id is not None:where=' WHERE o.user_id=? ';params.append(int(user_id))
    rows=conn.execute('SELECT o.*,u.name FROM student_price_overrides o JOIN users u ON u.id=o.user_id'+where+' ORDER BY u.name,o.tariff_key',params).fetchall();conn.close();return [dict(r) for r in rows]


def set_override(user_id,tariff_key,amount,note=None,active=True,source='WEB'):
    ensure_tables();uid=int(user_id);key=_key(tariff_key);amount=_money(amount);user=get_user(uid)
    if not user:raise ValueError('student_not_found')
    conn=connect();old=conn.execute('SELECT * FROM student_price_overrides WHERE user_id=? AND tariff_key=?',(uid,key)).fetchone();now=now_iso()
    if old:conn.execute('UPDATE student_price_overrides SET amount=?,note=?,active=?,updated_at=? WHERE user_id=? AND tariff_key=?',(amount,str(note or '').strip() or None,1 if active else 0,now,uid,key))
    else:conn.execute('INSERT INTO student_price_overrides(user_id,tariff_key,amount,active,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(uid,key,amount,1 if active else 0,str(note or '').strip() or None,now,now))
    conn.commit();row=dict(conn.execute('SELECT * FROM student_price_overrides WHERE user_id=? AND tariff_key=?',(uid,key)).fetchone());conn.close();_history('STUDENT_OVERRIDE',f'{uid}:{key}',dict(old) if old else None,row,source);return {'status':'ok','override':row}


def delete_override(user_id,tariff_key,source='WEB'):
    ensure_tables();uid=int(user_id);key=_key(tariff_key);conn=connect();old=conn.execute('SELECT * FROM student_price_overrides WHERE user_id=? AND tariff_key=?',(uid,key)).fetchone();conn.execute('DELETE FROM student_price_overrides WHERE user_id=? AND tariff_key=?',(uid,key));conn.commit();conn.close();_history('STUDENT_OVERRIDE',f'{uid}:{key}',dict(old) if old else None,None,source);return {'status':'ok'}


def _legacy_rate(user,key):
    field=LEGACY_RATE_FIELDS.get(key)
    if not field or field not in user.keys():return None
    try:v=user[field]
    except Exception:return None
    return int(v) if v not in (None,'') else None


def quote(user_id,tariff_key,duration_minutes=60):
    """Resolve a price without mutating any existing lesson/payment rows."""
    ensure_tables();uid=int(user_id);key=_key(tariff_key);user=get_user(uid)
    if not user:raise ValueError('student_not_found')
    duration=int(duration_minutes or 60)
    conn=connect();override=conn.execute('SELECT amount FROM student_price_overrides WHERE user_id=? AND tariff_key=? AND active=1',(uid,key)).fetchone();catalog=conn.execute('SELECT amount,duration_minutes FROM price_catalog WHERE tariff_key=? AND active=1',(key,)).fetchone();conn.close()
    if override:base=int(override['amount']);source='STUDENT_OVERRIDE';base_duration=60
    elif catalog:base=int(catalog['amount']);source='CATALOG';base_duration=int(catalog['duration_minutes'] or 60)
    else:
        legacy=_legacy_rate(user,key)
        if legacy is None:raise ValueError('price_not_configured')
        base=int(legacy);source='LEGACY_USER_RATE';base_duration=60
    total=round(base*duration/base_duration)
    return {'status':'ok','user_id':uid,'tariff_key':key,'amount':int(total),'currency':'RUB','duration_minutes':duration,'source':source,'base_amount':base,'base_duration_minutes':base_duration}


def list_packages():
    ensure_tables();conn=connect();rows=conn.execute('SELECT * FROM package_plans ORDER BY active DESC,sort_order,id').fetchall();conn.close();return [dict(r) for r in rows]


def save_package(code,title,lessons_count,discount_percent=0,fixed_total=None,tariff_key=None,active=True,sort_order=100,source='WEB'):
    ensure_tables();code=str(code or '').strip().upper().replace(' ','_')
    if not code:raise ValueError('code_required')
    count=int(lessons_count)
    if count<2 or count>100:raise ValueError('invalid_lessons_count')
    discount=float(discount_percent or 0)
    if discount<0 or discount>80:raise ValueError('invalid_discount')
    fixed=_money(fixed_total) if fixed_total not in (None,'') else None
    key=_key(tariff_key) if tariff_key else None;now=now_iso();conn=connect();old=conn.execute('SELECT * FROM package_plans WHERE code=?',(code,)).fetchone()
    if old:conn.execute('UPDATE package_plans SET title=?,lessons_count=?,discount_percent=?,fixed_total=?,tariff_key=?,active=?,sort_order=?,updated_at=? WHERE code=?',(str(title or '').strip() or code,count,discount,fixed,key,1 if active else 0,int(sort_order or 100),now,code))
    else:conn.execute('INSERT INTO package_plans(code,title,lessons_count,discount_percent,fixed_total,tariff_key,active,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(code,str(title or '').strip() or code,count,discount,fixed,key,1 if active else 0,int(sort_order or 100),now,now))
    conn.commit();row=dict(conn.execute('SELECT * FROM package_plans WHERE code=?',(code,)).fetchone());conn.close();_history('PACKAGE',code,dict(old) if old else None,row,source);return {'status':'ok','package':row}


def package_quote(user_id,code,tariff_key=None,duration_minutes=60):
    ensure_tables();conn=connect();p=conn.execute('SELECT * FROM package_plans WHERE code=? AND active=1',(str(code).strip().upper(),)).fetchone();conn.close()
    if not p:raise ValueError('package_not_found')
    key=tariff_key or p['tariff_key']
    if not key:raise ValueError('tariff_required')
    one=quote(user_id,key,duration_minutes)
    total=int(p['fixed_total']) if p['fixed_total'] is not None else round(one['amount']*int(p['lessons_count'])*(1-float(p['discount_percent'] or 0)/100))
    return {'status':'ok','code':p['code'],'title':p['title'],'lessons_count':int(p['lessons_count']),'lesson_amount':one['amount'],'total_amount':int(total),'discount_percent':float(p['discount_percent'] or 0),'tariff_key':one['tariff_key'],'currency':'RUB','source':one['source']}


def history(limit=200):
    ensure_tables();conn=connect();rows=conn.execute('SELECT * FROM pricing_history ORDER BY id DESC LIMIT ?',(max(1,min(int(limit),1000)),)).fetchall();conn.close();return [dict(r) for r in rows]
