"""Small, authenticated avatars. No remote image URLs or new dependencies."""
from __future__ import annotations
import struct
import zlib
from urllib.parse import urlencode
import database

PRESETS = {f'student_avatar_{i:02d}' for i in range(1, 11)}
ROLES = {'student', 'parent', 'teacher'}
MAX_BYTES = 400_000

def ensure_schema():
    c = database.connect()
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS profile_avatars (
            role TEXT NOT NULL, owner_id INTEGER NOT NULL,
            preset TEXT, image BLOB, updated_at TEXT NOT NULL,
            PRIMARY KEY(role, owner_id))''')
        c.commit()
    finally:
        c.close()

def identity(auth):
    if not auth or auth.get('role') not in ROLES:
        raise PermissionError('unauthorized')
    return auth['role'], int(auth['id'])

def _chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)

def sanitize_png(content):
    """Accept only bounded 8-bit RGB/RGBA canvas PNGs; discard metadata."""
    data = bytes(content)
    if len(data) > MAX_BYTES:
        raise ValueError('avatar_too_large')
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('avatar_png_required')
    pos, header, blocks, ended = 8, None, [], False
    while pos + 12 <= len(data):
        size = struct.unpack('>I', data[pos:pos+4])[0]
        kind = data[pos+4:pos+8]
        end = pos + 12 + size
        if end > len(data):
            raise ValueError('invalid_avatar')
        body = data[pos+8:pos+8+size]
        crc = struct.unpack('>I', data[pos+8+size:end])[0]
        if crc != zlib.crc32(kind + body) & 0xffffffff:
            raise ValueError('invalid_avatar')
        if kind == b'IHDR':
            if header is not None or pos != 8 or size != 13:
                raise ValueError('invalid_avatar')
            header = body
        elif kind == b'IDAT':
            blocks.append(body)
        elif kind == b'IEND':
            if size != 0 or end != len(data):
                raise ValueError('invalid_avatar')
            ended = True
            break
        elif kind in {b'acTL', b'fcTL', b'fdAT'} or not (kind[0] & 32):
            raise ValueError('invalid_avatar')
        pos = end
    if not header or not blocks or not ended:
        raise ValueError('invalid_avatar')
    width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', header)
    if not (1 <= width <= 256 and 1 <= height <= 256) or depth != 8 or color not in {2, 6} or compression or filtering or interlace:
        raise ValueError('avatar_dimensions')
    stride = width * (4 if color == 6 else 3) + 1
    expected = height * stride
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(b''.join(blocks), expected + 1)
    except zlib.error:
        raise ValueError('invalid_avatar') from None
    if len(raw) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('invalid_avatar')
    if any(raw[y * stride] > 4 for y in range(height)):
        raise ValueError('invalid_avatar')
    return b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header) + _chunk(b'IDAT', zlib.compress(raw)) + _chunk(b'IEND', b'')

def _url(role, uid, version=None):
    query = {'role': role, 'id': uid}
    if version:
        query['v'] = version
    return '/api/profile/avatar?' + urlencode(query)

def appearance(auth):
    role, uid = identity(auth)
    ensure_schema()
    c = database.connect()
    try:
        row = c.execute('SELECT preset,image,updated_at FROM profile_avatars WHERE role=? AND owner_id=?', (role, uid)).fetchone()
    finally:
        c.close()
    preset = row['preset'] if row and row['preset'] in PRESETS else 'student_avatar_01'
    image_url = _url(role, uid, row['updated_at']) if row and row['image'] else None
    if role == 'student' and not row:
        from web_backend import student_social_profile
        profile = student_social_profile.public_profile(uid, viewer_id=uid)
        if profile.get('avatar_value') in PRESETS:
            preset = profile['avatar_value']
    return {'role': role, 'owner_id': uid, 'preset': preset, 'url': image_url or f'/app/assets/avatars/{preset}.svg', 'custom': bool(image_url)}

def save(auth, *, preset=None, content=None):
    role, uid = identity(auth)
    if role == 'student':
        from web_backend import student_social_profile
        student_social_profile.public_profile(uid, viewer_id=uid)
    ensure_schema()
    image = sanitize_png(content) if content is not None else None
    if image is None and preset not in PRESETS:
        raise ValueError('invalid_avatar_preset')
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    c = database.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute('''INSERT INTO profile_avatars(role,owner_id,preset,image,updated_at) VALUES(?,?,?,?,?)
                     ON CONFLICT(role,owner_id) DO UPDATE SET preset=excluded.preset,image=excluded.image,updated_at=excluded.updated_at''',
                  (role, uid, preset if image is None else None, image, now))
        if role == 'student':
            value = _url(role, uid, now) if image else preset
            c.execute('''UPDATE student_social_profiles SET avatar_kind=?,avatar_value=?,updated_at=? WHERE user_id=?''',
                      ('CUSTOM' if image else 'PRESET', value, now, uid))
        c.commit()
    finally:
        c.close()
    return appearance(auth)

def read(auth, role, uid):
    viewer_role, viewer = identity(auth)
    uid = int(uid)
    if role not in ROLES:
        raise PermissionError('avatar_not_found')
    ensure_schema()
    c = database.connect()
    try:
        allowed = (viewer_role == role and viewer == uid) or viewer_role == 'teacher'
        if not allowed and role == viewer_role == 'student':
            allowed = bool(c.execute('''SELECT 1 FROM group_members a JOIN group_members b ON a.group_id=b.group_id
                         JOIN study_groups g ON g.id=a.group_id
                         WHERE a.user_id=? AND b.user_id=? AND a.status IN ('ACTIVE','PAUSED')
                         AND b.status IN ('ACTIVE','PAUSED') AND g.active=1 LIMIT 1''', (viewer, uid)).fetchone())
        if not allowed:
            raise PermissionError('avatar_not_found')
        row = c.execute('SELECT image FROM profile_avatars WHERE role=? AND owner_id=?', (role, uid)).fetchone()
        if not row or not row['image']:
            raise FileNotFoundError('avatar_not_found')
        return {'content': bytes(row['image']), 'filename': 'avatar.png', 'mime_type': 'image/png'}
    finally:
        c.close()

def conversation_avatars(items):
    """Decorate teacher-only inbox metadata, without loading photo blobs."""
    from web_backend import student_social_profile
    student_social_profile.ensure_schema()
    ensure_schema()
    ids = {int(item['student_id']) for item in items}
    parents = {int(item['participant_id']) for item in items if item.get('participant_type') == 'PARENT'}
    c = database.connect()
    try:
        profiles = {}
        if ids:
            marks = ','.join('?' for _ in ids)
            profiles = {int(r['user_id']):dict(r) for r in c.execute(f'SELECT user_id,avatar_kind,avatar_value FROM student_social_profiles WHERE user_id IN ({marks})', sorted(ids))}
        parent_profiles = {}
        if parents:
            marks = ','.join('?' for _ in parents)
            parent_profiles = {int(r['owner_id']):dict(r) for r in c.execute(f"SELECT owner_id,preset,image IS NOT NULL AS custom,updated_at FROM profile_avatars WHERE role='parent' AND owner_id IN ({marks})", sorted(parents))}
        for item in items:
            if item.get('participant_type') == 'PARENT':
                pid = int(item['participant_id']);p = parent_profiles.get(pid,{})
                item['avatar_kind'] = 'CUSTOM' if p.get('custom') else 'PRESET'
                item['avatar_value'] = _url('parent',pid,p['updated_at']) if p.get('custom') else p.get('preset') or 'student_avatar_01'
            else:
                p = profiles.get(int(item['student_id']),{})
                item['avatar_kind'] = p.get('avatar_kind') or 'PRESET'
                item['avatar_value'] = p.get('avatar_value') or 'student_avatar_01'
        return items
    finally:
        c.close()

class AvatarMixin:
    def avatar_get(self, path, query):
        if path not in {'/api/profile/appearance', '/api/profile/avatar'}:
            return False
        auth = self._auth()
        if not auth:
            self._json(401, {'error': 'unauthorized'}); return True
        try:
            if path.endswith('/appearance'):
                self._json(200, appearance(auth))
            else:
                self._file(read(auth, (query.get('role') or [''])[0], (query.get('id') or ['0'])[0]))
        except (PermissionError, FileNotFoundError):
            self._json(404, {'error': 'avatar_not_found'})
        except (ValueError, TypeError):
            self._json(400, {'error': 'invalid_request'})
        except Exception as exc:
            print('[avatars] read error:', type(exc).__name__, flush=True)
            self._json(500, {'error': 'avatar_unavailable'})
        return True

    def avatar_post(self, path):
        if path not in {'/api/profile/appearance', '/api/profile/avatar'}:
            return False
        if not self._same_origin_write():
            self._json(403, {'error': 'cross_origin_forbidden'}); return True
        auth = self._auth()
        if not auth:
            self._json(401, {'error': 'unauthorized'}); return True
        try:
            if auth.get('role') == 'student':
                from web_backend import student_social_profile
                student_social_profile.public_profile(auth['id'], viewer_id=auth['id'])
            if path.endswith('/appearance'):
                body = self._body()
                if not isinstance(body, dict):
                    raise ValueError('invalid_json')
                result = save(auth, preset=body.get('preset'))
            else:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_BYTES + 8192:
                    self._json(413, {'error': 'avatar_too_large'}); return True
                form = self._multipart()
                if form is None or 'file' not in form or isinstance(form['file'], list):
                    raise ValueError('avatar_required')
                file = form['file']
                if not file.file:
                    raise ValueError('avatar_required')
                result = save(auth, content=file.file.read(MAX_BYTES + 1))
            self._json(200, result)
        except PermissionError:
            self._json(401, {'error': 'unauthorized'})
        except (ValueError, TypeError) as exc:
            self._json(400, {'error': str(exc)})
        except Exception as exc:
            print('[avatars] save error:', type(exc).__name__, flush=True)
            self._json(500, {'error': 'avatar_unavailable'})
        return True
