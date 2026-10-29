"""Family access applies only to self-study; never changes working accounts."""
import hashlib
import secrets
import time
from datetime import datetime, timezone
from database import connect


def ensure_schema():
    conn=connect()
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS personal_study_memberships (
          account_key TEXT PRIMARY KEY,granted_by INTEGER NOT NULL,active INTEGER NOT NULL,
          activated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS personal_study_invitations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,token_hash TEXT NOT NULL UNIQUE,
          account_key TEXT NOT NULL,created_by INTEGER NOT NULL,expires_at INTEGER NOT NULL,
          used_at TEXT,revoked INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS idx_study_invite_student ON personal_study_invitations(account_key,created_by);
        ''');conn.commit()
    finally:conn.close()


def is_manager(teacher_id):
    conn=connect()
    try:
        row=conn.execute('SELECT role FROM admin_accounts WHERE telegram_id=? AND active=1',(teacher_id,)).fetchone()
        return bool(row and row['role']=='OWNER')
    finally:conn.close()


def is_member(student_id,role='student'):
    ensure_schema();conn=connect()
    try:return bool(conn.execute('SELECT 1 FROM personal_study_memberships WHERE account_key=? AND active=1',(account_key(role,student_id),)).fetchone())
    finally:conn.close()


def require_manager(teacher_id):
    if not is_manager(teacher_id):raise PermissionError('family_owner_required')


def account_key(role,value):
    if role not in ('student','parent'):raise ValueError('invalid_family_account')
    return role+':'+str(_student_id(value))

def study_identity(role,value):
    _student_id(value)
    return -value if role=='student' else -(10**12+value)

def _student_id(value):
    if type(value) is not int or not 1<=value<10**12:raise ValueError('invalid_family_account')
    return value


def overview(teacher_id):
    require_manager(teacher_id);ensure_schema();conn=connect()
    try:
        # Read-only lookup of existing accounts. No student/business record writes.
        accounts=[]
        for role,table in (('student','users'),('parent','parent_accounts')):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                accounts.extend({**dict(r),'role':role} for r in conn.execute('SELECT id,name FROM '+table+' WHERE active=1 ORDER BY name,id LIMIT 500'))
        members=[dict(r) for r in conn.execute('SELECT account_key,active,activated_at FROM personal_study_memberships WHERE granted_by=?',(teacher_id,))]
        invites=[dict(r) for r in conn.execute('SELECT id,account_key,expires_at,used_at,revoked FROM personal_study_invitations WHERE created_by=? ORDER BY id DESC LIMIT 100',(teacher_id,))]
        return {'accounts':accounts,'members':members,'invitations':invites}
    finally:conn.close()


def issue(teacher_id,data):
    require_manager(teacher_id);role=data.get('account_role','student');sid=_student_id(data.get('account_id',data.get('student_id')));key=account_key(role,sid);table='users' if role=='student' else 'parent_accounts';ensure_schema();conn=connect()
    token=secrets.token_urlsafe(32);expires=int(time.time())+7*86400
    try:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT id,name FROM '+table+' WHERE id=? AND active=1',(sid,)).fetchone()
        if not row:raise ValueError('invalid_family_account')
        conn.execute('UPDATE personal_study_invitations SET revoked=1 WHERE account_key=? AND created_by=?',(key,teacher_id))
        conn.execute('''INSERT INTO personal_study_invitations(token_hash,account_key,created_by,expires_at)
          VALUES(?,?,?,?)''',(hashlib.sha256(token.encode()).hexdigest(),key,teacher_id,expires));conn.commit()
        return {'token':token,'expires_at':expires,'account_id':sid,'account_role':role,'name':row['name']}
    except Exception:conn.rollback();raise
    finally:conn.close()


def accept(student_id,data,role='student'):
    sid=_student_id(student_id);key=account_key(role,sid);table='users' if role=='student' else 'parent_accounts';token=data.get('token')
    if not isinstance(token,str) or not 30<=len(token)<=100:raise PermissionError('invalid_family_invite')
    ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT * FROM personal_study_invitations WHERE token_hash=?',
                          (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row or row['account_key']!=key or row['revoked']:raise PermissionError('invalid_family_invite')
        if row['used_at']:
            if not conn.execute('SELECT 1 FROM personal_study_memberships WHERE account_key=? AND active=1',(key,)).fetchone():
                raise PermissionError('invalid_family_invite')
            return {'status':'active'}
        if row['expires_at']<=int(time.time()):raise PermissionError('invalid_family_invite')
        if not conn.execute('SELECT 1 FROM '+table+' WHERE id=? AND active=1',(sid,)).fetchone():raise PermissionError('invalid_family_invite')
        if not is_manager(row['created_by']):raise PermissionError('invalid_family_invite')
        stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
        conn.execute('''INSERT INTO personal_study_memberships VALUES(?,?,1,?) ON CONFLICT(account_key)
          DO UPDATE SET granted_by=excluded.granted_by,active=1,activated_at=excluded.activated_at''',(key,row['created_by'],stamp))
        conn.execute('UPDATE personal_study_invitations SET used_at=? WHERE id=?',(stamp,row['id']));conn.commit()
        return {'status':'active'}
    except Exception:conn.rollback();raise
    finally:conn.close()


def revoke(teacher_id,data):
    require_manager(teacher_id);role=data.get('account_role','student');sid=_student_id(data.get('account_id',data.get('student_id')));key=account_key(role,sid);table='users' if role=='student' else 'parent_accounts';ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('UPDATE personal_study_memberships SET active=0 WHERE account_key=? AND granted_by=?',(key,teacher_id))
        conn.execute('UPDATE personal_study_invitations SET revoked=1 WHERE account_key=? AND created_by=?',(key,teacher_id))
        conn.commit();return {'status':'revoked'}
    finally:conn.close()
