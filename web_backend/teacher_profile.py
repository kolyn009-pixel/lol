"""Public teacher profile: storage, seed, read and validated update."""
import json
import re

from database import connect, now_iso

PUBLIC_FIELDS = ('slug', 'display_name', 'headline', 'quote', 'bio', 'education',
                 'experience_text', 'facts', 'subjects', 'photo_url', 'links')
_TEXT_LIMITS = {'slug': 40, 'display_name': 120, 'headline': 200, 'quote': 500,
                'bio': 3000, 'education': 1000, 'experience_text': 200}
_SLUG_RE = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$')
_LINK_KEYS = {'profi', 'telegram_channel', 'telegram_bot', 'vk'}
_SUBJECTS = {'PHYSICS', 'CHEMISTRY'}
_GOALS = {'SCHOOL', 'OGE', 'EGE', 'OLYMPIAD'}

_SEED = {
    'slug': 'solovyev',
    'display_name': 'Николай Владимирович Соловьев',
    'headline': None,
    'quote': 'Физика объясняет, почему мир устроен именно так. Моя задача — чтобы ученик увидел это сам, а не заучил.',
    'bio': ('Сам поступил в университет по олимпиаде и знаю этот путь изнутри. Репетиторством занимаюсь с 2022 года: '
            'готовлю к экзаменам, помогаю со школьной программой и отдельно работаю с олимпиадной физикой.\n\n'
            'Моя задача — научить видеть физический смысл, рассуждать и уверенно применять знания. '
            'А расписание, задания, материалы и прогресс остаются у ученика в Аделии.'),
    'education': None,
    'experience_text': 'Преподаю с 2022 года',
    'facts': ['Преподаю с 2022 года', 'Более 70 учеников', 'Сам прошёл олимпиадный путь поступления',
              'Организация обучения через Аделию — 24/7'],
    'subjects': [{'subject': 'PHYSICS', 'label': 'Физика', 'goals': ['SCHOOL', 'OGE', 'EGE']},
                 {'subject': 'CHEMISTRY', 'label': 'Химия', 'goals': ['OGE']}],
    'photo_url': '/assets/nikolay-adelia-hero.png',
    'links': {'profi': 'https://profi.ru/profile/SolovyevNV2',
              'telegram_channel': 'https://t.me/+QC0t6N6kUmoxZjdi',
              'telegram_bot': 'https://t.me/AdeliaTutorBot',
              'vk': 'https://vk.ru/club241263797'},
}


def _owner_id():
    import admin
    return int(admin.ADMIN_ID)


def ensure_teacher_profile_table():
    conn = connect()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS teacher_public_profile(
            teacher_id INTEGER PRIMARY KEY, slug TEXT UNIQUE, display_name TEXT, headline TEXT,
            quote TEXT, bio TEXT, education TEXT, experience_text TEXT, facts_json TEXT,
            subjects_json TEXT, photo_url TEXT, links_json TEXT,
            active INTEGER DEFAULT 1, updated_at TEXT)""")
        if conn.execute('SELECT 1 FROM teacher_public_profile LIMIT 1').fetchone() is None:
            s = _SEED
            conn.execute("""INSERT OR IGNORE INTO teacher_public_profile(teacher_id,slug,display_name,headline,quote,bio,
                education,experience_text,facts_json,subjects_json,photo_url,links_json,active,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?)""",
                (_owner_id(), s['slug'], s['display_name'], s['headline'], s['quote'], s['bio'], s['education'],
                 s['experience_text'], json.dumps(s['facts'], ensure_ascii=False),
                 json.dumps(s['subjects'], ensure_ascii=False), s['photo_url'],
                 json.dumps(s['links'], ensure_ascii=False), now_iso()))
        conn.commit()
    finally:
        conn.close()


def _load(raw, default):
    try:
        v = json.loads(raw) if raw else default
        return v if isinstance(v, type(default)) else default
    except (ValueError, TypeError):
        return default


def get_public_teacher_profile(slug=None):
    ensure_teacher_profile_table()
    conn = connect()
    try:
        if slug:
            row = conn.execute('SELECT * FROM teacher_public_profile WHERE slug=? AND active=1', (str(slug),)).fetchone()
        else:
            row = conn.execute('SELECT * FROM teacher_public_profile WHERE teacher_id=? AND active=1', (_owner_id(),)).fetchone() \
                or conn.execute('SELECT * FROM teacher_public_profile WHERE active=1 ORDER BY teacher_id LIMIT 1').fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {'slug': row['slug'], 'display_name': row['display_name'], 'headline': row['headline'],
            'quote': row['quote'], 'bio': row['bio'], 'education': row['education'],
            'experience_text': row['experience_text'], 'facts': _load(row['facts_json'], []),
            'subjects': _load(row['subjects_json'], []), 'photo_url': row['photo_url'],
            'links': _load(row['links_json'], {}), 'updated_at': row['updated_at']}


def _https(v, what, limit=500):
    if not isinstance(v, str) or not v.startswith('https://') or len(v) > limit or re.search(r'\s', v):
        raise ValueError(what)
    return v


def _validate(body):
    if not isinstance(body, dict):
        raise ValueError('invalid_body')
    out = {}
    for k, lim in _TEXT_LIMITS.items():
        if k in body:
            v = body[k]
            if v is not None and (not isinstance(v, str) or len(v) > lim):
                raise ValueError('invalid_' + k)
            v = v.strip() if v else None
            if k in ('slug', 'display_name') and not v:
                raise ValueError('invalid_' + k)
            if k == 'slug' and not _SLUG_RE.match(v):
                raise ValueError('invalid_slug')
            out[k] = v
    if 'photo_url' in body:
        v = body['photo_url']
        if v is not None and not (isinstance(v, str) and len(v) <= 500 and not re.search(r'\s', v)
                                  and (v.startswith('https://') or (v.startswith('/') and not v.startswith('//')))):
            raise ValueError('invalid_photo_url')
        out['photo_url'] = v or None
    if 'facts' in body:
        f = body['facts']
        if not isinstance(f, list) or len(f) > 12 or any(not isinstance(x, str) or not x.strip() or len(x) > 200 for x in f):
            raise ValueError('invalid_facts')
        out['facts_json'] = json.dumps([x.strip() for x in f], ensure_ascii=False)
    if 'subjects' in body:
        s = body['subjects']
        if not isinstance(s, list) or len(s) > 10:
            raise ValueError('invalid_subjects')
        clean = []
        for it in s:
            if (not isinstance(it, dict) or it.get('subject') not in _SUBJECTS
                    or not isinstance(it.get('label'), str) or not it['label'].strip() or len(it['label']) > 60
                    or not isinstance(it.get('goals'), list) or len(it['goals']) > 6
                    or any(g not in _GOALS for g in it['goals'])):
                raise ValueError('invalid_subjects')
            clean.append({'subject': it['subject'], 'label': it['label'].strip(), 'goals': list(it['goals'])})
        out['subjects_json'] = json.dumps(clean, ensure_ascii=False)
    if 'links' in body:
        l = body['links']
        if not isinstance(l, dict) or set(l) - _LINK_KEYS:
            raise ValueError('invalid_links')
        out['links_json'] = json.dumps({k: _https(v, 'invalid_link_' + k) for k, v in l.items()}, ensure_ascii=False)
    if not out:
        raise ValueError('nothing_to_update')
    return out


def update_teacher_profile(teacher_id, body):
    """Update the caller's own record. Raises ValueError on invalid input."""
    ensure_teacher_profile_table()
    data = _validate(body)
    data['updated_at'] = now_iso()
    conn = connect()
    try:
        if not conn.execute('SELECT 1 FROM teacher_public_profile WHERE teacher_id=?', (int(teacher_id),)).fetchone():
            raise ValueError('profile_not_found')
        if 'slug' in data and conn.execute('SELECT 1 FROM teacher_public_profile WHERE slug=? AND teacher_id<>?',
                                           (data['slug'], int(teacher_id))).fetchone():
            raise ValueError('slug_taken')
        conn.execute('UPDATE teacher_public_profile SET %s WHERE teacher_id=?' % ','.join(k + '=?' for k in data),
                     tuple(data.values()) + (int(teacher_id),))
        conn.commit()
    finally:
        conn.close()
    slug = data.get('slug')
    conn = connect()
    try:
        slug = conn.execute('SELECT slug FROM teacher_public_profile WHERE teacher_id=?', (int(teacher_id),)).fetchone()['slug']
    finally:
        conn.close()
    return {'status': 'ok', 'profile': get_public_teacher_profile(slug)}
