"""Authenticated delivery of stored teaching materials.

Large PDFs are streamed with HTTP Range support so browsers do not have to
re-download a 100+ MB collection when opening or seeking inside it.
"""
from __future__ import annotations
from pathlib import Path
from urllib.parse import quote
from database import connect
from web_backend.pdf_storage import safe_material_path

CHUNK=1024*1024


def resolve_teacher(material_id):
    conn=connect();row=conn.execute("SELECT id,title,file_path,mime_type,original_filename,size_bytes,active FROM materials WHERE id=?",(int(material_id),)).fetchone();conn.close()
    if not row or not int(row['active'] or 0):return None
    p=safe_material_path(row['file_path'])
    if not p:return None
    return {'path':p,'title':row['title'],'mime_type':row['mime_type'] or 'application/pdf','filename':row['original_filename'] or p.name,'size':p.stat().st_size}


def resolve_student(material_id,user_id):
    conn=connect();row=conn.execute("""
      SELECT m.id,m.title,m.file_path,m.mime_type,m.original_filename,m.size_bytes,m.active
      FROM materials m
      WHERE m.id=? AND m.active=1 AND (
        EXISTS(SELECT 1 FROM material_access a WHERE a.material_id=m.id AND a.user_id=? AND a.access_scope='STUDENT') OR
        EXISTS(SELECT 1 FROM homework_material_links hml JOIN homework h ON h.id=hml.homework_id WHERE hml.material_id=m.id AND h.user_id=? AND h.status!='CANCELLED')
      ) LIMIT 1
    """,(int(material_id),int(user_id),int(user_id))).fetchone();conn.close()
    if not row:return None
    p=safe_material_path(row['file_path'])
    if not p:return None
    return {'path':p,'title':row['title'],'mime_type':row['mime_type'] or 'application/pdf','filename':row['original_filename'] or p.name,'size':p.stat().st_size}


def send(handler,item,inline=True):
    """Write a resolved file to BaseHTTPRequestHandler with single-range support."""
    path=Path(item['path']);size=int(item.get('size') or path.stat().st_size);start=0;end=size-1;status=200
    raw=handler.headers.get('Range','') or ''
    if raw.startswith('bytes=') and ',' not in raw:
        spec=raw[6:].strip()
        try:
            if spec.startswith('-'):
                length=max(1,int(spec[1:]));start=max(0,size-length)
            else:
                a,b=(spec.split('-',1)+[''])[:2];start=max(0,int(a));end=min(size-1,int(b)) if b else size-1
            if start> end or start>=size:raise ValueError
            status=206
        except Exception:
            handler.send_response(416);handler.send_header('Content-Range',f'bytes */{size}');handler.send_header('Content-Length','0');handler.end_headers();return
    length=end-start+1;name=str(item.get('filename') or path.name).replace('"','')
    handler.send_response(status);handler.send_header('Content-Type',item.get('mime_type') or 'application/octet-stream');handler.send_header('Accept-Ranges','bytes');handler.send_header('Cache-Control','private, max-age=0, must-revalidate');handler.send_header('X-Content-Type-Options','nosniff');handler.send_header('Content-Disposition',('inline' if inline else 'attachment')+f"; filename*=UTF-8''{quote(name)}")
    if status==206:handler.send_header('Content-Range',f'bytes {start}-{end}/{size}')
    handler.send_header('Content-Length',str(length));handler.end_headers()
    with open(path,'rb') as f:
        f.seek(start);remaining=length
        while remaining>0:
            chunk=f.read(min(CHUNK,remaining))
            if not chunk:break
            try:handler.wfile.write(chunk)
            except (BrokenPipeError,ConnectionResetError):break
            remaining-=len(chunk)
