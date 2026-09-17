"""Teacher availability settings shared by web and desktop clients.

Weekly working hours define self-bookable time. Date exceptions let the teacher
close a whole day or an interval. Existing lessons are never silently moved or
deleted: affected students are notified and can either reschedule or cancel.
"""
from __future__ import annotations

from datetime import date, datetime
import re

import database

WEEK_TYPES={"ALL","ODD","EVEN"}
MODES={"SAME","ALTERNATING"}
_TIME_RE=re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _time(value):
    value=str(value or "").strip()[:5]
    if not _TIME_RE.fullmatch(value): raise ValueError("invalid_time")
    return value


def _minutes(value):
    hh,mm=value.split(":");return int(hh)*60+int(mm)


def _normalize_rows(rows,mode):
    if not isinstance(rows,list): raise ValueError("invalid_schedule")
    normalized=[]
    for raw in rows:
        if not isinstance(raw,dict): raise ValueError("invalid_schedule_row")
        weekday=int(raw.get("weekday"));week_type=str(raw.get("week_type") or "ALL").upper()
        if weekday<0 or weekday>6: raise ValueError("invalid_weekday")
        if week_type not in WEEK_TYPES: raise ValueError("invalid_week_type")
        if mode=="SAME" and week_type!="ALL": raise ValueError("alternating_row_in_same_mode")
        start=_time(raw.get("start_time"));end=_time(raw.get("end_time"))
        if _minutes(end)<=_minutes(start): raise ValueError("invalid_working_interval")
        normalized.append({"weekday":weekday,"week_type":week_type,"start_time":start,"end_time":end})
    buckets={}
    for row in normalized:buckets.setdefault((row["weekday"],row["week_type"]),[]).append(row)
    for bucket in buckets.values():
        ordered=sorted(bucket,key=lambda r:_minutes(r["start_time"]))
        for left,right in zip(ordered,ordered[1:]):
            if _minutes(right["start_time"])<_minutes(left["end_time"]): raise ValueError("working_hours_overlap")
    normalized.sort(key=lambda r:(r["week_type"],r["weekday"],r["start_time"]));return normalized


def _rows():
    result=[]
    for row in database.get_working_hours():
        d=dict(row);result.append({"id":int(d["id"]),"weekday":int(d["weekday"]),"week_type":str(d.get("week_type") or "ALL").upper(),"start_time":str(d["start_time"])[:5],"end_time":str(d["end_time"])[:5],"active":bool(d.get("active",1))})
    return result


def _warnings(rows,mode):
    conn=database.connect()
    try:regular=conn.execute("""SELECT rs.id,rs.user_id,rs.weekday,rs.start_time,rs.duration_minutes,u.name AS student_name FROM regular_schedules rs JOIN users u ON u.id=rs.user_id WHERE rs.active=1 AND COALESCE(rs.status,'APPROVED') NOT IN ('CANCELLED','REJECTED') ORDER BY rs.weekday,rs.start_time,rs.id""").fetchall()
    finally:conn.close()
    by_day={}
    for row in rows:by_day.setdefault((row["weekday"],row["week_type"]),[]).append(row)
    warnings=[]
    for item in regular:
        start=str(item["start_time"] or "")[:5]
        if not _TIME_RE.fullmatch(start):continue
        duration=int(item["duration_minutes"] or 60);s=_minutes(start);e=s+duration;week_types=["ALL"] if mode=="SAME" else ["ODD","EVEN"];missing=[]
        for wt in week_types:
            candidates=by_day.get((int(item["weekday"]),wt),[])
            if not any(_minutes(x["start_time"])<=s and _minutes(x["end_time"])>=e for x in candidates):missing.append(wt)
        if missing:warnings.append({"type":"regular_schedule_outside_working_hours","regular_schedule_id":int(item["id"]),"student_id":int(item["user_id"]),"student_name":item["student_name"],"weekday":int(item["weekday"]),"start_time":start,"duration_minutes":duration,"week_types":missing})
    return warnings


def _exceptions():return [dict(x) for x in database.get_schedule_exceptions()]


def _affected_lessons(day,start_time=None,end_time=None):
    conn=database.connect()
    try:rows=conn.execute("""SELECT l.id,l.user_id,l.start_time,l.end_time,l.lesson_status,l.subject,u.name AS student_name FROM lessons l JOIN users u ON u.id=l.user_id WHERE DATE(l.start_time)=? AND l.lesson_status='CONFIRMED' ORDER BY l.start_time,l.id""",(day,)).fetchall()
    finally:conn.close()
    if start_time is None:return [dict(x) for x in rows]
    s,e=_minutes(start_time),_minutes(end_time);result=[]
    for row in rows:
        d=dict(row);ls=datetime.fromisoformat(str(d["start_time"]));le=datetime.fromisoformat(str(d["end_time"]))
        if ls.hour*60+ls.minute<e and le.hour*60+le.minute>s:result.append(d)
    return result


def preview_day_off(payload):
    if not isinstance(payload,dict):raise ValueError("invalid_payload")
    try:day=date.fromisoformat(str(payload.get("date") or ""))
    except Exception:raise ValueError("invalid_date")
    if day<date.today():raise ValueError("date_in_past")
    whole_day=bool(payload.get("whole_day",False));start=end=None
    if not whole_day:
        start=_time(payload.get("start_time"));end=_time(payload.get("end_time"))
        if _minutes(end)<=_minutes(start):raise ValueError("invalid_closed_interval")
    affected=_affected_lessons(day.isoformat(),start,end)
    return {"status":"ok","preview":True,"date":day.isoformat(),"whole_day":whole_day,"start_time":start,"end_time":end,"affected_lessons":affected,"affected_count":len(affected),"student_choices":["RESCHEDULE","CANCEL"],"existing_lessons_changed":False}


def _notify_affected(affected):
    sent=failed=0
    try:from web_backend import push_events
    except Exception:return {"sent":0,"failed":len(affected)}
    for item in affected:
        try:
            start=datetime.fromisoformat(str(item["start_time"]));when=start.strftime("%d.%m в %H:%M");lid=int(item["id"]);uid=int(item["user_id"])
            body=f"Занятие {when} попало в выходной преподавателя. Выберите перенос на свободное время или отмените занятие."
            result=push_events.student_and_parents(uid,"🗓️ Нужно решить по занятию",body,f"/app/lesson/?id={lid}","/app/parent/",f"teacher-day-off-{lid}",{"type":"schedule","lesson_id":lid,"reason":"teacher_day_off","actions":["reschedule","cancel"]},mirror_messengers=True)
            sent+=int((result.get("student") or {}).get("sent") or 0)+int((result.get("parents") or {}).get("sent") or 0);failed+=int((result.get("student") or {}).get("failed") or 0)+int((result.get("parents") or {}).get("failed") or 0)
        except Exception:failed+=1
    return {"sent":sent,"failed":failed}


def add_day_off(payload):
    preview=preview_day_off(payload);day=preview["date"];start=preview["start_time"];end=preview["end_time"];whole_day=preview["whole_day"];affected=preview["affected_lessons"]
    item_id=database.add_schedule_exception(day,"CLOSED",start,end,str(payload.get("comment") or "").strip()[:300] or "Выходной преподавателя")
    delivery=_notify_affected(affected)
    return {"status":"ok","exception_id":int(item_id),"date":day,"whole_day":whole_day,"start_time":start,"end_time":end,"affected_lessons":affected,"affected_count":len(affected),"notifications":delivery,"student_choices":["RESCHEDULE","CANCEL"],"existing_lessons_changed":False}


def remove_day_off(exception_id):
    exception_id=int(exception_id);rows={int(x["id"]):x for x in _exceptions()}
    if exception_id not in rows:raise ValueError("exception_not_found")
    database.delete_schedule_exception(exception_id);return {"status":"ok","exception_id":exception_id}


def snapshot():
    mode=str(database.get_setting("teacher_week_mode","SAME") or "SAME").upper()
    if mode not in MODES:mode="SAME"
    rows=_rows();return {"timezone":str(database.get_setting("bot_timezone","Europe/Samara") or "Europe/Samara"),"mode":mode,"items":rows,"exceptions":_exceptions(),"warnings":_warnings(rows,mode)}


def replace(payload):
    if not isinstance(payload,dict):raise ValueError("invalid_payload")
    action=str(payload.get("action") or "").strip().lower()
    if action=="preview_exception":return preview_day_off(payload)
    if action=="add_exception":return add_day_off(payload)
    if action=="remove_exception":return remove_day_off(payload.get("exception_id"))
    mode=str(payload.get("mode") or "SAME").upper()
    if mode not in MODES:raise ValueError("invalid_week_mode")
    rows=_normalize_rows(payload.get("items") or [],mode);now=database.now_iso();conn=database.connect()
    try:
        conn.execute("BEGIN IMMEDIATE");conn.execute("UPDATE working_hours SET active=0,updated_at=? WHERE active=1",(now,))
        for row in rows:conn.execute("""INSERT INTO working_hours(weekday,start_time,end_time,active,created_at,updated_at,week_type) VALUES(?,?,?,?,?,?,?)""",(row["weekday"],row["start_time"],row["end_time"],1,now,now,row["week_type"]))
        conn.commit()
    except Exception:conn.rollback();raise
    finally:conn.close()
    database.set_setting("teacher_week_mode",mode);result=snapshot();result["status"]="ok";result["saved_at"]=datetime.now().isoformat(timespec="seconds");result["existing_lessons_changed"]=False;return result
