"""Teacher-created individual lesson booking using canonical TutorBot lesson lifecycle."""
from __future__ import annotations

from datetime import datetime, timedelta
from core.lesson_time import lesson_timezone, schedule_datetime

import database
from integrations.lesson_sync import sync_lesson
from web_backend import push_events


_ALLOWED_PAYMENT_MODES = {"AWAITING_PAYMENT", "BALANCE", "FREE"}


def _student(user_id: int):
    user = database.get_user(int(user_id))
    if not user:
        raise ValueError("student_not_found")
    return user


def create(user_id, start_time, duration_minutes=60, payment_mode="AWAITING_PAYMENT", program_id=None, topic="", formula_id=None):
    uid = int(user_id)
    user = _student(uid)

    program=None
    if program_id is not None:
        program=next((p for p in database.get_student_programs(uid,active_only=True,approved_only=True) if int(p['id'])==int(program_id)),None)
        if not program:raise ValueError('program_not_found')
    topic=str(topic or '').strip()
    if len(topic)>180:raise ValueError('topic_too_long')
    if formula_id:
        from web_backend.formula_book import formula_detail
        formula=formula_detail(int(formula_id))
        if not formula:raise ValueError('formula_not_found')
        if program and formula['subject']!=program['subject']:raise ValueError('formula_program_mismatch')
    study_goal = str((program['study_goal'] if program else user["study_goal"]) or "SCHOOL").upper()
    subject = str((program["subject"] if program else user["main_subject"]) or "PHYSICS").upper()

    try:
        start = schedule_datetime(str(start_time or "").strip()).replace(tzinfo=None)
    except Exception as exc:
        raise ValueError("invalid_start_time") from exc

    now = datetime.now(lesson_timezone()).replace(tzinfo=None)
    if start < now - timedelta(minutes=5):
        raise ValueError("start_time_in_past")

    duration = int(duration_minutes or 60)
    if duration < 30 or duration > 240:
        raise ValueError("invalid_duration")

    mode = str(payment_mode or "AWAITING_PAYMENT").upper()
    if mode not in _ALLOWED_PAYMENT_MODES:
        raise ValueError("invalid_payment_mode")

    rate = int(database.get_program_rate_info(program["id"])["effective_rate"]) if program else int(database.get_student_rate(uid, study_goal, subject))
    price = int(database.calculate_lesson_price(rate, duration))
    end = start + timedelta(minutes=duration)

    # A retry after a lost response must open the existing lesson, not add it again.
    c=database.connect()
    try:
        prior=c.execute("SELECT id FROM lessons WHERE user_id=? AND start_time=? AND duration_minutes=? AND study_goal=? AND subject=? AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED') ORDER BY id DESC LIMIT 1",(uid,start.isoformat(timespec='seconds'),duration,study_goal,subject)).fetchone()
    finally:c.close()
    if prior:return {'status':'ok','lesson_id':int(prior['id']),'already_created':True}
    from web_backend import learning_tools
    learning_tools.ensure_tables()
    lesson_id = int(database.create_admin_lesson(
        uid,
        study_goal,
        subject,
        start.isoformat(timespec="seconds"),
        end.isoformat(timespec="seconds"),
        duration,
        rate,
        price,
        payment_mode=mode,
        is_trial=False,
    ))

    c=database.connect()
    try:
        if topic or formula_id:c.execute('INSERT INTO learning_lesson_topics(lesson_id,topic,formula_id) VALUES(?,?,?)',(lesson_id,topic,int(formula_id) if formula_id else None))
        if program and any(r['name']=='program_id' for r in c.execute('PRAGMA table_info(lessons)')):c.execute('UPDATE lessons SET program_id=? WHERE id=?',(int(program['id']),lesson_id))
        c.commit()
    finally:c.close()
    try:
        integrations = sync_lesson(lesson_id)
    except Exception as exc:
        integrations = {
            "google": {"status": "error", "error": type(exc).__name__},
            "telemost": {"status": "error", "error": type(exc).__name__},
        }

    payment_text = {
        "AWAITING_PAYMENT": "Оплата ожидается до занятия.",
        "BALANCE": "Минуты будут списаны из баланса по правилам TutorBot.",
        "FREE": "Занятие отмечено как бесплатное.",
    }[mode]
    when = start.strftime("%d.%m в %H:%M")
    delivery = push_events.student_and_parents(
        uid,
        "🗓️ Новое занятие в расписании",
        f"Преподаватель записал занятие на {when}. {payment_text}",
        f"/app/lesson/?id={lesson_id}",
        "/app/parent/",
        f"teacher-manual-booking-{lesson_id}",
        {"type": "schedule", "lesson_id": lesson_id, "reason": "teacher_manual_booking"},
        mirror_messengers=True,
    )

    lesson = database.get_lesson(lesson_id)
    return {
        "status": "ok",
        "lesson_id": lesson_id,
        "lesson": dict(lesson) if lesson else None,
        "hourly_rate": rate,
        "price": price,
        "payment_mode": mode,
        "integrations": integrations,
        "delivery": delivery,
    }



def options(user_id):
    uid=int(user_id);_student(uid)
    programs=[]
    for row in database.get_student_programs(uid,active_only=True,approved_only=True):
        rate=int(database.get_program_rate_info(row['id'])['effective_rate'])
        programs.append({'id':int(row['id']),'subject':row['subject'],'study_goal':row['study_goal'],'hourly_rate':rate})
    return {'programs':programs,'schedule_timezone':str(lesson_timezone())}
