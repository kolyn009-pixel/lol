"""Durable receipt archive on Yandex Disk.

The accounting database remains the source of truth. Receipt files are copied to
cloud storage asynchronously; payment processing never waits for Yandex Disk.
Supports local WEB receipts and Telegram / Telegram-parent receipts.
"""
from __future__ import annotations
import hashlib,json,os,re
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import quote,urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from database import connect,now_iso

DISK_API='https://cloud-api.yandex.net/v1/disk'
TELEGRAM_API='https://api.telegram.org'
ARCHIVE_ROOT=os.getenv('ADELIA_RECEIPT_ARCHIVE_ROOT','/TutorBot/Receipts').rstrip('/')
MAX_RECEIPT_BYTES=25*1024*1024;MAX_ATTEMPTS=12

def ensure_table():
 c=connect();c.executescript("""CREATE TABLE IF NOT EXISTS receipt_cloud_archives(receipt_id INTEGER PRIMARY KEY,provider TEXT NOT NULL DEFAULT 'YANDEX_DISK',remote_path TEXT,sha256 TEXT,size_bytes INTEGER,status TEXT NOT NULL DEFAULT 'PENDING',attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT,archived_at TEXT,verified_at TEXT,updated_at TEXT NOT NULL,FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE);CREATE INDEX IF NOT EXISTS idx_receipt_cloud_archive_status ON receipt_cloud_archives(status,updated_at);""");c.commit();c.close()
def configured():return bool(os.getenv('YANDEX_DISK_OAUTH_TOKEN','').strip())
def _safe_name(v,fallback='receipt'):
 text=re.sub(r'[^0-9A-Za-zА-Яа-я._-]+','_',str(v or '').strip(),flags=re.UNICODE).strip('._-')[:80];return text or fallback
def _ext(item):
 ft=str(item.get('file_type') or '').upper();src=str(item.get('source_platform') or '').upper();path=str(item.get('file_id') or '')
 if src=='WEB' and Path(path).suffix.lower() in {'.pdf','.jpg','.jpeg','.png','.webp'}:return Path(path).suffix.lower().lstrip('.')
 return {'DOCUMENT':'pdf','PHOTO':'jpg','PDF':'pdf','JPG':'jpg','JPEG':'jpeg','PNG':'png','WEBP':'webp'}.get(ft,'bin')
def _receipt(rid):
 c=connect();cols={str(r['name']) for r in c.execute('PRAGMA table_info(receipts)').fetchall()};file_expr='telegram_file_id' if 'telegram_file_id' in cols else 'file_id';row=c.execute(f"SELECT r.id,r.payment_id,r.user_id,r.file_id,{file_expr} AS telegram_file_id,r.source_platform,r.file_type,r.created_at,u.name FROM receipts r JOIN users u ON u.id=r.user_id WHERE r.id=? LIMIT 1",(int(rid),)).fetchone();c.close();return dict(row) if row else None
def _telegram_bytes(file_id):
 token=os.getenv('BOT_TOKEN','').strip()
 if not token:raise RuntimeError('telegram_bot_token_missing')
 with urlopen(f"{TELEGRAM_API}/bot{token}/getFile?{urlencode({'file_id':str(file_id)})}",timeout=20) as resp:p=json.loads(resp.read().decode())
 remote=(p.get('result') or {}).get('file_path') if p.get('ok') else None
 if not remote:raise RuntimeError('telegram_file_lookup_failed')
 with urlopen(f"{TELEGRAM_API}/file/bot{token}/{quote(remote,safe='/')}",timeout=30) as resp:
  if int(resp.headers.get('Content-Length') or 0)>MAX_RECEIPT_BYTES:raise RuntimeError('receipt_file_too_large')
  data=resp.read(MAX_RECEIPT_BYTES+1)
 if len(data)>MAX_RECEIPT_BYTES:raise RuntimeError('receipt_file_too_large')
 return data
def _local_bytes(path_value):
 path=Path(str(path_value or ''))
 if not path.is_file():raise RuntimeError('receipt_file_not_found')
 size=path.stat().st_size
 if size<=0 or size>MAX_RECEIPT_BYTES:raise RuntimeError('receipt_file_too_large')
 return path.read_bytes()
def _receipt_bytes(item):
 src=str(item.get('source_platform') or '').upper()
 if src=='WEB':return _local_bytes(item.get('file_id'))
 if src in {'TELEGRAM','TG','TELEGRAM_PARENT'}:
  fid=item.get('telegram_file_id') or item.get('file_id')
  if not fid:raise RuntimeError('telegram_file_id_missing')
  return _telegram_bytes(fid)
 raise RuntimeError('receipt_source_not_supported')
def _disk(method,path,params=None,data=None,content_type=None):
 token=os.getenv('YANDEX_DISK_OAUTH_TOKEN','').strip()
 if not token:raise RuntimeError('yandex_disk_token_missing')
 url=DISK_API+path+('?'+urlencode(params) if params else '');headers={'Authorization':f'OAuth {token}','Accept':'application/json'}
 if content_type:headers['Content-Type']=content_type
 try:
  with urlopen(Request(url,data=data,headers=headers,method=method),timeout=25) as resp:
   raw=resp.read();return json.loads(raw.decode()) if raw else {}
 except HTTPError as exc:
  if method=='PUT' and path=='/resources' and exc.code==409:return {}
  raise RuntimeError(f'yandex_disk_http_{exc.code}') from None
def _mkdirs(path):
 cur=''
 for p in [x for x in str(path).split('/') if x]:cur+='/'+p;_disk('PUT','/resources',{'path':cur})
def _upload(remote,data):
 _mkdirs(remote.rsplit('/',1)[0]);href=_disk('GET','/resources/upload',{'path':remote,'overwrite':'true'}).get('href')
 if not href:raise RuntimeError('yandex_upload_link_missing')
 try:
  with urlopen(Request(href,data=data,headers={'Content-Type':'application/octet-stream'},method='PUT'),timeout=60) as resp:
   if int(getattr(resp,'status',200)) not in {200,201,202,204}:raise RuntimeError('yandex_upload_failed')
 except HTTPError as exc:raise RuntimeError(f'yandex_upload_http_{exc.code}') from None
def _remote_path(item):
 try:dt=datetime.fromisoformat(str(item.get('created_at') or ''))
 except Exception:dt=datetime.now()
 student=_safe_name(item.get('name'),f"student_{item['user_id']}");return f"{ARCHIVE_ROOT}/{dt:%Y}/{dt:%m}/{student}_{int(item['user_id'])}/payment_{int(item['payment_id'])}_receipt_{int(item['id'])}.{_ext(item)}"
def _retry_seconds(n):return min(6*60*60,60*(2**max(0,min(int(n),8))))
def enqueue(receipt_id):
 ensure_table();rid=int(receipt_id);c=connect();c.execute("INSERT INTO receipt_cloud_archives(receipt_id,status,attempts,updated_at) VALUES(?,'PENDING',0,?) ON CONFLICT(receipt_id) DO NOTHING",(rid,now_iso()));c.commit();c.close();return {'status':'queued','receipt_id':rid}
def archive_receipt(receipt_id):
 ensure_table();rid=int(receipt_id);c=connect();existing=c.execute('SELECT * FROM receipt_cloud_archives WHERE receipt_id=?',(rid,)).fetchone()
 if existing and str(existing['status']).upper()=='ARCHIVED':out=dict(existing);c.close();return {'status':'ok','archive':out,'already_archived':True}
 if existing and int(existing['attempts'] or 0)>=MAX_ATTEMPTS:out=dict(existing);c.close();return {'status':'failed','archive':out,'max_attempts':True}
 c.execute("INSERT INTO receipt_cloud_archives(receipt_id,status,attempts,updated_at) VALUES(?,'PENDING',0,?) ON CONFLICT(receipt_id) DO UPDATE SET updated_at=excluded.updated_at",(rid,now_iso()));c.commit();c.close();item=_receipt(rid)
 if not item:raise ValueError('receipt_not_found')
 try:
  data=_receipt_bytes(item);digest=hashlib.sha256(data).hexdigest();remote=_remote_path(item);_upload(remote,data);now=now_iso();c=connect();c.execute("UPDATE receipt_cloud_archives SET provider='YANDEX_DISK',remote_path=?,sha256=?,size_bytes=?,status='ARCHIVED',attempts=attempts+1,last_error=NULL,archived_at=?,verified_at=NULL,updated_at=? WHERE receipt_id=?",(remote,digest,len(data),now,now,rid));c.commit();row=c.execute('SELECT * FROM receipt_cloud_archives WHERE receipt_id=?',(rid,)).fetchone();c.close();return {'status':'ok','archive':dict(row)}
 except Exception as exc:
  c=connect();c.execute("UPDATE receipt_cloud_archives SET status=CASE WHEN attempts+1>=? THEN 'FAILED' ELSE 'RETRY' END,attempts=attempts+1,last_error=?,updated_at=? WHERE receipt_id=?",(MAX_ATTEMPTS,str(exc)[:160],now_iso(),rid));c.commit();c.close();return {'status':'retry','error':str(exc)[:160],'receipt_id':rid}
def verify_archive(receipt_id):
 ensure_table();rid=int(receipt_id);c=connect();row=c.execute("SELECT * FROM receipt_cloud_archives WHERE receipt_id=? AND status='ARCHIVED'",(rid,)).fetchone();c.close()
 if not row:return {'status':'not_archived','receipt_id':rid}
 try:
  meta=_disk('GET','/resources',{'path':row['remote_path'],'fields':'path,size,sha256,md5,type'});size_ok=int(meta.get('size') or -1)==int(row['size_bytes'] or -1);remote_sha=str(meta.get('sha256') or '').lower();expected=str(row['sha256'] or '').lower();hash_ok=(remote_sha==expected) if remote_sha else None;ok=size_ok and hash_ok is not False;c=connect();c.execute('UPDATE receipt_cloud_archives SET verified_at=?,last_error=?,updated_at=? WHERE receipt_id=?',(now_iso(),None if ok else 'cloud_integrity_mismatch',now_iso(),rid));c.commit();c.close();return {'status':'ok' if ok else 'mismatch','receipt_id':rid,'size_ok':size_ok,'hash_ok':hash_ok}
 except Exception as exc:return {'status':'error','receipt_id':rid,'error':str(exc)[:160]}
def verify_archived(limit=20):
 ensure_table();c=connect();rows=c.execute("SELECT receipt_id FROM receipt_cloud_archives WHERE status='ARCHIVED' ORDER BY COALESCE(verified_at,'') ASC,receipt_id LIMIT ?",(max(1,min(int(limit),100)),)).fetchall();c.close();return [verify_archive(int(r['receipt_id'])) for r in rows]
def archive_pending(limit=20):
 ensure_table();limit=max(1,min(int(limit),100));c=connect();rows=c.execute("SELECT r.id,a.attempts,a.updated_at,a.status FROM receipts r LEFT JOIN receipt_cloud_archives a ON a.receipt_id=r.id WHERE a.receipt_id IS NULL OR a.status IN ('PENDING','RETRY') ORDER BY r.id LIMIT ?",(max(limit*5,limit),)).fetchall();c.close();now=datetime.now();due=[]
 for r in rows:
  if len(due)>=limit:break
  if r['status'] is None or str(r['status']).upper()=='PENDING':due.append(int(r['id']));continue
  try:updated=datetime.fromisoformat(str(r['updated_at']))
  except Exception:updated=now-timedelta(days=1)
  if now-updated>=timedelta(seconds=_retry_seconds(r['attempts'] or 0)):due.append(int(r['id']))
 return [archive_receipt(x) for x in due]
def queue_stats():
 ensure_table();c=connect();rows=c.execute('SELECT status,COUNT(*) c FROM receipt_cloud_archives GROUP BY status').fetchall();total=c.execute('SELECT COUNT(*) c FROM receipts').fetchone();c.close();counts={str(r['status']).upper():int(r['c'] or 0) for r in rows};tracked=sum(counts.values());return {'receipts_total':int(total['c'] or 0),'untracked':max(0,int(total['c'] or 0)-tracked),'pending':counts.get('PENDING',0),'retry':counts.get('RETRY',0),'archived':counts.get('ARCHIVED',0),'failed':counts.get('FAILED',0)}
