"""Teacher homework center: one feed for manual, interactive and external homework."""
from datetime import datetime
from database import connect

ACTIVE={'ASSIGNED','SUBMITTED','UNDER_REVIEW','REVISION','REVIEWED'}


def _rowdict(r): return dict(r) if r else None


def list_homework(status=None,user_id=None,mode=None,search=None,limit=200):
    conn=connect();where=['1=1'];params=[]
    if status:
        st=str(status).upper()
        if st=='OVERDUE':
            where.append("h.deadline IS NOT NULL AND h.deadline<? AND h.status NOT IN ('COMPLETED','CANCELLED')");params.append(datetime.now().isoformat(timespec='seconds'))
        elif st=='NEEDS_REVIEW':
            where.append("EXISTS(SELECT 1 FROM homework_submissions s WHERE s.homework_id=h.id AND s.status='SUBMITTED')")
        else:
            where.append('h.status=?');params.append(st)
    if user_id is not None:where.append('h.user_id=?');params.append(int(user_id))
    if mode:
        m=str(mode).upper();mapping={'MANUAL':'MAIN','INTERACTIVE':'INTERACTIVE','EXTERNAL':'EXTERNAL'};where.append('h.homework_type=?');params.append(mapping.get(m,m))
    if search:
        q='%'+str(search).lower()+'%';where.append("(LOWER(COALESCE(h.title,'')) LIKE ? OR LOWER(COALESCE(h.description,'')) LIKE ? OR LOWER(COALESCE(u.name,'')) LIKE ?)");params += [q,q,q]
    rows=conn.execute(f"""
      SELECT h.id,h.user_id,h.lesson_id,h.study_goal,h.subject,h.title,h.description,h.homework_type,h.source_type,h.source_reference,h.source_url,h.deadline,h.status,h.assigned_at,h.submitted_at,h.reviewed_at,u.name,u.grade,
      (SELECT COUNT(*) FROM homework_submissions s WHERE s.homework_id=h.id) submissions_count,
      (SELECT COUNT(*) FROM homework_submissions s WHERE s.homework_id=h.id AND s.status='SUBMITTED') pending_submissions,
      (SELECT COUNT(*) FROM homework_task_links tl WHERE tl.homework_id=h.id) task_count,
      (SELECT COUNT(*) FROM homework_material_links ml WHERE ml.homework_id=h.id) material_count,
      (SELECT score_percent FROM homework_auto_results ar WHERE ar.homework_id=h.id AND ar.user_id=h.user_id ORDER BY attempt_number DESC LIMIT 1) auto_score,
      (SELECT student_status FROM external_homework_state es WHERE es.homework_id=h.id AND es.user_id=h.user_id) external_status,
      (SELECT last_opened_at FROM external_homework_state es WHERE es.homework_id=h.id AND es.user_id=h.user_id) external_opened_at
      FROM homework h JOIN users u ON u.id=h.user_id
      WHERE {' AND '.join(where)}
      ORDER BY CASE WHEN h.status IN ('SUBMITTED','UNDER_REVIEW','REVISION') THEN 0 WHEN h.deadline IS NOT NULL AND h.deadline<? AND h.status NOT IN ('COMPLETED','CANCELLED') THEN 1 ELSE 2 END,
               COALESCE(h.deadline,h.assigned_at) DESC LIMIT ?
    """,(*params,datetime.now().isoformat(timespec='seconds'),int(limit))).fetchall();conn.close();return [_rowdict(r) for r in rows]


def stats():
    conn=connect();now=datetime.now().isoformat(timespec='seconds')
    row=conn.execute("""
      SELECT
      SUM(CASE WHEN status='ASSIGNED' THEN 1 ELSE 0 END) assigned,
      SUM(CASE WHEN status IN ('SUBMITTED','UNDER_REVIEW') THEN 1 ELSE 0 END) submitted,
      SUM(CASE WHEN status='REVISION' THEN 1 ELSE 0 END) revision,
      SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) completed,
      SUM(CASE WHEN deadline IS NOT NULL AND deadline<? AND status NOT IN ('COMPLETED','CANCELLED') THEN 1 ELSE 0 END) overdue
      FROM homework
    """,(now,)).fetchone();conn.close();return {k:int(row[k] or 0) for k in row.keys()}


def detail(homework_id):
    conn=connect();h=conn.execute("SELECT h.*,u.name,u.grade FROM homework h JOIN users u ON u.id=h.user_id WHERE h.id=?",(int(homework_id),)).fetchone()
    if not h:conn.close();return None
    subs=conn.execute("SELECT * FROM homework_submissions WHERE homework_id=? ORDER BY attempt_number DESC,id DESC",(int(homework_id),)).fetchall()
    reviews=conn.execute("SELECT * FROM homework_reviews WHERE homework_id=? ORDER BY reviewed_at DESC,id DESC",(int(homework_id),)).fetchall()
    tasks=conn.execute("""SELECT t.id,t.title,t.statement,t.subject,t.section,t.topic,t.task_number,t.answer,t.solution,s.points,s.answer_type,s.tolerance FROM homework_task_links l JOIN task_bank t ON t.id=l.task_id LEFT JOIN homework_task_settings s ON s.homework_id=l.homework_id AND s.task_id=t.id WHERE l.homework_id=? ORDER BY l.sort_order,l.id""",(int(homework_id),)).fetchall()
    mats=conn.execute("""SELECT m.* FROM homework_material_links l JOIN materials m ON m.id=l.material_id WHERE l.homework_id=? ORDER BY l.id""",(int(homework_id),)).fetchall()
    auto=conn.execute("SELECT * FROM homework_auto_results WHERE homework_id=? ORDER BY attempt_number DESC LIMIT 1",(int(homework_id),)).fetchone()
    ext=conn.execute("""SELECT l.*,s.first_opened_at,s.last_opened_at,s.student_status,s.student_status_at FROM external_homework_links l LEFT JOIN external_homework_state s ON s.homework_id=l.homework_id AND s.user_id=? WHERE l.homework_id=?""",(int(h['user_id']),int(homework_id))).fetchone()
    conn.close();return {'homework':dict(h),'submissions':[dict(x) for x in subs],'reviews':[dict(x) for x in reviews],'tasks':[dict(x) for x in tasks],'materials':[dict(x) for x in mats],'auto_result':dict(auto) if auto else None,'external':dict(ext) if ext else None}
