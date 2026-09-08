"""Structured homework delivery and automatic scoring."""
import math,re
from database import connect,now_iso
from web_backend.library import ensure_tables as ensure_library_tables
from web_backend.homework_notifications import enqueue_teacher_auto_result
AUTO_ACCEPT_PERCENT=100.0

def ensure_tables():
 ensure_library_tables();conn=connect();conn.executescript("""CREATE TABLE IF NOT EXISTS homework_task_settings(id INTEGER PRIMARY KEY AUTOINCREMENT,homework_id INTEGER NOT NULL,task_id INTEGER NOT NULL,points REAL NOT NULL DEFAULT 1,answer_type TEXT NOT NULL DEFAULT 'TEXT',tolerance REAL,required INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(homework_id,task_id));CREATE TABLE IF NOT EXISTS homework_task_responses(id INTEGER PRIMARY KEY AUTOINCREMENT,homework_id INTEGER NOT NULL,task_id INTEGER NOT NULL,user_id INTEGER NOT NULL,attempt_number INTEGER NOT NULL DEFAULT 1,response_text TEXT,is_correct INTEGER,points_awarded REAL,checked_at TEXT,created_at TEXT NOT NULL,updated_at TEXT,UNIQUE(homework_id,task_id,user_id,attempt_number));CREATE TABLE IF NOT EXISTS homework_auto_results(homework_id INTEGER NOT NULL,user_id INTEGER NOT NULL,attempt_number INTEGER NOT NULL DEFAULT 1,total_points REAL NOT NULL DEFAULT 0,earned_points REAL NOT NULL DEFAULT 0,score_percent REAL NOT NULL DEFAULT 0,correct_tasks INTEGER NOT NULL DEFAULT 0,total_tasks INTEGER NOT NULL DEFAULT 0,completed_at TEXT NOT NULL,submission_id INTEGER,review_id INTEGER,PRIMARY KEY(homework_id,user_id,attempt_number));""");conn.commit();conn.close()
def _norm(v):return re.sub(r'\s+','',str(v or '').strip().lower().replace('ё','е').replace(',','.').replace('−','-').replace('–','-'))
def _variants(v):return [_norm(x) for x in str(v or '').split('|') if _norm(x)]
def _number(v):
 m=re.match(r'^([-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)',_norm(v))
 try:return float(m.group(1)) if m else None
 except:return None
def _check(response,answer,answer_type='TEXT',tolerance=None):
 vs=_variants(answer)
 if not vs:return None
 if str(answer_type).upper()=='NUMBER':
  rv=_number(response)
  if rv is None:return False
  tol=float(tolerance if tolerance is not None else 1e-6);return any((av:=_number(x)) is not None and math.isclose(rv,av,rel_tol=tol,abs_tol=tol) for x in vs)
 return _norm(response) in vs
def configure_task(homework_id,task_id,points=1,answer_type='TEXT',tolerance=None,required=True):
 ensure_tables();conn=connect();conn.execute("INSERT INTO homework_task_settings(homework_id,task_id,points,answer_type,tolerance,required,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(homework_id,task_id) DO UPDATE SET points=excluded.points,answer_type=excluded.answer_type,tolerance=excluded.tolerance,required=excluded.required",(int(homework_id),int(task_id),float(points or 1),str(answer_type or 'TEXT').upper(),float(tolerance) if tolerance is not None else None,int(bool(required)),now_iso()));conn.commit();conn.close()
def student_homework_payload(homework_id,user_id):
 ensure_tables();conn=connect();hw=conn.execute('SELECT * FROM homework WHERE id=? AND user_id=?',(int(homework_id),int(user_id))).fetchone()
 if not hw:conn.close();return None
 rows=conn.execute("SELECT t.id,t.subject,t.grade,t.study_goal,t.section,t.topic,t.source_label,t.task_number,t.title,t.statement,t.difficulty,COALESCE(s.points,1) points,COALESCE(s.answer_type,'TEXT') answer_type FROM homework_task_links l JOIN task_bank t ON t.id=l.task_id LEFT JOIN homework_task_settings s ON s.homework_id=l.homework_id AND s.task_id=l.task_id WHERE l.homework_id=? AND t.active=1 ORDER BY l.sort_order,l.id",(int(homework_id),)).fetchall();materials=conn.execute("SELECT m.id,m.title,m.description,m.material_type,m.external_url,m.original_filename,m.mime_type,m.size_bytes FROM homework_material_links h JOIN materials m ON m.id=h.material_id WHERE h.homework_id=? AND m.active=1 ORDER BY h.id",(int(homework_id),)).fetchall();conn.close();return {'homework':dict(hw),'tasks':[dict(r) for r in rows],'materials':[dict(r) for r in materials]}
def _canonical_submission(conn,homework_id,user_id,attempt,now,comment):
 row=conn.execute('SELECT id,status FROM homework_submissions WHERE homework_id=? AND user_id=? AND attempt_number=? ORDER BY id DESC LIMIT 1',(int(homework_id),int(user_id),int(attempt))).fetchone()
 if row:
  if str(row['status']).upper() in ('REVIEWED','ACCEPTED'):raise ValueError('attempt_already_reviewed')
  conn.execute("UPDATE homework_submissions SET student_comment=?,status='SUBMITTED',submitted_from='WEB_STRUCTURED',submitted_at=?,reviewed_at=NULL WHERE id=?",(comment,now,int(row['id'])));return int(row['id'])
 cur=conn.execute("INSERT INTO homework_submissions(homework_id,user_id,attempt_number,student_comment,status,submitted_from,submitted_at) VALUES(?,?,?,?, 'SUBMITTED','WEB_STRUCTURED',?)",(int(homework_id),int(user_id),int(attempt),comment,now));return int(cur.lastrowid)
def submit_structured(homework_id,user_id,responses,attempt_number=1):
 ensure_tables();payload=student_homework_payload(homework_id,user_id)
 if not payload:raise PermissionError('homework_not_found')
 if not payload['tasks']:raise ValueError('homework_has_no_tasks')
 attempt=max(1,int(attempt_number));conn=connect()
 old=conn.execute('SELECT id,status FROM homework_submissions WHERE homework_id=? AND user_id=? AND attempt_number=? ORDER BY id DESC LIMIT 1',(int(homework_id),int(user_id),attempt)).fetchone()
 if old and str(old['status']).upper() in ('REVIEWED','ACCEPTED'):conn.close();raise ValueError('attempt_already_reviewed')
 now=now_iso();responses=responses or {};total=earned=0.;correct=count=unchecked=0;details=[]
 try:
  for task in payload['tasks']:
   tid=int(task['id']);row=conn.execute("SELECT t.answer,COALESCE(s.points,1) points,COALESCE(s.answer_type,'TEXT') answer_type,s.tolerance FROM task_bank t LEFT JOIN homework_task_settings s ON s.homework_id=? AND s.task_id=t.id WHERE t.id=?",(int(homework_id),tid)).fetchone();points=float(row['points'] or 1);response=responses.get(str(tid),responses.get(tid,''));ok=_check(response,row['answer'],row['answer_type'],row['tolerance'])
   if ok is None:unchecked+=1
   else:
    total+=points;count+=1
    if ok:earned+=points;correct+=1
   conn.execute("INSERT INTO homework_task_responses(homework_id,task_id,user_id,attempt_number,response_text,is_correct,points_awarded,checked_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(homework_id,task_id,user_id,attempt_number) DO UPDATE SET response_text=excluded.response_text,is_correct=excluded.is_correct,points_awarded=excluded.points_awarded,checked_at=excluded.checked_at,updated_at=excluded.updated_at",(int(homework_id),tid,int(user_id),attempt,str(response or ''),None if ok is None else int(ok),None if ok is None else (points if ok else 0),now,now,now));details.append({'task_id':tid,'auto_checked':ok is not None,'is_correct':ok,'points_awarded':None if ok is None else(points if ok else 0),'max_points':points})
  percent=round(earned/total*100,1) if total else 0.;summary=f'Интерактивное ДЗ: {correct}/{count} авто-проверено, {percent}%'+(f'; ручная проверка: {unchecked}' if unchecked else '');sid=_canonical_submission(conn,homework_id,user_id,attempt,now,summary);rid=None
  if unchecked==0 and count>0 and percent>=AUTO_ACCEPT_PERCENT:
   cur=conn.execute("INSERT INTO homework_reviews(homework_id,submission_id,result,tutor_comment,reviewed_at,total_tasks,correct_tasks,accuracy_percent) VALUES(?,?,'ACCEPTED',?,?,?,?,?)",(int(homework_id),sid,'Автопроверка: все ответы верны.',now,count,correct,percent));rid=int(cur.lastrowid);conn.execute("UPDATE homework_submissions SET status='REVIEWED',reviewed_at=? WHERE id=?",(now,sid));conn.execute("UPDATE homework SET status='COMPLETED',submitted_at=?,reviewed_at=?,updated_at=? WHERE id=?",(now,now,now,int(homework_id)))
  else:conn.execute("UPDATE homework SET status='SUBMITTED',submitted_at=?,updated_at=? WHERE id=?",(now,now,int(homework_id)))
  result={'status':'ok','attempt_number':attempt,'score_percent':percent,'earned_points':earned,'total_points':total,'correct_tasks':correct,'total_tasks':count,'unchecked_tasks':unchecked,'submission_id':sid,'auto_accepted':bool(rid),'details':details}
  conn.execute("INSERT INTO homework_auto_results(homework_id,user_id,attempt_number,total_points,earned_points,score_percent,correct_tasks,total_tasks,completed_at,submission_id,review_id) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(homework_id,user_id,attempt_number) DO UPDATE SET total_points=excluded.total_points,earned_points=excluded.earned_points,score_percent=excluded.score_percent,correct_tasks=excluded.correct_tasks,total_tasks=excluded.total_tasks,completed_at=excluded.completed_at,submission_id=excluded.submission_id,review_id=excluded.review_id",(int(homework_id),int(user_id),attempt,total,earned,percent,correct,count,now,sid,rid));user=conn.execute('SELECT name FROM users WHERE id=?',(int(user_id),)).fetchone();conn.commit()
 except Exception:conn.rollback();conn.close();raise
 conn.close();enqueue_teacher_auto_result(int(homework_id),int(user_id),(user['name'] if user else 'Ученик'),result,attempt_number=attempt);return result
def teacher_result(homework_id,user_id,attempt_number=1):
 ensure_tables();conn=connect();res=conn.execute('SELECT * FROM homework_auto_results WHERE homework_id=? AND user_id=? AND attempt_number=?',(int(homework_id),int(user_id),int(attempt_number))).fetchone();rows=conn.execute('SELECT r.*,t.title,t.statement,t.answer,t.solution FROM homework_task_responses r JOIN task_bank t ON t.id=r.task_id WHERE r.homework_id=? AND r.user_id=? AND r.attempt_number=? ORDER BY r.id',(int(homework_id),int(user_id),int(attempt_number))).fetchall();conn.close();return {'result':dict(res) if res else None,'responses':[dict(r) for r in rows]}
