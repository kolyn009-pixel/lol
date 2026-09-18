"""Adelia lesson access integration with Yandex Telemost."""
from __future__ import annotations
import database
from integrations.telemost_lifecycle import ensure_individual_conference, create_conference, finish_individual_conference
from web_backend import lesson_workspace, group_lesson_access, group_portal, attendance_tracking, telemost_settings, lesson_link_delivery

def _now(): return database.now_iso()
def _meeting_disabled():return {'status':'disabled_by_teacher','conference_id':None,'join_url':None,'reused':False}
def _access_revoked(conference_id):
    return {'status':'access_revoked','conference_id':str(conference_id or '').strip() or None,'provider_ended':False}
def start_individual(lesson_id):
    lid=int(lesson_id)
    c=database.connect();row=c.execute('SELECT l.*,u.board_url FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?',(lid,)).fetchone();c.close()
    if not row:return {'status':'not_found','lesson_id':lid}
    status=str(row['lesson_status'] or '').upper()
    if status in {'CANCELLED','REJECTED','NO_SHOW','LATE_CANCELLED','SICKNESS','COMPLETED'} or row['finished_at']:
        return {'status':'invalid_status','lesson_id':lid,'lesson_status':status}
    payment=str(row['payment_status'] or '').upper()
    paid=bool(row['is_trial']) or payment in {'PAID','FREE','RESERVED_BALANCE','WAIVED','COVERED'}
    if not paid:return {'status':'payment_required','lesson_id':lid,'payment_status':payment}
    meeting=ensure_individual_conference(lid) if telemost_settings.auto_on_start() else _meeting_disabled();opened=_now()
    if meeting.get('status') not in {'ok','disabled','disabled_by_teacher'}:raise RuntimeError('telemost_create_failed')
    c=database.connect();c.execute('UPDATE lessons SET meeting_link_sent_at=COALESCE(meeting_link_sent_at,?),updated_at=? WHERE id=?',(opened,opened,lid));c.commit();row=c.execute('SELECT l.started_at,l.lesson_status,l.meeting_link_sent_at,l.meeting_url,u.board_url FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?',(lid,)).fetchone();c.close()
    delivery=None
    if meeting.get('status')=='ok':
        try:delivery=lesson_link_delivery.send_individual(lid)
        except Exception as exc:delivery={'status':'failed','error':str(exc)[:120]}
    return {'status':'opened','lesson_id':lid,'opened_at':row['meeting_link_sent_at'] if row else opened,'started_at':row['started_at'] if row else None,'lesson_status':row['lesson_status'] if row else None,'meeting_url':row['meeting_url'] if row and meeting.get('status')=='ok' else None,'board_url':row['board_url'] if row else None,'telemost':meeting,'delivery':delivery}
def finish_individual(lesson_id,attendance_status='PRESENT',tutor_comment=None,mode='NOW'):
    lid=int(lesson_id);result=lesson_workspace.finish_lesson(lid,attendance_status,tutor_comment,mode);telemost={'status':'not_finished'}
    if result.get('status')=='ok':
        if result.get('already_finished'):
            telemost={'status':'already_finished'}
        else:
            telemost=finish_individual_conference(lid)
        c=database.connect();c.execute('UPDATE lessons SET meeting_link_sent_at=NULL,meeting_url=NULL,updated_at=? WHERE id=?',(_now(),lid));c.commit();c.close()
    return {**result,'telemost':telemost}
def individual_student_access(lesson_id,user_id):
    lid=int(lesson_id);uid=int(user_id);c=database.connect();row=c.execute('SELECT l.id,l.user_id,l.lesson_status,l.payment_status,l.is_trial,l.started_at,l.finished_at,l.meeting_link_sent_at,l.meeting_url,u.board_url FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?',(lid,)).fetchone();c.close()
    if not row or int(row['user_id'])!=uid:raise PermissionError('lesson_access_denied')
    payment=str(row['payment_status'] or '').upper();paid=bool(row['is_trial']) or payment in {'PAID','FREE','RESERVED_BALANCE','WAIVED','COVERED'}
    visible=bool(paid and row['meeting_link_sent_at'] and not row['finished_at'] and str(row['lesson_status'] or '').upper() not in {'CANCELLED','REJECTED','NO_SHOW','LATE_CANCELLED','SICKNESS','COMPLETED'})
    return {'lesson_id':lid,'links_visible':visible,'payment_required':not paid,'payment_status':row['payment_status'],'meeting_url':row['meeting_url'] if visible else None,'board_url':row['board_url'],'lesson_status':row['lesson_status'],'started_at':row['started_at']}
def start_group(lesson_id,teacher_id):
    lid=int(lesson_id);preview=group_lesson_access.teacher_start_preview(lid)
    if preview['unresolved']:raise ValueError('group_lesson_has_unresolved_admissions')
    admitted=[p for p in preview['participants'] if p['admission_status']=='ADMITTED' and str(p.get('rsvp_status') or 'UNKNOWN').upper()!='NOT_GOING' and int(p.get('financial_attention') or 0)==0];minimum=max(2,int(preview['lesson']['min_attendees'] or 2))
    if len(admitted)<minimum:raise ValueError('group_lesson_quorum_not_met')
    c=database.connect();row=c.execute('SELECT telemost_conference_id,telemost_join_url FROM group_lessons WHERE id=?',(lid,)).fetchone();c.close()
    if row and row['telemost_conference_id'] and row['telemost_join_url']:meeting={'status':'ok','conference_id':row['telemost_conference_id'],'join_url':row['telemost_join_url'],'reused':True}
    elif telemost_settings.auto_on_start():
        meeting=create_conference()
        if meeting.get('status')=='ok':
            c=database.connect();c.execute('UPDATE group_lessons SET telemost_conference_id=?,telemost_join_url=?,updated_at=? WHERE id=?',(meeting['conference_id'],meeting['join_url'],_now(),lid));c.commit();c.close();meeting['reused']=False
    else:meeting=_meeting_disabled()
    result=group_lesson_access.start_group_lesson(lid,int(teacher_id));delivery=None
    if meeting.get('status')=='ok':
        try:delivery=lesson_link_delivery.send_group(lid)
        except Exception as exc:delivery={'status':'failed','error':str(exc)[:120]}
    return {**result,'telemost':meeting,'delivery':delivery}
def finish_group(lesson_id):
    lid=int(lesson_id);c=database.connect();row=c.execute('SELECT status,telemost_conference_id FROM group_lessons WHERE id=?',(lid,)).fetchone();c.close()
    if not row:raise ValueError('group_lesson_not_found')
    for item in attendance_tracking.roster('GROUP_LESSON',lid):
        if item['attendance']['present']:attendance_tracking.record('GROUP_LESSON',lid,int(item['user_id']),'LEAVE',source='SYSTEM')
    telemost=_access_revoked(row['telemost_conference_id']);now=_now();c=database.connect();c.execute("UPDATE group_lessons SET status='COMPLETED',telemost_join_url=NULL,updated_at=? WHERE id=?",(now,lid));c.execute('UPDATE group_lesson_participants SET access_granted=0,updated_at=? WHERE lesson_id=?',(now,lid));c.commit();c.close();return {'status':'completed','lesson_id':lid,'telemost':telemost}
def start_open_event(event_id):
    eid=int(event_id);c=database.connect();row=c.execute('SELECT telemost_conference_id,telemost_join_url,board_url FROM open_learning_events WHERE id=?',(eid,)).fetchone();c.close()
    if not row:raise ValueError('event_not_found')
    if row['telemost_conference_id'] and row['telemost_join_url']:meeting={'status':'ok','conference_id':row['telemost_conference_id'],'join_url':row['telemost_join_url'],'reused':True}
    elif telemost_settings.auto_on_start():
        meeting=create_conference()
        if meeting.get('status')=='ok':
            c=database.connect();c.execute('UPDATE open_learning_events SET telemost_conference_id=?,telemost_join_url=?,updated_at=? WHERE id=?',(meeting['conference_id'],meeting['join_url'],_now(),eid));c.commit();c.close();meeting['reused']=False
    else:meeting=_meeting_disabled()
    result=group_portal.start_open_event(eid,meeting.get('join_url'),row['board_url']);delivery=None
    if meeting.get('status')=='ok':
        try:delivery=lesson_link_delivery.send_open_event(eid)
        except Exception as exc:delivery={'status':'failed','error':str(exc)[:120]}
    return {**result,'telemost':meeting,'delivery':delivery}
def finish_open_event(event_id):
    eid=int(event_id);c=database.connect();row=c.execute('SELECT id,telemost_conference_id FROM open_learning_events WHERE id=?',(eid,)).fetchone();c.close()
    if not row:raise ValueError('event_not_found')
    telemost=_access_revoked(row['telemost_conference_id']);now=_now();c=database.connect();c.execute("UPDATE open_learning_events SET status='COMPLETED',telemost_join_url=NULL,updated_at=? WHERE id=?",(now,eid));c.execute('UPDATE open_event_participants SET access_granted=0,updated_at=? WHERE event_id=?',(now,eid));c.commit();c.close();return {'status':'completed','event_id':eid,'telemost':telemost}
