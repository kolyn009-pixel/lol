"""Published immutable legal editions and authenticated parent acceptance.

Drafts never require acceptance. Publishing activates the gate; editing a draft
does not change an edition that a parent already accepted.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from database import connect

FIELDS = ('name', 'inn', 'email', 'phone', 'address', 'terms', 'privacy', 'consent')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ensure_schema():
    conn = connect()
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS legal_draft (
          id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL,
          updated_at TEXT NOT NULL, updated_by INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS legal_editions (
          version TEXT PRIMARY KEY, payload TEXT NOT NULL,
          published_at TEXT NOT NULL, published_by INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS legal_current (
          id INTEGER PRIMARY KEY CHECK(id=1), version TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS parent_legal_acceptances (
          parent_id INTEGER NOT NULL, version TEXT NOT NULL,
          accepted_at TEXT NOT NULL, terms INTEGER NOT NULL,
          privacy_ack INTEGER NOT NULL, consent INTEGER NOT NULL,
          PRIMARY KEY(parent_id, version));
        ''')
        conn.commit()
    finally:
        conn.close()


def _edition(conn, version=None):
    if version:
        row = conn.execute('SELECT * FROM legal_editions WHERE version=?', (version,)).fetchone()
    else:
        row = conn.execute('SELECT e.* FROM legal_editions e JOIN legal_current c ON c.version=e.version WHERE c.id=1').fetchone()
    if not row:
        return None
    return {'version': row['version'], 'published_at': row['published_at'],
            **json.loads(row['payload'])}


def public(version=None):
    ensure_schema()
    conn = connect()
    try:
        return _edition(conn, version)
    finally:
        conn.close()


def editor():
    ensure_schema()
    conn = connect()
    try:
        row = conn.execute('SELECT * FROM legal_draft WHERE id=1').fetchone()
        current = _edition(conn)
        return {'draft': json.loads(row['payload']) if row else {k: '' for k in FIELDS},
                'updated_at': row['updated_at'] if row else None, 'published': current}
    finally:
        conn.close()


def _clean(body):
    if not isinstance(body, dict):
        raise ValueError('invalid_document')
    result = {}
    for key in FIELDS:
        value = body.get(key, '')
        if not isinstance(value, str) or len(value) > (24000 if key in ('terms', 'privacy', 'consent') else 500):
            raise ValueError('invalid_' + key)
        result[key] = value.strip()
    return result


def _validate(data):
    for key, value in data.items():
        if not value or '[заполнить' in value.lower() or '{{' in value:
            raise ValueError('required_' + key)
    inn = data['inn']
    if not re.fullmatch(r'[0-9]{12}', inn) or len(set(inn)) == 1:
        raise ValueError('invalid_inn')
    digits = list(map(int, inn))
    for weights, check in [([7,2,4,10,3,5,9,4,6,8],10), ([3,7,2,4,10,3,5,9,4,6,8],11)]:
        if sum(a*b for a,b in zip(digits,weights)) % 11 % 10 != digits[check]:
            raise ValueError('invalid_inn')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', data['email']):
        raise ValueError('invalid_email')
    if len(re.sub(r'\D', '', data['phone'])) < 10:
        raise ValueError('invalid_phone')
    for key in ('terms', 'privacy', 'consent'):
        if len(data[key]) < 100:
            raise ValueError('incomplete_' + key)


def save(body, teacher_id, publish=False):
    data = _clean(body)
    if publish:
        if body.get('reviewed') is not True:
            raise ValueError('review_required')
        _validate(data)
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    version = hashlib.sha256(payload.encode()).hexdigest()
    ensure_schema()
    conn = connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('INSERT OR REPLACE INTO legal_draft VALUES(1,?,?,?)', (payload, now(), int(teacher_id)))
        if publish:
            conn.execute('INSERT OR IGNORE INTO legal_editions VALUES(?,?,?,?)', (version, payload, now(), int(teacher_id)))
            conn.execute('INSERT OR REPLACE INTO legal_current VALUES(1,?)', (version,))
        conn.commit()
    finally:
        conn.close()
    return {'saved': True, 'published': publish, 'version': version if publish else None}


def status(parent_id):
    ensure_schema()
    conn = connect()
    try:
        edition = _edition(conn)
        row = conn.execute('SELECT accepted_at FROM parent_legal_acceptances WHERE parent_id=? AND version=?',
                           (int(parent_id), edition['version'])).fetchone() if edition else None
        return {'configured': bool(edition), 'required': bool(edition and not row),
                'edition': edition, 'accepted_at': row['accepted_at'] if row else None}
    finally:
        conn.close()


def accept(parent_id, body):
    if not isinstance(body, dict) or any(body.get(k) is not True for k in ('terms', 'privacy_ack', 'consent')):
        raise ValueError('explicit_acceptance_required')
    ensure_schema()
    conn = connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        edition = _edition(conn)
        if not edition:
            raise ValueError('documents_not_published')
        if body.get('version') != edition['version']:
            raise ValueError('documents_changed')
        conn.execute('INSERT OR IGNORE INTO parent_legal_acceptances VALUES(?,?,?,1,1,1)',
                     (int(parent_id), edition['version'], now()))
        conn.commit()
    finally:
        conn.close()
    return status(parent_id)
