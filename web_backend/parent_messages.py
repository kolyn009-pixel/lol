"""Private parent–teacher conversations, one per linked child."""
from database import connect, now_iso
from web_backend import unified_messaging as um, message_media
from web_backend.parent_portal import _assert_link, linked_students

MAX_TEXT = 4000


def _conversation(parent_id, student_id):
    uid = _assert_link(parent_id, student_id)
    return um.conversation(uid, 'PARENT', int(parent_id))


def thread(parent_id, student_id, limit=100):
    conv = _conversation(parent_id, student_id)
    messages = list(reversed(um.history(conv['id'], limit)))
    # Return only the parent's own conversation, never the child's student chat.
    return {'conversation_id': int(conv['id']), 'items': messages}


def _attachment(parent_id, student_id, attachment):
    if not attachment:return None
    if not isinstance(attachment,dict):raise ValueError('invalid_attachment')
    meta=message_media.metadata(attachment.get('token'))
    if not meta or str(meta.get('participant_type')).upper()!='PARENT' or int(meta.get('participant_id') or 0)!=int(parent_id) or int(meta.get('student_id') or 0)!=int(student_id):
        raise ValueError('invalid_attachment')
    return {key:meta[key] for key in ('token','student_id','participant_type','participant_id','kind','name','mime','size','url')}


def send(parent_id, student_id, text, attachment=None):
    conv = _conversation(parent_id, student_id)
    body = str(text or '').strip()
    media=_attachment(parent_id,student_id,attachment)
    if (not body and not media) or len(body) > MAX_TEXT:
        raise ValueError('invalid_message')
    mid = um.record_message(int(student_id), 'IN', body,
                            participant_type='PARENT', participant_id=int(parent_id),
                            sender_type='PARENT', sender_id=int(parent_id), origin_channel='WEB',
                            content_type=media['kind'].upper() if media else 'TEXT', attachment=media)
    try:
        from web_backend import push_events
        push_events.teachers('💬 Сообщение родителя', 'Родитель написал в Аделии.',
                             '/teacher/', f'parent-message-{mid}',
                             {'type': 'message', 'conversation_id': int(conv['id'])})
    except Exception as exc:
        print('[parent-messages] teacher push:', type(exc).__name__, flush=True)
    return {'status': 'ok', 'conversation_id': int(conv['id']), 'message_id': mid}


def mark_parent_read(parent_id, student_id):
    conv = _conversation(parent_id, student_id)
    conn = connect()
    try:
        conn.execute("""UPDATE unified_messages SET read_at=COALESCE(read_at,?),
                        status=CASE WHEN status IN ('DELIVERED','SENT') THEN 'READ' ELSE status END
                        WHERE conversation_id=? AND direction='OUT' AND read_at IS NULL""",
                     (now_iso(), int(conv['id'])))
        conn.commit()
    finally:
        conn.close()
    return {'status': 'ok'}


def students(parent_id):
    return {'items': [{'id': row['id'], 'name': row['name']} for row in linked_students(parent_id)]}


def parent_target(conversation_id):
    um.ensure_tables()
    conn = connect()
    try:
        row = conn.execute("""SELECT c.student_id,c.participant_id
                              FROM unified_conversations c
                              JOIN parent_student_links l ON l.student_id=c.student_id AND l.parent_id=c.participant_id
                              JOIN parent_accounts p ON p.id=l.parent_id AND p.active=1
                              JOIN users u ON u.id=c.student_id AND u.active=1
                              WHERE c.id=? AND c.participant_type='PARENT'""",
                           (int(conversation_id),)).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError('parent_conversation_not_found')
    return {'student_id':int(row['student_id']),'parent_id':int(row['participant_id'])}


def send_teacher_to_parent(conversation_id, text, teacher_id, attachment=None):
    target=parent_target(conversation_id)
    body = str(text or '').strip()
    media=_attachment(target['parent_id'],target['student_id'],attachment)
    if (not body and not media) or len(body) > MAX_TEXT:
        raise ValueError('invalid_message')
    mid = um.record_message(target['student_id'], 'OUT', body,
                            participant_type='PARENT', participant_id=target['parent_id'],
                            sender_type='TEACHER', sender_id=teacher_id, origin_channel='WEB',
                            content_type=media['kind'].upper() if media else 'TEXT', attachment=media)
    try:
        from web_backend import web_push
        web_push.send('parent', target['parent_id'], '💬 Сообщение преподавателя',
                      'В Аделии есть новый ответ.', '/app/parent/',
                      f'parent-reply-{mid}', {'type': 'message', 'student_id': target['student_id']})
    except Exception as exc:
        print('[parent-messages] parent push:', type(exc).__name__, flush=True)
    return {'status': 'ok', 'message_id': mid, 'delivery_status': 'SENT'}
