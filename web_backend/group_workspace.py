"""Group settings and explicit teacher invitations; lesson payment remains separate."""
from __future__ import annotations
import secrets
from contextlib import contextmanager
from urllib.parse import urlencode
import database
from web_backend import group_lessons


@contextmanager
def connection():
    c = database.connect()
    try:
        with c:
            yield c
    finally:
        c.close()


def ensure_schema():
    group_lessons.ensure_schema()
    with connection() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS group_invite_links (
          group_id INTEGER PRIMARY KEY REFERENCES study_groups(id),
          token TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS group_invite_onboarding (
          onboarding_token TEXT PRIMARY KEY, invite_token TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS group_slot_windows (
          slot_id INTEGER PRIMARY KEY REFERENCES group_schedule_slots(id),
          starts_on TEXT NOT NULL, ends_on TEXT NOT NULL);
        ''')


def _group(c, gid):
    g = c.execute('SELECT * FROM study_groups WHERE id=? AND active=1', (int(gid),)).fetchone()
    if not g:
        raise ValueError('group_not_found')
    return dict(g)


def invitation(gid, rotate=False):
    ensure_schema()
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        _group(c, gid)
        if rotate:
            c.execute('DELETE FROM group_invite_links WHERE group_id=?', (int(gid),))
        c.execute('INSERT OR IGNORE INTO group_invite_links VALUES(?,?,?)',
                  (int(gid), secrets.token_urlsafe(32), database.now_iso()))
        token = c.execute('SELECT token FROM group_invite_links WHERE group_id=?', (int(gid),)).fetchone()['token']
    return '/app/group-invite.html?' + urlencode({'invite': token})


def preview(token):
    ensure_schema()
    from datetime import datetime
    from core.lesson_time import lesson_timezone
    today=datetime.now(lesson_timezone()).date().isoformat()
    with connection() as c:
        row = c.execute('SELECT group_id FROM group_invite_links WHERE token=?', (str(token),)).fetchone()
        if not row:
            raise ValueError('invite_not_found')
        g = _group(c, row['group_id'])
        count = c.execute("SELECT COUNT(*) FROM group_members WHERE group_id=? AND status IN ('ACTIVE','PAUSED')", (g['id'],)).fetchone()[0]
        slots = [dict(r) for r in c.execute('''SELECT s.weekday,s.start_time,s.duration_minutes,w.starts_on,w.ends_on
           FROM group_schedule_slots s LEFT JOIN group_slot_windows w ON w.slot_id=s.id
           WHERE s.group_id=? AND s.active=1 AND (w.ends_on IS NULL OR w.ends_on>=?) ORDER BY s.weekday,s.start_time''', (g['id'],today))]
    # Public invite responses contain no roster, board, or conference links.
    return {'group': {k:g[k] for k in ('id','name','subject','study_goal','description','price_per_lesson','recruitment_status')},
            'places_left': max(0, g['max_members']-count), 'slots':slots,'timezone':str(lesson_timezone())}


def join(token, uid):
    ensure_schema()
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT group_id FROM group_invite_links WHERE token=?', (str(token),)).fetchone()
        if not row:
            raise ValueError('invite_not_found')
        g = _group(c, row['group_id']); gid = g['id']
        user = c.execute('SELECT active FROM users WHERE id=?', (int(uid),)).fetchone()
        if not user or not user['active']:
            raise PermissionError('student_not_found')
        member = c.execute('SELECT status FROM group_members WHERE group_id=? AND user_id=?', (gid,int(uid))).fetchone()
        if not member or member['status'] not in ('ACTIVE','PAUSED'):
            if g['recruitment_status'] != 'OPEN':
                raise ValueError('group_recruitment_closed')
            count = c.execute("SELECT COUNT(*) FROM group_members WHERE group_id=? AND status IN ('ACTIVE','PAUSED')", (gid,)).fetchone()[0]
            if count >= g['max_members']:
                raise ValueError('group_full')
            now = database.now_iso()
            c.execute("""INSERT INTO group_members(group_id,user_id,status,joined_at,source)
                         VALUES(?,?,'ACTIVE',?,'TEACHER_INVITE') ON CONFLICT(group_id,user_id)
                         DO UPDATE SET status='ACTIVE',left_at=NULL,joined_at=excluded.joined_at,source=excluded.source""", (gid,int(uid),now))
            # New members also see already generated upcoming lessons, without paid access.
            for lesson in c.execute("SELECT id FROM group_lessons WHERE group_id=? AND start_time>=? AND status='SCHEDULED'", (gid,now)).fetchall():
                c.execute("""INSERT OR IGNORE INTO group_lesson_participants
                  (lesson_id,user_id,participation_kind,payment_status,access_granted,attendance_status,created_at,updated_at)
                  VALUES(?,?,'PERMANENT','PENDING',0,'EXPECTED',?,?)""", (lesson['id'],int(uid),now,now))
    return {'status':'ok','group_id':gid,'redirect':'/app/?group='+str(gid)}


def settings(gid):
    from web_backend import group_visuals
    group_visuals.ensure_schema()
    ensure_schema()
    group = group_lessons.get_group(int(gid))
    if not group['active']:
        raise ValueError('group_not_found')
    # Do not send contacts or identities in the roster unnecessarily.
    with connection() as c:
        avatars={r['user_id']:dict(r) for r in c.execute('SELECT p.user_id,p.avatar_kind,p.avatar_value FROM student_social_profiles p JOIN group_members m ON m.user_id=p.user_id WHERE m.group_id=?',(int(gid),))}
    group['members'] = [{**{k:r.get(k) for k in ('user_id','name','status')},**avatars.get(r['user_id'],{})} for r in group['members']]
    from core.lesson_time import lesson_timezone
    with connection() as c:
        windows={r['slot_id']:dict(r) for r in c.execute('SELECT w.* FROM group_slot_windows w JOIN group_schedule_slots s ON s.id=w.slot_id WHERE s.group_id=?',(int(gid),))}
    for slot in group['slots']:
        slot.update(windows.get(slot['id'],{}))
    from datetime import datetime
    today=datetime.now(lesson_timezone()).date().isoformat()
    group['slots']=[s for s in group['slots'] if not s.get('ends_on') or s['ends_on']>=today]
    return {'group':group, 'invite_path':invitation(gid), 'timezone':str(lesson_timezone())}


def update(gid, body):
    ensure_schema()
    name = str(body.get('name') or '').strip()
    price = int(body.get('price_per_lesson',0)); cap = int(body.get('max_members',8)); minimum = int(body.get('min_attendees',2))
    recruitment = str(body.get('recruitment_status','OPEN')); chat = str(body.get('chat_mode','OPEN'))
    board = str(body.get('board_url') or '').strip()
    if not 2 <= len(name) <= 100: raise ValueError('group_name_required')
    if price < 0: raise ValueError('invalid_group_price')
    if not 2 <= minimum <= cap <= 100: raise ValueError('invalid_max_members')
    if recruitment not in group_lessons.VALID_RECRUITMENT: raise ValueError('invalid_recruitment_status')
    if chat not in group_lessons.VALID_CHAT_MODE: raise ValueError('invalid_chat_mode')
    if board and not board.startswith('https://'): raise ValueError('invalid_board_url')
    with connection() as c:
        c.execute('BEGIN IMMEDIATE'); _group(c,gid)
        count = c.execute("SELECT COUNT(*) FROM group_members WHERE group_id=? AND status IN ('ACTIVE','PAUSED')", (int(gid),)).fetchone()[0]
        if cap < count: raise ValueError('capacity_below_members')
        c.execute('''UPDATE study_groups SET name=?,description=?,price_per_lesson=?,max_members=?,min_attendees=?,recruitment_status=?,chat_mode=?,board_url=?,updated_at=? WHERE id=?''',
                  (name,str(body.get('description') or '')[:1000],price,cap,minimum,recruitment,chat,board or None,database.now_iso(),int(gid)))
    return {'status':'ok'}


def onboarding_invite(token):
    ensure_schema()
    with connection() as c:
        row = c.execute('SELECT invite_token FROM group_invite_onboarding WHERE onboarding_token=?', (str(token).strip().upper(),)).fetchone()
    return row['invite_token'] if row else None


def onboarding_start(body):
    from web_backend import student_onboarding as onboarding
    token = str(body.get('group_invite') or '')
    g = preview(token)['group']
    if g['recruitment_status'] != 'OPEN': raise ValueError('group_recruitment_closed')
    result = onboarding.start_returning(body.get('preferred_channel'),body.get('profile_url'),body.get('name'),body.get('grade'),g['subject'],g['study_goal'],body.get('phone'),body.get('legacy_note'))
    with connection() as c:
        c.execute('INSERT INTO group_invite_onboarding VALUES(?,?)',(result['token'],token))
    return result


def onboarding_status(token):
    from web_backend import student_onboarding as onboarding
    result = onboarding.status_payload(token); invite = onboarding_invite(token)
    if not invite: raise ValueError('invite_not_found')
    result['group_invite'] = invite
    result['group'] = preview(invite)['group']
    return result


def onboarding_region(body):
    from web_backend import student_onboarding as onboarding
    if not onboarding_invite(body.get('token')): raise ValueError('invite_not_found')
    result = onboarding.save_region(body.get('token'),body.get('region'),body.get('timezone'))
    with connection() as c:
        c.execute("UPDATE student_onboarding_sessions SET status='SCHEDULE_SET',schedule_json='[]' WHERE token=?", (result['token'],))
    return onboarding_status(result['token'])


def onboarding_complete(body):
    from web_backend import student_onboarding as onboarding
    invite = onboarding_invite(body.get('token'))
    if not invite: raise ValueError('invite_not_found')
    result = onboarding.complete(body.get('token'),body.get('login'),body.get('password'))
    # Joining is retriable after account creation, even if recruitment changes midway.
    result['redirect'] = '/app/group-invite.html?' + urlencode({'invite':invite,'registered':'1'})
    return result
