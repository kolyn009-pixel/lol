"""Telegram step-up scoped to the owner's current web session and legal editor."""
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.request import Request, urlopen

from database import connect
from web_backend import otp_secret

TTL = 300
ACCESS_TTL = 600


def _session(token):
    if not token:
        raise ValueError('stepup_required')
    return hashlib.sha256(str(token).encode()).hexdigest()


def _db():
    conn = connect()
    conn.execute('''CREATE TABLE IF NOT EXISTS legal_stepup (
        session_hash TEXT PRIMARY KEY, owner_id INTEGER NOT NULL,
        challenge TEXT NOT NULL, code_hash TEXT NOT NULL,
        created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0, consumed INTEGER NOT NULL DEFAULT 1,
        verified_until INTEGER NOT NULL DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS legal_stepup_requests (
        owner_id INTEGER NOT NULL, created_at INTEGER NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS legal_stepup_rate ON legal_stepup_requests(owner_id,created_at)')
    conn.commit()
    return conn


def _send(owner_id, code):
    token = os.environ.get('BOT_TOKEN', '').strip()
    if not token:
        raise RuntimeError('stepup_unavailable')
    message = ('Аделия: доступ к реквизитам и документам сайта.\n'
               f'Код: {code}\nДействует 5 минут. Не передавайте его другим.\n'
               'Если вы не открывали этот раздел, не вводите код.')
    request = Request('https://api.telegram.org/bot' + token + '/sendMessage',
                      data=json.dumps({'chat_id': int(owner_id), 'text': message}).encode(),
                      headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read(65536))
        if not result.get('ok'):
            raise RuntimeError('stepup_delivery_failed')
    except Exception:
        # Never surface Telegram URLs, bot tokens or response details.
        raise RuntimeError('stepup_delivery_failed') from None


def issue(token, owner_id, sender=None):
    key, owner_id, now = _session(token), int(owner_id), int(time.time())
    code = f'{secrets.randbelow(1000000):06d}'
    challenge = secrets.token_hex(16)
    digest = otp_secret.digest('legal:' + key + ':' + challenge + ':' + code)
    conn = _db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        stamps = [r[0] for r in conn.execute(
            'SELECT created_at FROM legal_stepup_requests WHERE owner_id=? AND created_at>?',
            (owner_id, now - 3600))]
        if len(stamps) >= 5 or any(t > now - 60 for t in stamps):
            raise ValueError('stepup_rate_limited')
        conn.execute('DELETE FROM legal_stepup_requests WHERE created_at<?', (now - 86400,))
        conn.execute('DELETE FROM legal_stepup WHERE expires_at<? AND verified_until<?', (now - 86400, now))
        conn.execute('INSERT INTO legal_stepup_requests VALUES (?,?)', (owner_id, now))
        conn.execute('INSERT OR REPLACE INTO legal_stepup VALUES (?,?,?,?,?,?,0,1,0)',
                     (key, owner_id, challenge, digest, now, now + TTL))
        conn.commit()
    finally:
        conn.close()
    (sender or _send)(owner_id, code)
    conn = _db()
    try:
        conn.execute('UPDATE legal_stepup SET consumed=0 WHERE session_hash=? AND challenge=?', (key, challenge))
        conn.commit()
    finally:
        conn.close()
    return {'sent': True, 'expires_in': TTL, 'retry_after': 60}


def verify(token, owner_id, code):
    key, now = _session(token), int(time.time())
    conn = _db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM legal_stepup WHERE session_hash=? AND owner_id=?',
                           (key, int(owner_id))).fetchone()
        if not row or row['consumed'] or row['expires_at'] <= now or row['attempts'] >= 5:
            raise ValueError('stepup_invalid')
        digest = otp_secret.digest('legal:' + key + ':' + row['challenge'] + ':' + str(code).strip())
        good = hmac.compare_digest(digest, row['code_hash'])
        conn.execute('UPDATE legal_stepup SET attempts=attempts+1, consumed=?, verified_until=? WHERE session_hash=?',
                     (int(good or row['attempts'] >= 4), now + ACCESS_TTL if good else 0, key))
        conn.commit()
        if not good:
            raise ValueError('stepup_invalid')
    finally:
        conn.close()
    return {'verified': True, 'expires_in': ACCESS_TTL}


def allowed(token, owner_id):
    if not token:
        return False
    conn = _db()
    try:
        return bool(conn.execute('SELECT 1 FROM legal_stepup WHERE session_hash=? AND owner_id=? AND verified_until>?',
                                 (_session(token), int(owner_id), int(time.time()))).fetchone())
    finally:
        conn.close()
