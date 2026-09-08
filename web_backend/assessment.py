"""Structured homework delivery and automatic scoring.

Teacher-only task_bank.answer/solution are never returned by student payloads.
Student homework pages receive statements and metadata only. Responses are
stored independently and scored server-side against normalized hidden answers.
"""
import math
import re
from database import connect, now_iso
from web_backend.library import ensure_tables as ensure_library_tables
from web_backend.homework_notifications import enqueue_teacher_auto_result


def ensure_tables():
    ensure_library_tables();conn=connect();conn.executescript("""
    CREATE TABLE IF NOT EXISTS homework_task_settings(id INTEGER PRIMARY KEY AUTOINCREMENT,homework_id INTEGER NOT NULL,task_id INTEGER NOT NULL,points REAL NOT NULL DEFAULT 1,answer_type TEXT NOT NULL DEFAULT 'TEXT',tolerance REAL,required INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(homework_id,task_id),FOREIGN KEY(homework_id) REFERENCES homework(id) ON DELETE CASCADE,FOREIGN KEY(task_id) REFERENCES task_bank(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS homework_task_responses(id INTEGER PRIMARY KEY AUTOINCREMENT,homework_id INTEGER NOT NULL,task_id INTEGER NOT NULL,user_id INTEGER NOT NULL,attempt_number INTEGER NOT NULL DEFAULT 1,response_text TEXT,is_correct INTEGER,points_awarded REAL,checked_at TEXT,created_at TEXT NOT NULL,updated_at TEXT,UNIQUE(homework_id,task_id,user_id,attempt_number),FOREIGN KEY(homework_id) REFERENCES homework(id) ON DELETE CASCADE,FOREIGN KEY(task_id) REFERENCES task_bank(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS homework_auto_results(homework_id INTEGER NOT NULL,user_id INTEGER NOT NULL,attempt_number INTEGER NOT NULL DEFAULT 1,total_points REAL NOT NULL DEFAULT 0,earned_points REAL NOT NULL DEFAULT 0,score_percent REAL NOT NULL DEFAULT 0,correct_tasks INTEGER NOT NULL DEFAULT 0,total_tasks INTEGER NOT NULL DEFAULT 0,completed_at TEXT NOT NULL,PRIMARY KEY(homework_id,user_id,attempt_number),FOREIGN KEY(homework_id) REFERENCES homework(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    """);conn.commit();conn.close()


def _norm(value):
    s=str(value or '').strip().lower().replace('ё','е').replace('−','-').replace('–','-').replace('×','*').replace('·','*');s=re.sub(r'\s+','',s);return s.replace(',','.')

def _answer_variants(raw):return [_norm(x) for x in str(raw or '').strip().split('|') if _norm(x)]
def _number(value):
    m=re.match(r'^([-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)',_norm(value))
    try:return float(m.group(1)) if m else None
    except:return None

def _check(response,answer,answer_type='TEXT',tolerance=None):
    variants=_answer_variants(answer)
    if not variants:return None
    if str(answer_type or 'TEXT').upper()=='NUMBER':
        rv=_number(response)
        if rv is None:return False
        tol=float(tolerance if tolerance is not None else 1e-6)
        return any((av:=_number(x)) is not None and math.isclose(rv,av,rel_tol=tol,abs_tol=tol) for x in variants)
    return _norm(response) in variants


def configure_task(homework_id,task_id,points=1,answer_type='TEXT',tolerance=None,required=True):
    ensure_tables();conn=connect();conn.execute("""INSERT INTO homework_task_settings(homework_id,task_id,points,answer_type,tolerance,required,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(homework_id,task_id) DO UPDATE SET points=excluded.points,answer_type=excluded.answer_type,tolerance=excluded.tolerance,required=excluded.required""",(int(homework_id),int(task_id),float(points or 1),str(answer_type or 'TEXT').upper(),float(tolerance) if tolerance is not None else None,int(bool(required)),now_iso()));conn.commit();conn.close()


def student_homework_payload(homework_id,user_id):
    ensure_tables();conn=connect();hw=conn.execute("SELECT * FROM homework WHERE id=? AND user_id=?",(int(homework_id),int(user_id))).fetchone()
    if not hw:conn.close();return None
    rows=conn.execute("""SELECT t.id,t.subject,t.grade,t.study_goal,t.section,t.topic,t.source_label,t.task_number,t.title,t.statement,t.difficulty,COALESCE(s.points,1) points,COALESCE(s.answer_type,'TEXT') answer_type FROM homework_task_links l JOIN task_bank t ON t.id=l.task_id LEFT JOIN homework_task_settings s ON s.homework_id=l.homework_id AND s.task_id=l.task_id WHERE l.homework_id=? AND t.active=1 ORDER BY l.sort_order,l.id""",(int(homework_id),)).fetchall();materials=conn.execute("""SELECT m.id,m.title,m.description,m.material_type,m.external_url,m.original_filename,m.mime_type,m.size_bytes FROM homework_material_links h JOIN materials m ON m.id=h.material_id WHERE h.homework_id=? AND m.active=1 ORDER BY h.id""",(int(homework_id),)).fetchall();conn.close();return {'homework':dict(hw),'tasks':[dict(r) for r in rows],'materials':[dict(r) for r in materials]}


def submit_structured(homework_id,user_id,responses,attempt_number=1):
    ensure_tables();payload=student_homework_payload(homework_id,user_id)
    if not payload:raise PermissionError('homework_not_found')
    responses=responses or {};conn=connect();now=now_iso();total=earned=0.0;correct=count=0;details=[]
    for task in payload['tasks']:
        tid=int(task['id']);row=conn.execute("""SELECT t.answer,COALESCE(s.points,1) points,COALESCE(s.answer_type,'TEXT') answer_type,s.tolerance FROM task_bank t LEFT JOIN homework_task_settings s ON s.homework_id=? AND s.task_id=t.id WHERE t.id=?""",(int(homework_id),tid)).fetchone();points=float(row['points'] or 1);response=responses.get(str(tid),responses.get(tid,''));ok=_check(response,row['answer'],row['answer_type'],row['tolerance'])
        if ok is not None:
            total+=points;count+=1
            if ok:earned+=points;correct+=1
        conn.execute("""INSERT INTO homework_task_responses(homework_id,task_id,user_id,attempt_number,response_text,is_correct,points_awarded,checked_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(homework_id,task_id,user_id,attempt_number) DO UPDATE SET response_text=excluded.response_text,is_correct=excluded.is_correct,points_awarded=excluded.points_awarded,checked_at=excluded.checked_at,updated_at=excluded.updated_at""",(int(homework_id),tid,int(user_id),int(attempt_number),str(response or ''),None if ok is None else int(ok),None if ok is None else (points if ok else 0),now,now,now));details.append({'task_id':tid,'auto_checked':ok is not None,'is_correct':ok,'points_awarded':None if ok is None else (points if ok else 0),'max_points':points})
    percent=round((earned/total*100),1) if total else 0.0;result={'status':'ok','score_percent':percent,'earned_points':earned,'total_points':total,'correct_tasks':correct,'total_tasks':count,'details':details}
    conn.execute("""INSERT OR REPLACE INTO homework_auto_results(homework_id,user_id,attempt_number,total_points,earned_points,score_percent,correct_tasks,total_tasks,completed_at) VALUES(?,?,?,?,?,?,?,?,?)""",(int(homework_id),int(user_id),int(attempt_number),total,earned,percent,correct,count,now));conn.execute("UPDATE homework SET status='UNDER_REVIEW',submitted_at=?,updated_at=? WHERE id=?",(now,now,int(homework_id)));user=conn.execute("SELECT name FROM users WHERE id=?",(int(user_id),)).fetchone();conn.commit();conn.close()
    enqueue_teacher_auto_result(int(homework_id),int(user_id),(user['name'] if user else 'Ученик'),result);return result


def teacher_result(homework_id,user_id,attempt_number=1):
    ensure_tables();conn=connect();res=conn.execute("SELECT * FROM homework_auto_results WHERE homework_id=? AND user_id=? AND attempt_number=?",(int(homework_id),int(user_id),int(attempt_number))).fetchone();rows=conn.execute("""SELECT r.*,t.title,t.statement,t.answer,t.solution FROM homework_task_responses r JOIN task_bank t ON t.id=r.task_id WHERE r.homework_id=? AND r.user_id=? AND r.attempt_number=? ORDER BY r.id""",(int(homework_id),int(user_id),int(attempt_number))).fetchall();conn.close();return {'result':dict(res) if res else None,'responses':[dict(r) for r in rows]}
