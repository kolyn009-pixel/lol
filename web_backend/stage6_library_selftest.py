"""Stage 6 isolated self-test. Never point it at production."""
from __future__ import annotations
import os,sys
DB=os.environ.get('ADELIA_DB_PATH','').strip()
if not DB or DB in {'tutor.db','/opt/tutorbot/tutor.db'}:raise SystemExit('Set ADELIA_DB_PATH to an isolated database copy')
from database import connect
from web_backend.library import create_collection,create_material,add_material_to_collection,add_task
from web_backend.library_stage6 import overview,collection_detail,update_task
from web_backend.pdf_import import create_import_draft,draft,approve_item,commit_job

def check(v,msg):
 if not v:raise AssertionError(msg)
def main():
 cid=create_collection('Stage6 selftest','temporary','PHYSICS',11,'BOOK');mid=create_material('Stage6 material','temporary','PHYSICS',11,11,'LINK',external_url='https://example.invalid',tags=['stage6']);add_material_to_collection(cid,mid);tid=add_task('PHYSICS','Найдите ускорение.',11,'EGE','Механика','Кинематика',cid,'selftest','1',answer='2',solution='a=F/m')
 try:
  o=overview('Stage6','PHYSICS');check(any(x['id']==mid for x in o['materials']),'material missing');check(any(x['id']==cid for x in o['collections']),'collection missing')
  d=collection_detail(cid);check(len(d['materials'])==1 and len(d['tasks'])==1,'collection relations broken')
  r=update_task(tid,{'difficulty':4,'topic':'Динамика'});check(r['status']=='ok','task update failed')
  text='[[PAGE 1]]\n1. Тело движется со скоростью 2 м/с. Найдите путь за 3 с.\n\n2. Найдите ускорение тела.\n\nОтветы\n1 - 6 м; 2 - 2 м/с2'
  job=create_import_draft(text,'stage6.pdf',collection_id=cid,page_count=1,defaults={'subject':'PHYSICS','grade':11,'topic':'Механика'});check(job['items']==2,'pdf parser did not split tasks')
  dr=draft(job['job_id']);check(len(dr['items'])==2,'draft missing items');approve_item(dr['items'][0]['id'],True);pub=commit_job(job['job_id']);check(pub['status']=='ok' and pub['created']==1,'approved PDF task was not published')
  print('STAGE6_LIBRARY_SELFTEST_OK')
 finally:
  conn=connect();conn.execute('DELETE FROM pdf_import_items WHERE job_id IN (SELECT id FROM pdf_import_jobs WHERE source_filename=?)',('stage6.pdf',));conn.execute('DELETE FROM pdf_import_jobs WHERE source_filename=?',('stage6.pdf',));conn.execute("DELETE FROM task_bank WHERE collection_id=? OR source_label=?",(cid,'stage6.pdf'));conn.execute('DELETE FROM collection_materials WHERE collection_id=?',(cid,));conn.execute('DELETE FROM materials WHERE id=?',(mid,));conn.execute('DELETE FROM material_collections WHERE id=?',(cid,));conn.commit();conn.close()
if __name__=='__main__':
 try:main()
 except Exception as exc:print('STAGE6_LIBRARY_SELFTEST_FAILED:',repr(exc),file=sys.stderr);raise
