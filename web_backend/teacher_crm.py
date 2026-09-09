"""Teacher CRM read models and safe student profile mutations."""
from __future__ import annotations
from datetime import datetime, timedelta
from database import connect, get_user, now_iso
import education_profile
RATE_FIELDS={"ege_physics_rate","oge_physics_rate","oge_chemistry_rate","olympiad_physics_rate","school_physics_rate","school_chemistry_rate"}
PROFILE_FIELDS={"grade","study_goal","main_subject","phone","board_url","parent_name","parent_phone","education_type","education_level"}
EDITABLE_FIELDS=RATE_FIELDS|PROFILE_FIELDS

def _dict(row):return dict(row) if row else None
def _iso(value,fallback):
    if not value:return fallback
    try:return datetime.fromisoformat(str(value)).isoformat(timespec="seconds")
    except Exception:return fallback

def _education(x):
    p=education_profile.get(x);return {"education_type":p["type"],"education_level":p["level"],"education_label":p["label"]}

def schedule(start=None,end=None,limit=300):
    education_profile.initialize();now=datetime.now();monday=datetime.combine(now.date()-timedelta(days=now.weekday()),datetime.min.time());start=_iso(start,monday.isoformat(timespec="seconds"));end=_iso(end,(monday+timedelta(days=7)).isoformat(timespec="seconds"));limit=max(1,min(int(limit),500));conn=connect();rows=conn.execute("""SELECT l.id,l.user_id,l.start_time,l.end_time,l.duration_minutes,l.subject,l.study_goal,l.lesson_status,l.payment_status,l.price,l.started_at,l.finished_at,l.actual_duration_minutes,l.meeting_link_sent_at,u.name,u.grade,u.education_type,u.education_level,u.board_url FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.start_time>=? AND l.start_time<? ORDER BY l.start_time,l.id LIMIT ?""",(start,end,limit)).fetchall();conn.close();items=[]
    for r in rows:
        x=dict(r);x.update(_education(x));items.append(x)
    return {"start":start,"end":end,"items":items}

def students(search=None,status=None,limit=200):
    education_profile.initialize();now=datetime.now().isoformat(timespec="seconds");limit=max(1,min(int(limit),500));search=str(search or '').strip().lower();status=str(status or 'ALL').upper();conn=connect();rows=conn.execute("""
    SELECT u.id,u.name,u.grade,u.education_type,u.education_level,u.study_goal,u.main_subject,u.telegram_username,u.phone,u.board_url,
      MIN(CASE WHEN l.start_time>=? AND l.lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED') THEN l.start_time END) next_lesson,
      COUNT(DISTINCT CASE WHEN h.status IN ('ASSIGNED','SUBMITTED','UNDER_REVIEW','REVISION') THEN h.id END) homework_open,
      COUNT(DISTINCT CASE WHEN s.status='SUBMITTED' THEN s.id END) submissions_waiting,
      COALESCE((SELECT SUM(p.total_amount) FROM payments p WHERE p.user_id=u.id AND p.status IN ('WAITING','PENDING')),0) payment_waiting
    FROM users u LEFT JOIN lessons l ON l.user_id=u.id LEFT JOIN homework h ON h.user_id=u.id LEFT JOIN homework_submissions s ON s.user_id=u.id WHERE u.active=1 GROUP BY u.id ORDER BY u.name COLLATE NOCASE LIMIT ?
    """,(now,limit)).fetchall();conn.close();items=[]
    for row in rows:
        x=dict(row);x.update(_education(x));flags=[]
        if int(x['submissions_waiting'] or 0)>0:flags.append('REVIEW')
        if int(x['payment_waiting'] or 0)>0:flags.append('PAYMENT')
        if not x['next_lesson']:flags.append('NO_LESSON')
        if int(x['homework_open'] or 0)>0:flags.append('HOMEWORK')
        x['attention_flags']=flags;x['crm_status']='ATTENTION' if any(f in flags for f in ('REVIEW','PAYMENT','NO_LESSON')) else 'OK'
        hay=' '.join(str(x.get(k) or '').lower() for k in ('name','telegram_username','phone','study_goal','main_subject','grade','education_label'))
        if search and search not in hay:continue
        if status!='ALL' and status not in flags and status!=x['crm_status']:continue
        items.append(x)
    return {"items":items,"total":len(items)}

def student(user_id):
    education_profile.initialize();uid=int(user_id);user=get_user(uid)
    if not user:return None
    conn=connect();now=datetime.now().isoformat(timespec="seconds");stats=conn.execute("""SELECT (SELECT COUNT(*) FROM lessons WHERE user_id=? AND lesson_status='COMPLETED') lessons_completed,(SELECT COUNT(*) FROM homework WHERE user_id=? AND status IN ('ASSIGNED','SUBMITTED','UNDER_REVIEW','REVISION')) homework_open,(SELECT COUNT(*) FROM homework_submissions WHERE user_id=? AND status='SUBMITTED') submissions_waiting,(SELECT COALESCE(SUM(total_amount),0) FROM payments WHERE user_id=? AND status IN ('WAITING','PENDING')) payment_waiting""",(uid,uid,uid,uid)).fetchone();next_lesson=conn.execute("""SELECT id,start_time,end_time,duration_minutes,subject,study_goal,lesson_status,payment_status,price FROM lessons WHERE user_id=? AND start_time>=? AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED') ORDER BY start_time LIMIT 1""",(uid,now)).fetchone();recent=conn.execute("""SELECT id,start_time,duration_minutes,actual_duration_minutes,subject,study_goal,lesson_status,payment_status,price FROM lessons WHERE user_id=? ORDER BY start_time DESC LIMIT 8""",(uid,)).fetchall();conn.close();allowed=["id","name","grade","study_goal","main_subject","telegram_username","phone","board_url","parent_name","parent_phone","education_type","education_level","extra_minutes_balance","bonus_lessons_earned",*sorted(RATE_FIELDS)];profile={k:user[k] for k in allowed if k in user.keys()};profile.update(_education(user));return {"student":profile,"stats":dict(stats),"next_lesson":_dict(next_lesson),"recent_lessons":[dict(r) for r in recent]}

def update_student(user_id,fields):
    education_profile.initialize();uid=int(user_id);user=get_user(uid)
    if not user:return {"status":"student_not_found"}
    fields=fields or {}
    etype=str(fields.get('education_type') or (user['education_type'] if 'education_type' in user.keys() else 'SCHOOL') or 'SCHOOL').upper();level=fields.get('education_level')
    if level not in (None,''):
        try:level=int(level)
        except Exception:return {"status":"invalid_education_level"}
        try:education_profile.set_profile(uid,etype,level)
        except ValueError:return {"status":"invalid_education_level"}
        user=get_user(uid)
    updates=[];params=[]
    for key,raw in fields.items():
        if key in {'education_type','education_level','grade'}:continue
        if key not in EDITABLE_FIELDS or key not in user.keys():continue
        value=raw
        if key in RATE_FIELDS:
            if value in (None,''):value=None
            else:
                try:value=int(value)
                except Exception:return {"status":"invalid_rate","field":key}
                if value<0 or value>100000:return {"status":"invalid_rate","field":key}
        else:value=str(value or '').strip() or None
        updates.append(f"{key}=?");params.append(value)
    if updates:
        if 'updated_at' in user.keys():updates.append('updated_at=?');params.append(now_iso())
        params.append(uid);conn=connect();conn.execute(f"UPDATE users SET {','.join(updates)} WHERE id=?",params);conn.commit();conn.close()
    return {"status":"ok","changed":1 if updates or level not in (None,'') else 0,"student":student(uid)["student"]}
