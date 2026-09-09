"""Stage 6 isolated self-test. Never point it at production."""
from __future__ import annotations
import os,sys
DB=os.environ.get('ADELIA_DB_PATH','').strip()
if not DB or DB in {'tutor.db','/opt/tutorbot/tutor.db'}:raise SystemExit('Set ADELIA_DB_PATH to an isolated database copy')
from database import connect
from web_backend.library import create_collection,create_material,add_material_to_collection,add_task
from web_backend.library_stage6 import overview,collection_detail,update_task
from web_backend.pdf_import import create_import_draft,draft,approve_item,commit_job
from web_backend.stage6_api import Stage6Mixin
from web_backend import api_v2

def check(v,msg):
 if not v:raise AssertionError(msg)
def main():
 print('=== ADELIA STAGE 6 LIBRARY SELFTEST ===')
 check(issubclass(api_v2.Handler,Stage6Mixin),'Stage6Mixin is not wired into api_v2.Handler')
 cid=create_collection('Stage6 selftest','temporary','PHYSICS',11,'BOOK');mid=create_material('Stage6 material','temporary','PHYSICS',11,11,'LINK',external_url='https://example.invalid',tags=['stage6']);add_material_to_collection(cid,mid);tid=add_task('PHYSICS','Найдите ускорение.',11,'EGE','Механика','Кинематика',cid,'selftest','1',answer='2',solution='a=F/m')
 try:
  o=overview('Stage6','PHYSICS');check(any(x['id']==mid for x in o['materials']),'material missing');check(any(x['id']==cid for x in o['collections']),'collection missing');check(any(x['id']==tid for x in o['tasks']),'task missing')
  d=collection_detail(cid);check(len(d['materials'])==1 and len(d['tasks'])==1,'collection relations broken')
  r=update_task(tid,{'difficulty':4,'topic':'Динамика'});check(r['status']=='ok','task update failed')
  d=collection_detail(cid);updated=next(x for x in d['tasks'] if x['id']==tid);check(updated['difficulty']==4 and updated['topic']=='Динамика','task update not persisted')
  text='[[PAGE 1]]\n1. Тело движется со скоростью 2 м/с. Найдите путь за 3 с.\n\n2. Найдите ускорение тела.\n\nОтветы\n1 - 6 м; 2 - 2 м/с2'
  job=create_import_draft(text,'stage6.pdf',collection_id=cid,page_count=1,defaults={'subject':'PHYSICS','grade':11,'topic':'Механика'});check(job['items']==2,'pdf parser did not split tasks')
  dr=draft(job['job_id']);check(len(dr['items'])==2,'draft missing items');approve_item(dr['items'][0]['id'],True)
  pub=commit_job(job['job_id']);check(pub['status']=='ok' and pub['created']==1 and len(pub['task_ids'])==1,'approved PDF task was not published')
  published_id=int(pub['task_ids'][0]);again=commit_job(job['job_id']);check(again['status']=='ok' and again.get('already_imported') is True,'repeat publish is not idempotent');check(published_id in [int(x) for x in again['task_ids']],'repeat publish did not return existing task id')
  conn=connect();count=conn.execute("SELECT COUNT(*) FROM task_bank WHERE source_label=? AND task_number='1'",('stage6.pdf',)).fetchone()[0];conn.close();check(int(count)==1,'repeat publish duplicated task_bank row')
  print('api_v2 wiring: OK');print('library overview: OK');print('collection relations: OK');print('task update: OK');print('pdf parse/review/publish: OK');print('publish idempotency: OK');print('STAGE6_LIBRARY_SELFTEST_OK')
 finally:
  conn=connect();conn.execute('DELETE FROM pdf_import_items WHERE job_id IN (SELECT id FROM pdf_import_jobs WHERE source_filename=?)',('stage6.pdf',));conn.execute('DELETE FROM pdf_import_jobs WHERE source_filename=?',('stage6.pdf',));conn.execute("DELETE FROM task_bank WHERE collection_id=? OR source_label=?",(cid,'stage6.pdf'));conn.execute('DELETE FROM collection_materials WHERE collection_id=?',(cid,));conn.execute('DELETE FROM materials WHERE id=?',(mid,));conn.execute('DELETE FROM material_collections WHERE id=?',(cid,));conn.commit();conn.close()
if __name__=='__main__':
 try:main()
 except Exception as exc:print('STAGE6_LIBRARY_SELFTEST_FAILED:',repr(exc),file=sys.stderr);raise
