"""Durable Yandex.Disk archive for payment receipts.

Receipts are accepted locally first, then archived asynchronously. A temporary
Yandex outage must never block a student's payment submission. Configure with:
ADELIA_YANDEX_DISK_TOKEN and optional ADELIA_YANDEX_DISK_ROOT.
"""
from __future__ import annotations
import json,os,time
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import database

API='https://cloud-api.yandex.net/v1/disk/resources'
ROOT=os.environ.get('ADELIA_YANDEX_DISK_ROOT','/TutorBot/Receipts').rstrip('/')
TOKEN_ENV='ADELIA_YANDEX_DISK_TOKEN'


def _now():return database.now_iso()
def ensure_schema():
 c=database.connect();c.executescript("""CREATE TABLE IF NOT EXISTS receipt_cloud_archives(
 receipt_id INTEGER PRIMARY KEY,status TEXT NOT NULL DEFAULT 'PENDING',provider TEXT NOT NULL DEFAULT 'YANDEX_DISK',remote_path TEXT,attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT,next_attempt_at TEXT,archived_at TEXT,verified_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE);
 CREATE INDEX IF NOT EXISTS idx_receipt_archive_queue ON receipt_cloud_archives(status,next_attempt_at,receipt_id);""");c.commit();c.close()
def configured():return bool(os.environ.get(TOKEN_ENV,'').strip())
def enqueue(receipt_id):
 ensure_schema();now=_now();c=database.connect();c.execute("INSERT INTO receipt_cloud_archives(receipt_id,status,created_at,updated_at) VALUES(?,'PENDING',?,?) ON CONFLICT(receipt_id) DO NOTHING",(int(receipt_id),now,now));c.commit();c.close();return {'status':'queued','receipt_id':int(receipt_id)}
def _request(method,url,data=None,headers=None,timeout=25):
 h={'Authorization':'OAuth '+os.environ.get(TOKEN_ENV,'').strip(),'Accept':'application/json',**(headers or {})};req=Request(url,data=data,headers=h,method=method)
 with urlopen(req,timeout=timeout) as r:return r.status,r.read(),dict(r.headers)
def _remote_path(row):
 created=str(row['created_at'] or _now())[:10];year,month=created[:4],created[5:7];suffix={'PHOTO':'.jpg','DOCUMENT':'.pdf'}.get(str(row['file_type'] or '').upper(),Path(str(row['file_id'] or '')).suffix or '.bin');return f"{ROOT}/{year}/{month}/receipt_{int(row['id'])}_payment_{int(row['payment_id'])}_user_{int(row['user_id'])}{suffix}"
def _mkdir(path):
 parts=[p for p in path.strip('/').split('/') if p];current=''
 for part in parts:
  current+='/'+part;url=API+'?'+urlencode({'path':current})
  try:_request('PUT',url)
  except Exception:pass
def _upload(local_path,remote_path):
 parent=remote_path.rsplit('/',1)[0];_mkdir(parent);status,body,_=_request('GET',API+'/upload?'+urlencode({'path':remote_path,'overwrite':'true'}));href=json.loads(body.decode('utf-8'))['href'];raw=Path(local_path).read_bytes();req=Request(href,data=raw,method='PUT',headers={'Content-Type':'application/octet-stream','Content-Length':str(len(raw))})
 with urlopen(req,timeout=60) as r:
  if r.status not in (200,201,202):raise RuntimeError('yandex_upload_failed')
def _verify(remote_path):
 status,body,_=_request('GET',API+'?'+urlencode({'path':remote_path,'fields':'path,size,md5'}));return status==200 and bool(json.loads(body.decode('utf-8')).get('path'))
def process_one(receipt_id):
 ensure_schema()
 if not configured():raise RuntimeError('yandex_disk_not_configured')
 c=database.connect();row=c.execute("SELECT r.*,a.attempts FROM receipts r JOIN receipt_cloud_archives a ON a.receipt_id=r.id WHERE r.id=?",(int(receipt_id),)).fetchone();c.close()
 if not row:raise ValueError('receipt_archive_not_found')
 if str(row['source_platform'] or '').upper()!='WEB':raise ValueError('receipt_not_local')
 local=Path(str(row['file_id'] or ''))
 if not local.is_file():raise ValueError('receipt_file_not_found')
 remote=_remote_path(row);_upload(local,remote)
 if not _verify(remote):raise RuntimeError('yandex_verify_failed')
 now=_now();c=database.connect();c.execute("UPDATE receipt_cloud_archives SET status='ARCHIVED',remote_path=?,attempts=attempts+1,last_error=NULL,next_attempt_at=NULL,archived_at=COALESCE(archived_at,?),verified_at=?,updated_at=? WHERE receipt_id=?",(remote,now,now,now,int(receipt_id)));c.commit();c.close();return {'status':'ARCHIVED','receipt_id':int(receipt_id),'remote_path':remote}
def _fail(receipt_id,exc):
 ensure_schema();c=database.connect();row=c.execute('SELECT attempts FROM receipt_cloud_archives WHERE receipt_id=?',(int(receipt_id),)).fetchone();attempts=int(row['attempts'] or 0)+1 if row else 1;delay=min(3600,30*(2**min(attempts,7)));next_at=(datetime.now()+timedelta(seconds=delay)).isoformat(timespec='seconds');status='FAILED' if attempts>=10 else 'RETRY';c.execute("UPDATE receipt_cloud_archives SET status=?,attempts=?,last_error=?,next_attempt_at=?,updated_at=? WHERE receipt_id=?",(status,attempts,type(exc).__name__+': '+str(exc)[:300],next_at,_now(),int(receipt_id)));c.commit();c.close()
def run_once(limit=20):
 ensure_schema()
 if not configured():return {'status':'disabled','processed':0}
 c=database.connect();rows=c.execute("SELECT receipt_id FROM receipt_cloud_archives WHERE status IN ('PENDING','RETRY') AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY receipt_id LIMIT ?",(_now(),max(1,min(int(limit),100)))).fetchall();c.close();ok=failed=0
 for r in rows:
  try:process_one(int(r['receipt_id']));ok+=1
  except Exception as exc:_fail(int(r['receipt_id']),exc);failed+=1
 return {'status':'ok','processed':ok+failed,'archived':ok,'failed':failed}
def main():
 ensure_schema()
 while True:
  try:run_once(20)
  except Exception:pass
  time.sleep(30)
if __name__=='__main__':main()
