"""Structured homework delivery, automatic scoring and per-task feedback."""
import math,re
from database import connect,now_iso
from web_backend.library import ensure_tables as ensure_library_tables
from web_backend.homework_notifications import enqueue_teacher_auto_result
from web_backend.homework_status import canonical
AUTO_ACCEPT_PERCENT=100.0

def ensure_tables():
 ensure_library_tables();conn=connect();conn.executescript("""
 CREATE TABLE IF NOT EXISTS homework_task_settings(id INTEGER PRIMARY KEY AUTOINCREMENT,homework_id INTEGER NOT NULL,task_id INTEGER NOT NULL,points REAL NOT NULL DEFAULT 1,answer_type TEXT NOT NULL DEFAULT 'TEXT',tolerance REAL,required INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(homework_id,task_id));
 CREATE TABLE IF NOT EXISTS homework_task_responses(id INTEGER PRIMARY KEY AUTOINCREMENT,homework_id INTEGER NOT NULL,task_id INTEGER NOT NULL,user_id INTEGER NOT NULL,attempt_number INTEGER NOT NULL DEFAULT 1,response_text TEXT,is_correct INTEGER,points_awarded REAL,checked_at TEXT,created_at TEXT NOT NULL,updated_at TEXT,UNIQUE(homework_id,task_id,user_id,attempt_number));
 CREATE TABLE IF NOT EXISTS homework_auto_results(homework_id INTEGER NOT NULL,user_id INTEGER NOT NULL,attempt_number INTEGER NOT NULL DEFAULT 1,total_points REAL NOT NULL DEFAULT 0,earned_points REAL NOT NULL DEFAULT 0,score_percent REAL NOT NULL DEFAULT 0,correct_tasks INTEGER NOT NULL DEFAULT 0,total_tasks INTEGER NOT NULL DEFAULT 0,completed_at TEXT NOT NULL,submission_id INTEGER,review_id INTEGER,PRIMARY KEY(homework_id,user_id,attempt_number));
 CREATE TABLE IF NOT EXISTS homework_task_feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,homework_id INTEGER NOT NULL,task_id INTEGER NOT NULL,user_id INTEGER NOT NULL,attempt_number INTEGER NOT NULL,teacher_comment TEXT,override_correct INTEGER,override_points REAL,created_at TEXT NOT NULL,updated_at TEXT,UNIQUE(homework_id,task_id,user_id,attempt_number));
 CREATE INDEX IF NOT EXISTS idx_hw_task_feedback_lookup ON homework_task_feedback(homework_id,user_id,attempt_number);
 """);conn.commit();conn.close()
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
 if row:raise ValueError('attempt_already_submitted')
 cur=conn.execute("INSERT INTO homework_submissions(homework_id,user_id,attempt_number,student_comment,status,submitted_from,submitted_at) VALUES(?,?,?,?, 'SUBMITTED','WEB_STRUCTURED',?)",(int(homework_id),int(user_id),int(attempt),comment,now));return int(cur.lastrowid)
def _lifecycle(conn,homework_id,user_id):
 hw=conn.execute('SELECT status FROM homework WHERE id=? AND user_id=?',(int(homework_id),int(user_id))).fetchone()
 if not hw:return {'exists':False,'can_submit':False,'reason':'homework_not_found','next_attempt_number':1}
 latest=conn.execute('SELECT id,attempt_number,status,submitted_at,reviewed_at FROM homework_submissions WHERE homework_id=? AND user_id=? ORDER BY attempt_number DESC,id DESC LIMIT 1',(int(homework_id),int(user_id))).fetchone();review=None
 if latest:review=conn.execute('SELECT result,tutor_comment,accuracy_percent,reviewed_at FROM homework_reviews WHERE homework_id=? AND submission_id=? ORDER BY id DESC LIMIT 1',(int(homework_id),int(latest['id']))).fetchone()
 hs=canonical(hw['status']);result=str(review['result'] if review else '').upper();latest_attempt=int(latest['attempt_number'] or 0) if latest else 0
 completed=hs in ('COMPLETED','CANCELLED') or result=='ACCEPTED';revision=hs=='REVISION' or result=='REVISION';pending=bool(latest) and not completed and not revision
 can_submit=(not latest and hs not in ('COMPLETED','CANCELLED')) or revision
 reason=None if can_submit else ('homework_completed' if completed else 'attempt_pending_review')
 return {'exists':True,'can_submit':can_submit,'retry_allowed':bool(revision and can_submit),'pending_review':pending,'completed':completed,'reason':reason,'latest_attempt':latest_attempt,'next_attempt_number':latest_attempt+1 if latest else 1,'latest_submission':dict(latest) if latest else None,'latest_review':dict(review) if review else None}
def homework_lifecycle(homework_id,user_id):
 ensure_tables();conn=connect()
 try:return _lifecycle(conn,homework_id,user_id)
 finally:conn.close()
def next_attempt_number(homework_id,user_id):return int(homework_lifecycle(homework_id,user_id)['next_attempt_number'])
def recalculate_result(conn,homework_id,user_id,attempt_number,submission_id=None,review_id=None):
 hid=int(homework_id);uid=int(user_id);attempt=int(attempt_number);rows=conn.execute("SELECT r.is_correct,r.points_awarded,COALESCE(s.points,1) max_points FROM homework_task_responses r LEFT JOIN homework_task_settings s ON s.homework_id=r.homework_id AND s.task_id=r.task_id WHERE r.homework_id=? AND r.user_id=? AND r.attempt_number=? ORDER BY r.id",(hid,uid,attempt)).fetchall();total=earned=0.;correct=checked=0
 for row in rows:
  maxp=max(0.,float(row['max_points'] or 0));total+=maxp
  if row['points_awarded'] is not None:earned+=max(0.,min(float(row['points_awarded']),maxp if maxp>0 else float(row['points_awarded'])))
  if row['is_correct'] is not None:checked+=1;correct+=1 if int(row['is_correct']) else 0
 percent=round(earned/total*100,1) if total else 0.;now=now_iso();existing=conn.execute('SELECT submission_id,review_id FROM homework_auto_results WHERE homework_id=? AND user_id=? AND attempt_number=?',(hid,uid,attempt)).fetchone();sid=submission_id if submission_id is not None else (existing['submission_id'] if existing else None);rid=review_id if review_id is not None else (existing['review_id'] if existing else None)
 conn.execute("INSERT INTO homework_auto_results(homework_id,user_id,attempt_number,total_points,earned_points,score_percent,correct_tasks,total_tasks,completed_at,submission_id,review_id) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(homework_id,user_id,attempt_number) DO UPDATE SET total_points=excluded.total_points,earned_points=excluded.earned_points,score_percent=excluded.score_percent,correct_tasks=excluded.correct_tasks,total_tasks=excluded.total_tasks,completed_at=excluded.completed_at,submission_id=excluded.submission_id,review_id=excluded.review_id",(hid,uid,attempt,total,earned,percent,correct,len(rows),now,sid,rid));return {'total_points':round(total,2),'earned_points':round(earned,2),'score_percent':percent,'accuracy_percent':percent,'correct_tasks':correct,'total_tasks':len(rows),'checked_tasks':checked,'submission_id':sid,'review_id':rid}
def submit_structured(homework_id,user_id,responses,attempt_number=None):
 ensure_tables();payload=student_homework_payload(homework_id,user_id)
 if not payload:raise PermissionError('homework_not_found')
 if not payload['tasks']:raise ValueError('homework_has_no_tasks')
 conn=connect();life=_lifecycle(conn,homework_id,user_id)
 if not life['can_submit']:conn.close();raise ValueError(life['reason'] or 'submission_not_allowed')
 expected=int(life['next_attempt_number']);attempt=expected if attempt_number in (None,'','AUTO') else max(1,int(attempt_number))
 if attempt!=expected:conn.close();raise ValueError('invalid_attempt_number')
 now=now_iso();responses=responses or {};total=earned=0.;correct=count=unchecked=0;details=[]
 try:
  for task in payload['tasks']:
   tid=int(task['id']);row=conn.execute("SELECT t.answer,COALESCE(s.points,1) points,COALESCE(s.answer_type,'TEXT') answer_type,s.tolerance FROM task_bank t LEFT JOIN homework_task_settings s ON s.homework_id=? AND s.task_id=t.id WHERE t.id=?",(int(homework_id),tid)).fetchone();points=float(row['points'] or 1);response=responses.get(str(tid),responses.get(tid,''));ok=_check(response,row['answer'],row['answer_type'],row['tolerance'])
   if ok is None:unchecked+=1
   else:total+=points;count+=1;earned+=points if ok else 0;correct+=1 if ok else 0
   conn.execute("INSERT INTO homework_task_responses(homework_id,task_id,user_id,attempt_number,response_text,is_correct,points_awarded,checked_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(int(homework_id),tid,int(user_id),attempt,str(response or ''),None if ok is None else int(ok),None if ok is None else (points if ok else 0),now,now,now));details.append({'task_id':tid,'auto_checked':ok is not None,'is_correct':ok,'points_awarded':None if ok is None else(points if ok else 0),'max_points':points})
  percent=round(earned/total*100,1) if total else 0.;summary=f'Интерактивное ДЗ: {correct}/{count} авто-проверено, {percent}%'+(f'; ручная проверка: {unchecked}' if unchecked else '');sid=_canonical_submission(conn,homework_id,user_id,attempt,now,summary);rid=None
  if unchecked==0 and count>0 and percent>=AUTO_ACCEPT_PERCENT:
   cur=conn.execute("INSERT INTO homework_reviews(homework_id,submission_id,result,tutor_comment,reviewed_at,total_tasks,correct_tasks,accuracy_percent) VALUES(?,?,'ACCEPTED',?,?,?,?,?)",(int(homework_id),sid,'Автопроверка: все ответы верны.',now,count,correct,percent));rid=int(cur.lastrowid);conn.execute("UPDATE homework_submissions SET status='REVIEWED',reviewed_at=? WHERE id=?",(now,sid));conn.execute("UPDATE homework SET status='COMPLETED',submitted_at=?,reviewed_at=?,updated_at=? WHERE id=?",(now,now,now,int(homework_id)))
  else:conn.execute("UPDATE homework SET status='SUBMITTED',submitted_at=?,updated_at=? WHERE id=?",(now,now,int(homework_id)))
  result={'status':'ok','attempt_number':attempt,'score_percent':percent,'earned_points':earned,'total_points':total,'correct_tasks':correct,'total_tasks':count,'unchecked_tasks':unchecked,'submission_id':sid,'auto_accepted':bool(rid),'details':details};recalculate_result(conn,homework_id,user_id,attempt,sid,rid);user=conn.execute('SELECT name FROM users WHERE id=?',(int(user_id),)).fetchone();conn.commit()
 except Exception:conn.rollback();conn.close();raise
 conn.close();enqueue_teacher_auto_result(int(homework_id),int(user_id),(user['name'] if user else 'Ученик'),result,attempt_number=attempt);return result
def save_task_feedback(homework_id,task_id,user_id,attempt_number,comment=None,is_correct=None,points_awarded=None):
 ensure_tables();hid=int(homework_id);tid=int(task_id);uid=int(user_id);attempt=max(1,int(attempt_number));comment=str(comment or '').strip() or None;conn=connect();resp=conn.execute("SELECT id FROM homework_task_responses WHERE homework_id=? AND task_id=? AND user_id=? AND attempt_number=?",(hid,tid,uid,attempt)).fetchone()
 if not resp:conn.close();return {'status':'response_not_found'}
 now=now_iso();oc=None if is_correct is None else int(bool(is_correct));op=None if points_awarded in (None,'') else max(0.0,float(points_awarded));conn.execute("INSERT INTO homework_task_feedback(homework_id,task_id,user_id,attempt_number,teacher_comment,override_correct,override_points,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(homework_id,task_id,user_id,attempt_number) DO UPDATE SET teacher_comment=excluded.teacher_comment,override_correct=excluded.override_correct,override_points=excluded.override_points,updated_at=excluded.updated_at",(hid,tid,uid,attempt,comment,oc,op,now,now))
 if oc is not None or op is not None:conn.execute("UPDATE homework_task_responses SET is_correct=COALESCE(?,is_correct),points_awarded=COALESCE(?,points_awarded),checked_at=?,updated_at=? WHERE id=?",(oc,op,now,now,int(resp['id'])))
 aggregate=recalculate_result(conn,hid,uid,attempt);conn.commit();conn.close();return {'status':'ok','result':aggregate}
def student_feedback(homework_id,user_id):
 ensure_tables();conn=connect();rows=conn.execute("SELECT f.task_id,f.attempt_number,f.teacher_comment,f.override_correct,f.override_points,t.title,t.task_number FROM homework_task_feedback f JOIN task_bank t ON t.id=f.task_id WHERE f.homework_id=? AND f.user_id=? ORDER BY f.attempt_number DESC,f.task_id",(int(homework_id),int(user_id))).fetchall();subs=conn.execute("SELECT attempt_number,status,submitted_at,reviewed_at FROM homework_submissions WHERE homework_id=? AND user_id=? ORDER BY attempt_number DESC",(int(homework_id),int(user_id))).fetchall();reviews=conn.execute("SELECT r.result,r.tutor_comment,r.accuracy_percent,r.reviewed_at,s.attempt_number FROM homework_reviews r JOIN homework_submissions s ON s.id=r.submission_id WHERE r.homework_id=? AND s.user_id=? ORDER BY r.reviewed_at DESC",(int(homework_id),int(user_id))).fetchall();life=_lifecycle(conn,homework_id,user_id);conn.close();return {'task_feedback':[dict(r) for r in rows],'submissions':[dict(r) for r in subs],'reviews':[dict(r) for r in reviews],**life}
def teacher_result(homework_id,user_id,attempt_number=1):
 ensure_tables();conn=connect();res=conn.execute('SELECT * FROM homework_auto_results WHERE homework_id=? AND user_id=? AND attempt_number=?',(int(homework_id),int(user_id),int(attempt_number))).fetchone();rows=conn.execute('SELECT r.*,t.title,t.statement,t.answer,t.solution,f.teacher_comment,f.override_correct,f.override_points FROM homework_task_responses r JOIN task_bank t ON t.id=r.task_id LEFT JOIN homework_task_feedback f ON f.homework_id=r.homework_id AND f.task_id=r.task_id AND f.user_id=r.user_id AND f.attempt_number=r.attempt_number WHERE r.homework_id=? AND r.user_id=? AND r.attempt_number=? ORDER BY r.id',(int(homework_id),int(user_id),int(attempt_number))).fetchall();conn.close();return {'result':dict(res) if res else None,'responses':[dict(r) for r in rows]}