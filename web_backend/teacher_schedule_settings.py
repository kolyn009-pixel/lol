"""Teacher availability settings shared by web and desktop clients.

Weekly working hours define self-bookable time. Date exceptions let the teacher
close a whole day or an interval. Existing lessons are never silently moved or
deleted: affected students are notified and can either reschedule or cancel.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
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
    from web_backend import teacher_day_off_state
    marked=teacher_day_off_state.mark_lessons(int(item_id),[int(x["id"]) for x in affected])
    delivery=_notify_affected(affected)
    return {"status":"ok","exception_id":int(item_id),"date":day,"whole_day":whole_day,"start_time":start,"end_time":end,"affected_lessons":affected,"affected_count":len(affected),"marked_lessons":marked,"notifications":delivery,"student_choices":["RESCHEDULE","CANCEL"],"existing_lessons_changed":False}


def remove_day_off(exception_id):
    exception_id=int(exception_id);rows={int(x["id"]):x for x in _exceptions()}
    if exception_id not in rows:raise ValueError("exception_not_found")
    database.delete_schedule_exception(exception_id);return {"status":"ok","exception_id":exception_id}


def _zone(name):
    value=str(name or "").strip()[:80]
    try:return value,ZoneInfo(value)
    except ZoneInfoNotFoundError:raise ValueError("invalid_timezone")


def booking_paused():
    return str(database.get_setting("teacher_schedule_booking_paused","0") or "0").lower() in {"1","true","on","yes"}


def _pending_timezone():
    if str(database.get_setting("teacher_timezone_change_pending","0") or "0").lower() not in {"1","true","on","yes"}:return None
    value=database.get_setting("teacher_timezone_pending",None)
    return str(value) if value else None


def _anchor_monday(tz):
    today=datetime.now(tz).date()
    return today-timedelta(days=today.weekday())


def _convert_weekly_item(weekday,start_time,end_time,old_tz,new_tz,anchor):
    day=anchor+timedelta(days=int(weekday))
    sh,sm=[int(x) for x in str(start_time)[:5].split(":")]
    eh,em=[int(x) for x in str(end_time)[:5].split(":")]
    start=datetime(day.year,day.month,day.day,sh,sm,tzinfo=old_tz).astimezone(new_tz)
    end=datetime(day.year,day.month,day.day,eh,em,tzinfo=old_tz).astimezone(new_tz)
    return {
        "weekday":int(start.weekday()),
        "start_time":start.strftime("%H:%M"),
        "end_time":end.strftime("%H:%M"),
        "end_weekday":int(end.weekday()),
        "crosses_day":start.date()!=end.date(),
        "offset":start.strftime("%z"),
    }


def _regular_preview(old_tz,new_tz,anchor):
    conn=database.connect()
    try:rows=conn.execute("""SELECT rs.id,rs.user_id,rs.weekday,rs.start_time,rs.duration_minutes,rs.status,u.name AS student_name FROM regular_schedules rs JOIN users u ON u.id=rs.user_id WHERE COALESCE(rs.active,1)=1 AND COALESCE(rs.status,'APPROVED') NOT IN ('CANCELLED','REJECTED') ORDER BY rs.weekday,rs.start_time,rs.id""").fetchall()
    finally:conn.close()
    out=[]
    for row in rows:
        day=anchor+timedelta(days=int(row["weekday"]))
        hh,mm=[int(x) for x in str(row["start_time"])[:5].split(":")]
        old_start=datetime(day.year,day.month,day.day,hh,mm,tzinfo=old_tz)
        new_start=old_start.astimezone(new_tz)
        out.append({
            "id":int(row["id"]),
            "student_id":int(row["user_id"]),
            "student_name":row["student_name"],
            "status":str(row["status"] or "APPROVED"),
            "duration_minutes":int(row["duration_minutes"] or 60),
            "old_weekday":int(row["weekday"]),
            "old_start_time":str(row["start_time"])[:5],
            "new_weekday":int(new_start.weekday()),
            "new_start_time":new_start.strftime("%H:%M"),
            "new_offset":new_start.strftime("%z"),
        })
    return out


def preview_timezone_change(timezone_name):
    current_name,current_tz=_zone(database.get_setting("bot_timezone","Europe/Samara") or "Europe/Samara")
    target_name,target_tz=_zone(timezone_name)
    anchor=_anchor_monday(current_tz)
    converted=[]
    for row in _rows():
        item=_convert_weekly_item(row["weekday"],row["start_time"],row["end_time"],current_tz,target_tz,anchor)
        converted.append({**row,"local":item})
    conn=database.connect()
    try:
        future=conn.execute("""SELECT COUNT(*) n FROM lessons WHERE start_time>=? AND lesson_status NOT IN ('CANCELLED','REJECTED')""",(datetime.now().isoformat(timespec="seconds"),)).fetchone()
    finally:conn.close()
    return {
        "status":"ok",
        "current_timezone":current_name,
        "timezone":target_name,
        "anchor_week_start":anchor.isoformat(),
        "items":converted,
        "regular_schedules":_regular_preview(current_tz,target_tz,anchor),
        "existing_future_lessons":int((future["n"] if future else 0) or 0),
        "existing_lessons_changed":False,
        "booking_paused":booking_paused(),
    }


def begin_timezone_change(payload):
    target=str(payload.get("timezone") or "").strip()
    preview=preview_timezone_change(target)
    database.set_setting("teacher_timezone_change_pending","1")
    database.set_setting("teacher_timezone_pending",preview["timezone"])
    database.set_setting("teacher_timezone_change_started_at",database.now_iso())
    database.set_setting("teacher_schedule_booking_paused","1")
    preview["pending"]=True
    preview["booking_paused"]=True
    return preview


def cancel_timezone_change():
    database.delete_setting("teacher_timezone_change_pending")
    database.delete_setting("teacher_timezone_pending")
    database.delete_setting("teacher_timezone_change_started_at")
    database.set_setting("teacher_schedule_booking_paused","0")
    result=snapshot();result["status"]="ok";result["timezone_change_cancelled"]=True;return result


def _upsert_setting(conn,key,value,now):
    conn.execute("""INSERT INTO bot_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",(str(key),None if value is None else str(value),now))


def _normalize_regular_edits(conn,items):
    if not isinstance(items,list):raise ValueError("invalid_regular_schedule_edits")
    rows=conn.execute("""SELECT id,weekday,start_time,duration_minutes FROM regular_schedules WHERE COALESCE(active,1)=1 AND COALESCE(status,'APPROVED') NOT IN ('CANCELLED','REJECTED') ORDER BY id""").fetchall()
    expected={int(row["id"]):row for row in rows}
    if len(items)!=len(expected):raise ValueError("regular_schedule_edits_incomplete")
    normalized=[];seen=set()
    for raw in items:
        if not isinstance(raw,dict):raise ValueError("invalid_regular_schedule_edit")
        rid=int(raw.get("id"))
        if rid not in expected or rid in seen:raise ValueError("invalid_regular_schedule_id")
        seen.add(rid);weekday=int(raw.get("weekday"));start=_time(raw.get("start_time"))
        if weekday<0 or weekday>6:raise ValueError("invalid_weekday")
        normalized.append({"id":rid,"weekday":weekday,"start_time":start,"duration_minutes":int(expected[rid]["duration_minutes"] or 60)})
    if seen!=set(expected):raise ValueError("regular_schedule_edits_incomplete")
    buckets={}
    for row in normalized:buckets.setdefault(row["weekday"],[]).append(row)
    for bucket in buckets.values():
        ordered=sorted(bucket,key=lambda r:_minutes(r["start_time"]))
        for left,right in zip(ordered,ordered[1:]):
            if _minutes(right["start_time"]) < _minutes(left["start_time"])+int(left["duration_minutes"]):raise ValueError("regular_schedule_overlap")
    return normalized


def _apply_regular_edits(conn,items,now):
    changed=0
    for row in items:
        current=conn.execute("SELECT weekday,start_time FROM regular_schedules WHERE id=?",(int(row["id"]),)).fetchone()
        if not current:raise ValueError("regular_schedule_not_found")
        new_time=str(row["start_time"])[:5]
        if int(current["weekday"])!=int(row["weekday"]) or str(current["start_time"])[:5]!=new_time:
            conn.execute("UPDATE regular_schedules SET weekday=?,start_time=?,updated_at=? WHERE id=?",(int(row["weekday"]),new_time,now,int(row["id"])))
            changed+=1
    return changed


def commit_timezone_change(payload):
    pending=_pending_timezone()
    if not pending:raise ValueError("timezone_change_not_pending")
    target_name,target_tz=_zone(payload.get("timezone") or pending)
    if target_name!=pending:raise ValueError("timezone_mismatch")
    current_name,current_tz=_zone(database.get_setting("bot_timezone","Europe/Samara") or "Europe/Samara")
    mode=str(payload.get("mode") or "SAME").upper()
    if mode not in MODES:raise ValueError("invalid_week_mode")
    rows=_normalize_rows(payload.get("items") or [],mode)
    now=database.now_iso();conn=database.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        regular_edits=_normalize_regular_edits(conn,payload.get("regular_schedules") or [])
        conn.execute("UPDATE working_hours SET active=0,updated_at=? WHERE active=1",(now,))
        for row in rows:conn.execute("""INSERT INTO working_hours(weekday,start_time,end_time,active,created_at,updated_at,week_type) VALUES(?,?,?,?,?,?,?)""",(row["weekday"],row["start_time"],row["end_time"],1,now,now,row["week_type"]))
        regular_changed=_apply_regular_edits(conn,regular_edits,now)
        _upsert_setting(conn,"teacher_week_mode",mode,now)
        _upsert_setting(conn,"bot_timezone",target_name,now)
        _upsert_setting(conn,"teacher_schedule_booking_paused","0",now)
        conn.execute("DELETE FROM bot_settings WHERE key IN ('teacher_timezone_change_pending','teacher_timezone_pending','teacher_timezone_change_started_at')")
        conn.commit()
    except Exception:conn.rollback();raise
    finally:conn.close()
    result=snapshot();result.update({"status":"ok","timezone_changed":True,"previous_timezone":current_name,"regular_schedules_updated":regular_changed,"existing_lessons_changed":False,"saved_at":datetime.now().isoformat(timespec="seconds")});return result


def snapshot():
    mode=str(database.get_setting("teacher_week_mode","SAME") or "SAME").upper()
    if mode not in MODES:mode="SAME"
    rows=_rows();pending=_pending_timezone()
    result={"timezone":str(database.get_setting("bot_timezone","Europe/Samara") or "Europe/Samara"),"mode":mode,"items":rows,"exceptions":_exceptions(),"warnings":_warnings(rows,mode),"booking_paused":booking_paused(),"timezone_change":{"pending":bool(pending),"pending_timezone":pending,"started_at":database.get_setting("teacher_timezone_change_started_at",None)}}
    if pending:
        try:result["timezone_change"]["preview"]=preview_timezone_change(pending)
        except Exception:result["timezone_change"]["preview"]=None
    return result


def replace(payload):
    if not isinstance(payload,dict):raise ValueError("invalid_payload")
    action=str(payload.get("action") or "").strip().lower()
    if action=="preview_exception":return preview_day_off(payload)
    if action=="add_exception":return add_day_off(payload)
    if action=="remove_exception":return remove_day_off(payload.get("exception_id"))
    if action=="preview_timezone":return preview_timezone_change(payload.get("timezone"))
    if action=="begin_timezone_change":return begin_timezone_change(payload)
    if action=="cancel_timezone_change":return cancel_timezone_change()
    if action=="commit_timezone_change":return commit_timezone_change(payload)
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
