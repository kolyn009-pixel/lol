"""Owned, bounded avatar images and the teacher view of the existing group chat."""
import base64
import binascii
import hashlib
import re
import secrets
import struct
import zlib
from web_backend import group_lessons, student_social_profile
from web_backend.group_workspace import connection
import database

STUDENT_PRESETS={f'student_avatar_{i:02}' for i in range(1,11)}|{f'adelia_{i:02}' for i in range(1,9)}
GROUP_PRESETS={f'group_{i:02}' for i in range(1,9)}
MAX_BYTES=180*1024


def ensure_schema():
    group_lessons.ensure_schema();student_social_profile.ensure_schema()
    with connection() as c:
        cols={r['name'] for r in c.execute('PRAGMA table_info(study_groups)')}
        for name,definition in [('avatar_kind',"TEXT NOT NULL DEFAULT 'PRESET'"),('avatar_value',"TEXT NOT NULL DEFAULT 'group_01'")]:
            if name not in cols:c.execute('ALTER TABLE study_groups ADD COLUMN '+name+' '+definition)
        c.executescript('''CREATE TABLE IF NOT EXISTS profile_avatar_images(
            token TEXT PRIMARY KEY,owner_kind TEXT NOT NULL,owner_id INTEGER NOT NULL,
            content BLOB NOT NULL,created_at TEXT NOT NULL,UNIQUE(owner_kind,owner_id));
        CREATE TABLE IF NOT EXISTS group_chat_client_ids(
            group_id INTEGER NOT NULL,sender_key TEXT NOT NULL,client_id TEXT NOT NULL,
            message_id INTEGER NOT NULL,body_hash TEXT NOT NULL,
            PRIMARY KEY(group_id,sender_key,client_id));''')


def png_image(encoded):
    """Accept canvas PNGs only; strip metadata and reject oversized/decompression bombs."""
    if not isinstance(encoded,str) or len(encoded)>MAX_BYTES*4//3+8:raise ValueError('avatar_too_large')
    try:data=base64.b64decode(encoded,validate=True)
    except (ValueError,binascii.Error):raise ValueError('invalid_avatar_image')
    if len(data)>MAX_BYTES:raise ValueError('avatar_too_large')
    if data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('invalid_avatar_image')
    offset=8;header=None;packed=[];ended=False
    while offset<len(data):
        if len(data)-offset<12:raise ValueError('invalid_avatar_image')
        size=int.from_bytes(data[offset:offset+4],'big');kind=data[offset+4:offset+8];end=offset+12+size
        if size>MAX_BYTES or end>len(data):raise ValueError('invalid_avatar_image')
        payload=data[offset+8:offset+8+size];crc=int.from_bytes(data[offset+8+size:end],'big')
        if zlib.crc32(kind+payload)&0xffffffff!=crc:raise ValueError('invalid_avatar_image')
        if header is None and kind!=b'IHDR':raise ValueError('invalid_avatar_image')
        if kind==b'IHDR':
            if header is not None or size!=13:raise ValueError('invalid_avatar_image')
            header=payload;w,h,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',payload)
            if not 1<=w<=192 or not 1<=h<=192 or depth!=8 or color not in (2,6) or (compression,filtering,interlace)!=(0,0,0):raise ValueError('invalid_avatar_dimensions')
        elif kind==b'IDAT':packed.append(payload)
        elif kind==b'IEND':
            if size or end!=len(data):raise ValueError('invalid_avatar_image')
            ended=True;break
        elif not kind[0]&32:raise ValueError('invalid_avatar_image')
        offset=end
    if not ended or not packed:raise ValueError('invalid_avatar_image')
    expected=(1+w*(4 if color==6 else 3))*h
    try:
        dec=zlib.decompressobj();pixels=dec.decompress(b''.join(packed),expected+1)
        if len(pixels)!=expected or not dec.eof or dec.unused_data or dec.unconsumed_tail:raise ValueError('invalid_avatar_image')
        stride=expected//h
        if any(pixels[i]>4 for i in range(0,expected,stride)):raise ValueError('invalid_avatar_image')
    except zlib.error:raise ValueError('invalid_avatar_image')
    def chunk(kind,payload):return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',header)+chunk(b'IDAT',zlib.compress(pixels,6))+chunk(b'IEND',b'')


def save_avatar(kind,owner_id,body):
    ensure_schema();kind=str(kind).upper();oid=int(owner_id)
    if kind not in ('STUDENT','GROUP'):raise ValueError('invalid_avatar_owner')
    if kind=='STUDENT':student_social_profile._profile(oid)
    custom=body.get('png') is not None
    if custom:data=png_image(body['png']);value='/api/visual/avatar/'+secrets.token_hex(16);avatar_kind='CUSTOM'
    else:
        value=str(body.get('avatar_value') or '');avatar_kind='PRESET'
        if value not in (STUDENT_PRESETS if kind=='STUDENT' else GROUP_PRESETS):raise ValueError('invalid_avatar_preset')
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        if kind=='GROUP':
            if not c.execute('SELECT 1 FROM study_groups WHERE id=? AND active=1',(oid,)).fetchone():raise ValueError('group_not_found')
        elif not c.execute('SELECT 1 FROM users WHERE id=? AND active=1',(oid,)).fetchone():raise PermissionError('student_not_found')
        c.execute('DELETE FROM profile_avatar_images WHERE owner_kind=? AND owner_id=?',(kind,oid))
        if custom:c.execute('INSERT INTO profile_avatar_images VALUES(?,?,?,?,?)',(value.rsplit('/',1)[-1],kind,oid,data,database.now_iso()))
        table,key=('study_groups','id') if kind=='GROUP' else ('student_social_profiles','user_id')
        onboarding=',onboarding_completed=1' if kind=='STUDENT' else ''
        c.execute(f'UPDATE {table} SET avatar_kind=?,avatar_value=?,updated_at=?{onboarding} WHERE {key}=?',(avatar_kind,value,database.now_iso(),oid))
    return {'status':'ok','avatar_kind':avatar_kind,'avatar_value':value}


def image(token,student_id=None,teacher=False):
    ensure_schema()
    if not re.fullmatch('[a-f0-9]{32}',str(token)):raise ValueError('avatar_not_found')
    with connection() as c:
        row=c.execute('SELECT * FROM profile_avatar_images WHERE token=?',(token,)).fetchone()
        if not row:raise ValueError('avatar_not_found')
        if row['owner_kind']=='GROUP':
            allowed=c.execute('SELECT 1 FROM study_groups WHERE id=? AND active=1',(row['owner_id'],)).fetchone() is not None
        else:
            uid=int(student_id) if student_id is not None else None
            allowed=teacher or uid==row['owner_id']
            if not allowed and uid:
                allowed=c.execute("""SELECT 1 FROM group_members a JOIN group_members b ON a.group_id=b.group_id
                  JOIN study_groups g ON g.id=a.group_id WHERE a.user_id=? AND b.user_id=?
                  AND a.status IN ('ACTIVE','PAUSED') AND b.status IN ('ACTIVE','PAUSED') AND g.active=1 LIMIT 1""",(uid,row['owner_id'])).fetchone() is not None
        if not allowed:raise PermissionError('avatar_not_available')
        return bytes(row['content'])


def teacher_chat(gid,limit=100):
    ensure_schema();gid=int(gid)
    with connection() as c:
        if not c.execute('SELECT 1 FROM study_groups WHERE id=? AND active=1',(gid,)).fetchone():raise ValueError('group_not_found')
        rows=c.execute('''SELECT m.id,m.sender_role,m.body,m.created_at,m.sender_user_id,
          COALESCE(p.display_name,u.name) AS sender_name,p.avatar_kind,p.avatar_value FROM group_chat_messages m
          LEFT JOIN users u ON u.id=m.sender_user_id LEFT JOIN student_social_profiles p ON p.user_id=m.sender_user_id
          WHERE m.group_id=? AND m.deleted_at IS NULL ORDER BY m.id DESC LIMIT ?''',(gid,max(1,min(int(limit),150)))).fetchall()
    return {'items':[{**dict(r),'mine':r['sender_role']=='TEACHER'} for r in reversed(rows)]}


def teacher_send(gid,teacher_id,text,client_id):
    ensure_schema();gid=int(gid);text=str(text or '').strip();client_id=str(client_id or '')
    if not text:raise ValueError('message_required')
    if len(text)>4000:raise ValueError('message_too_long')
    if not re.fullmatch('[a-zA-Z0-9_-]{16,80}',client_id):raise ValueError('invalid_message_key')
    sender='teacher:'+str(int(teacher_id));digest=hashlib.sha256(text.encode()).hexdigest()
    with connection() as c:
        c.execute('BEGIN IMMEDIATE')
        prior=c.execute('SELECT * FROM group_chat_client_ids WHERE group_id=? AND sender_key=? AND client_id=?',(gid,sender,client_id)).fetchone()
        if prior:
            if prior['body_hash']!=digest:raise ValueError('message_key_conflict')
            return {'status':'ok','message_id':prior['message_id'],'already_sent':True}
        g=c.execute('SELECT chat_mode FROM study_groups WHERE id=? AND active=1',(gid,)).fetchone()
        if not g:raise ValueError('group_not_found')
        if g['chat_mode']=='CLOSED':raise ValueError('group_chat_closed')
        cur=c.execute("INSERT INTO group_chat_messages(group_id,sender_role,body,created_at) VALUES(?,'TEACHER',?,?)",(gid,text,database.now_iso()))
        mid=int(cur.lastrowid);c.execute('INSERT INTO group_chat_client_ids VALUES(?,?,?,?,?)',(gid,sender,client_id,mid,digest))
    return {'status':'ok','message_id':mid,'already_sent':False}
