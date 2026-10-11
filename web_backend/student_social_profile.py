"""Student-facing social profile for the app.

This layer is intentionally separate from tutoring, group membership and event
registration. Group membership only controls access to a group's social space.
Sensitive contacts are never exposed through public profile payloads.
"""
from __future__ import annotations

import database

ALLOWED_MANUAL_STATUSES={"","AVAILABLE","STUDYING","DND","AWAY"}
ALLOWED_AVATAR_KINDS={"PRESET","CUSTOM"}


def ensure_schema():
    c=database.connect();c.executescript("""
    CREATE TABLE IF NOT EXISTS student_social_profiles(
      user_id INTEGER PRIMARY KEY,
      display_name TEXT,
      avatar_kind TEXT NOT NULL DEFAULT 'PRESET',
      avatar_value TEXT NOT NULL DEFAULT 'adelia_01',
      manual_status TEXT NOT NULL DEFAULT '',
      study_status_text TEXT,
      show_online INTEGER NOT NULL DEFAULT 0,
      allow_group_messages INTEGER NOT NULL DEFAULT 1,
      onboarding_completed INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS student_presence(
      user_id INTEGER PRIMARY KEY,
      app_active_until TEXT,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS group_user_mutes(
      group_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      muted_user_id INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY(group_id,user_id,muted_user_id)
    );
    """)
    cols={r['name'] for r in c.execute("PRAGMA table_info(student_social_profiles)").fetchall()}
    if 'onboarding_completed' not in cols:
        c.execute("ALTER TABLE student_social_profiles ADD COLUMN onboarding_completed INTEGER NOT NULL DEFAULT 0")
        c.execute("""UPDATE student_social_profiles SET onboarding_completed=1
                     WHERE avatar_kind!='PRESET' OR avatar_value!='adelia_01'
                        OR manual_status!='' OR COALESCE(study_status_text,'')!=''
                        OR show_online!=0 OR allow_group_messages!=1""")
    c.commit();c.close()


def _profile(uid):
    ensure_schema();c=database.connect();row=c.execute("SELECT * FROM student_social_profiles WHERE user_id=?",(int(uid),)).fetchone();c.close()
    if row:return dict(row)
    c=database.connect();u=c.execute("SELECT name FROM users WHERE id=?",(int(uid),)).fetchone()
    if not u:c.close();raise ValueError('user_not_found')
    now=database.now_iso();c.execute("INSERT INTO student_social_profiles(user_id,display_name,updated_at) VALUES(?,?,?)",(int(uid),u['name'],now));c.commit();c.close();return _profile(uid)


def update(user_id,*,display_name=None,avatar_kind=None,avatar_value=None,manual_status=None,study_status_text=None,show_online=None,allow_group_messages=None):
    p=_profile(user_id);kind=str(avatar_kind or p['avatar_kind']).upper();status=p['manual_status'] if manual_status is None else str(manual_status).upper()
    if kind not in ALLOWED_AVATAR_KINDS:raise ValueError('invalid_avatar_kind')
    if status not in ALLOWED_MANUAL_STATUSES:raise ValueError('invalid_manual_status')
    name=str(display_name if display_name is not None else p['display_name']).strip()[:40]
    if not name:raise ValueError('display_name_required')
    avatar=str(avatar_value if avatar_value is not None else p['avatar_value']).strip()[:500]
    if avatar_kind is not None or avatar_value is not None:
        from web_backend.profile_avatars import PRESETS
        from urllib.parse import urlparse,parse_qs
        if kind=='PRESET' and avatar not in PRESETS and avatar not in {f'adelia_{i:02d}' for i in range(1,9)}:raise ValueError('invalid_avatar_preset')
        if kind=='CUSTOM':
            parsed=urlparse(avatar);query=parse_qs(parsed.query)
            if parsed.scheme or parsed.netloc or parsed.path!='/api/profile/avatar' or query.get('role')!=['student'] or query.get('id')!=[str(int(user_id))]:raise ValueError('invalid_avatar_url')
    study=str(study_status_text if study_status_text is not None else (p['study_status_text'] or '')).strip()[:80] or None
    c=database.connect();c.execute("""UPDATE student_social_profiles SET display_name=?,avatar_kind=?,avatar_value=?,manual_status=?,study_status_text=?,show_online=?,allow_group_messages=?,onboarding_completed=1,updated_at=? WHERE user_id=?""",(name,kind,avatar,status,study,int(bool(p['show_online'] if show_online is None else show_online)),int(bool(p['allow_group_messages'] if allow_group_messages is None else allow_group_messages)),database.now_iso(),int(user_id)));c.commit();c.close()
    if (avatar_kind is not None or avatar_value is not None) and kind=='PRESET':
        from web_backend import profile_avatars
        preset=avatar if avatar in profile_avatars.PRESETS else 'student_avatar_'+avatar[-2:]
        profile_avatars.save({'role':'student','id':int(user_id)},preset=preset)
    return public_profile(user_id,viewer_id=user_id)


def touch_presence(user_id,active_seconds=120):
    ensure_schema();from datetime import datetime,timedelta
    until=(datetime.now()+timedelta(seconds=max(30,min(int(active_seconds or 120),600)))).isoformat(timespec='seconds');now=database.now_iso();c=database.connect();c.execute("INSERT INTO student_presence(user_id,app_active_until,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET app_active_until=excluded.app_active_until,updated_at=excluded.updated_at",(int(user_id),until,now));c.commit();c.close();return {'status':'ok','active_until':until}


def _is_online(uid):
    from datetime import datetime
    c=database.connect();row=c.execute("SELECT app_active_until FROM student_presence WHERE user_id=?",(int(uid),)).fetchone();c.close()
    if not row or not row['app_active_until']:return False
    try:return datetime.fromisoformat(row['app_active_until'])>=datetime.now()
    except Exception:return False


def public_profile(user_id,viewer_id=None):
    p=_profile(user_id);own=viewer_id is not None and int(viewer_id)==int(user_id)
    out={'user_id':int(user_id),'display_name':p['display_name'],'avatar_kind':p['avatar_kind'],'avatar_value':p['avatar_value'],'manual_status':p['manual_status'],'study_status_text':p['study_status_text'],'online':bool(p['show_online'] and _is_online(user_id))}
    if own:out.update({'show_online':bool(p['show_online']),'allow_group_messages':bool(p['allow_group_messages']),'onboarding_completed':bool(p['onboarding_completed'])})
    return out


def group_members(group_id,viewer_id):
    ensure_schema();gid=int(group_id);vid=int(viewer_id);c=database.connect();allowed=c.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=? AND status IN ('ACTIVE','PAUSED')",(gid,vid)).fetchone()
    if not allowed:c.close();raise PermissionError('group_access_denied')
    rows=c.execute("SELECT user_id FROM group_members WHERE group_id=? AND status IN ('ACTIVE','PAUSED') ORDER BY user_id",(gid,)).fetchall();mutes={int(r['muted_user_id']) for r in c.execute("SELECT muted_user_id FROM group_user_mutes WHERE group_id=? AND user_id=?",(gid,vid)).fetchall()};c.close()
    return [{**public_profile(int(r['user_id']),viewer_id=vid),'muted':int(r['user_id']) in mutes} for r in rows]

