"""Compatibility layer keeping Web individual prices in sync with TutorBot.

TutorBot historically stores a custom hourly rate both in users.*_rate fields and
in student_programs.custom_hourly_rate. Stage 8 adds tariff-specific Web overrides.
These helpers make all three views converge so Telegram/VK/Web quote the same rate.
"""
from __future__ import annotations
from database import connect, now_iso, get_user
from web_backend import finance_pricing as pricing


def _meta(tariff_key):
    key=str(tariff_key or '').strip().upper()
    if key not in pricing.TARIFF_META:raise ValueError('invalid_tariff_key')
    title,subject,education,goal,gmin,gmax=pricing.TARIFF_META[key]
    return key,subject,education,goal


def _legacy_column(key):
    return pricing.LEGACY_RATE_FIELDS.get(key)


def _sync_program(uid,goal,subject,amount):
    conn=connect();now=now_iso()
    rows=conn.execute("SELECT id FROM student_programs WHERE user_id=? AND study_goal=? AND subject=? AND active=1",(uid,goal,subject)).fetchall()
    for row in rows:conn.execute("UPDATE student_programs SET custom_hourly_rate=?,updated_at=? WHERE id=?",(amount,now,int(row['id'])))
    conn.commit();conn.close();return len(rows)


def _clear_program(uid,goal,subject):
    conn=connect();now=now_iso();cur=conn.execute("UPDATE student_programs SET custom_hourly_rate=NULL,updated_at=? WHERE user_id=? AND study_goal=? AND subject=? AND active=1",(now,uid,goal,subject));conn.commit();count=int(cur.rowcount or 0);conn.close();return count


def set_override(user_id,tariff_key,amount,note=None,active=True,source='WEB'):
    uid=int(user_id);key,subject,education,goal=_meta(tariff_key);amount=int(amount)
    result=pricing.set_override(uid,key,amount,note,active,source)
    user=get_user(uid)
    if not user:return result
    conn=connect();now=now_iso();column=_legacy_column(key)
    if column and column in user.keys():conn.execute(f"UPDATE users SET {column}=?,updated_at=? WHERE id=?",(amount,now,uid))
    conn.commit();conn.close()
    _sync_program(uid,goal,subject,amount)
    result['synced']={'legacy_user_rate':bool(column),'student_programs':True}
    return result


def delete_override(user_id,tariff_key,source='WEB'):
    uid=int(user_id);key,subject,education,goal=_meta(tariff_key);result=pricing.delete_override(uid,key,source);user=get_user(uid)
    conn=connect();now=now_iso();column=_legacy_column(key)
    if user and column and column in user.keys():conn.execute(f"UPDATE users SET {column}=NULL,updated_at=? WHERE id=?",(now,uid))
    conn.commit();conn.close();_clear_program(uid,goal,subject);result['synced']={'legacy_user_rate':bool(column),'student_programs':True};return result


def quote(user_id,tariff_key=None,duration_minutes=60,study_goal=None,subject=None,grade=None,education_type=None):
    """Resolve Web price, falling back to TutorBot program custom rate before defaults."""
    uid=int(user_id);key=pricing._key(tariff_key) if tariff_key else pricing.tariff_for(uid,study_goal,subject,grade,education_type)
    try:
        q=pricing.quote(uid,key,duration_minutes,study_goal,subject,grade,education_type)
        # Existing Web override is already strongest and must win.
        if q.get('source')=='STUDENT_OVERRIDE':return q
    except ValueError as exc:
        if str(exc)!='price_not_configured':raise
        q=None
    _,subj,edu,goal=_meta(key);conn=connect();program=conn.execute("SELECT custom_hourly_rate FROM student_programs WHERE user_id=? AND study_goal=? AND subject=? AND active=1 AND approval_status='APPROVED' AND custom_hourly_rate IS NOT NULL ORDER BY is_primary DESC,id LIMIT 1",(uid,goal,subj)).fetchone();conn.close()
    if program:
        base=int(program['custom_hourly_rate']);duration=int(duration_minutes or 60);return {'status':'ok','user_id':uid,'tariff_key':key,'amount':round(base*duration/60),'currency':'RUB','duration_minutes':duration,'source':'STUDENT_PROGRAM','base_amount':base,'base_duration_minutes':60}
    if q is not None:return q
    return pricing.quote(uid,key,duration_minutes,study_goal,subject,grade,education_type)


def package_quote(user_id,code,tariff_key=None,duration_minutes=60):
    pricing.ensure_tables();conn=connect();p=conn.execute('SELECT * FROM package_plans WHERE code=? AND active=1',(str(code).strip().upper(),)).fetchone();conn.close()
    if not p:raise ValueError('package_not_found')
    key=tariff_key or p['tariff_key'];one=quote(user_id,key,duration_minutes) if key else quote(user_id,None,duration_minutes);total=int(p['fixed_total']) if p['fixed_total'] is not None else round(one['amount']*int(p['lessons_count'])*(1-float(p['discount_percent'] or 0)/100));return {'status':'ok','code':p['code'],'title':p['title'],'lessons_count':int(p['lessons_count']),'lesson_amount':one['amount'],'total_amount':int(total),'discount_percent':float(p['discount_percent'] or 0),'tariff_key':one['tariff_key'],'currency':'RUB','source':one['source']}
