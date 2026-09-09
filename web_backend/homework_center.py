"""Teacher homework center: one feed for manual, interactive and external homework."""
from database import connect, now_iso
from web_backend.library import ensure_tables as ensure_library_tables
from web_backend.assessment import ensure_tables as ensure_assessment_tables, student_homework_payload
from web_backend.external_homework import ensure_tables as ensure_external_tables


def ensure_tables():
    ensure_library_tables(); ensure_assessment_tables(); ensure_external_tables()


def _rowdict(row): return dict(row) if row else None


def list_homework(status=None,user_id=None,mode=None,search=None,limit=200):
    ensure_tables();conn=connect();where=['1=1'];params=[]
    if status:
        st=str(status).upper()
        if st=='OVERDUE': where.append("h.deadline IS NOT NULL AND datetime(h.deadline)<datetime('now') AND h.status NOT IN ('COMPLETED','CANCELLED')")
        elif st=='NEEDS_REVIEW': where.append("EXISTS(SELECT 1 FROM homework_submissions s WHERE s.homework_id=h.id AND s.status='SUBMITTED')")
        else: where.append('h.status=?');params.append(st)
    if user_id is not None: where.append('h.user_id=?');params.append(int(user_id))
    if mode:
        m=str(mode).upper();mapping={'MANUAL':'MAIN','INTERACTIVE':'INTERACTIVE','EXTERNAL':'EXTERNAL'}
        where.append('h.homework_type=?');params.append(mapping.get(m,m))
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
      FROM homework h JOIN users u ON u.id=h.user_id WHERE {' AND '.join(where)}
      ORDER BY CASE WHEN h.status IN ('SUBMITTED','UNDER_REVIEW','REVISION') THEN 0 WHEN h.deadline IS NOT NULL AND datetime(h.deadline)<datetime('now') AND h.status NOT IN ('COMPLETED','CANCELLED') THEN 1 ELSE 2 END,
      datetime(COALESCE(h.deadline,h.assigned_at)) DESC,h.id DESC LIMIT ?
    """,(*params,int(limit))).fetchall();conn.close();return [_rowdict(r) for r in rows]


def stats():
    ensure_tables();conn=connect();row=conn.execute("""
      SELECT SUM(CASE WHEN status='ASSIGNED' THEN 1 ELSE 0 END) assigned,
      SUM(CASE WHEN status IN ('SUBMITTED','UNDER_REVIEW') THEN 1 ELSE 0 END) submitted,
      SUM(CASE WHEN status='REVISION' THEN 1 ELSE 0 END) revision,
      SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) completed,
      SUM(CASE WHEN deadline IS NOT NULL AND datetime(deadline)<datetime('now') AND status NOT IN ('COMPLETED','CANCELLED') THEN 1 ELSE 0 END) overdue FROM homework
    """).fetchone();conn.close();return {k:int(row[k] or 0) for k in row.keys()}


def detail(homework_id):
    ensure_tables();hid=int(homework_id);conn=connect();h=conn.execute("SELECT h.*,u.name,u.grade FROM homework h JOIN users u ON u.id=h.user_id WHERE h.id=?",(hid,)).fetchone()
    if not h:conn.close();return None
    subs=conn.execute("SELECT * FROM homework_submissions WHERE homework_id=? ORDER BY attempt_number DESC,id DESC",(hid,)).fetchall()
    reviews=conn.execute("SELECT * FROM homework_reviews WHERE homework_id=? ORDER BY datetime(reviewed_at) DESC,id DESC",(hid,)).fetchall()
    tasks=conn.execute("""SELECT t.id,t.title,t.statement,t.subject,t.section,t.topic,t.task_number,t.answer,t.solution,COALESCE(s.points,1) points,COALESCE(s.answer_type,'TEXT') answer_type,s.tolerance,COALESCE(s.required,1) required FROM homework_task_links l JOIN task_bank t ON t.id=l.task_id LEFT JOIN homework_task_settings s ON s.homework_id=l.homework_id AND s.task_id=t.id WHERE l.homework_id=? ORDER BY l.sort_order,l.id""",(hid,)).fetchall()
    mats=conn.execute("""SELECT m.* FROM homework_material_links l JOIN materials m ON m.id=l.material_id WHERE l.homework_id=? ORDER BY l.id""",(hid,)).fetchall()
    autos=conn.execute("SELECT * FROM homework_auto_results WHERE homework_id=? ORDER BY attempt_number DESC",(hid,)).fetchall()
    responses=conn.execute("""SELECT r.*,t.title,t.task_number,t.statement,t.answer,t.solution,COALESCE(s.points,1) max_points,f.teacher_comment,f.override_correct,f.override_points FROM homework_task_responses r JOIN task_bank t ON t.id=r.task_id LEFT JOIN homework_task_settings s ON s.homework_id=r.homework_id AND s.task_id=r.task_id LEFT JOIN homework_task_feedback f ON f.homework_id=r.homework_id AND f.task_id=r.task_id AND f.user_id=r.user_id AND f.attempt_number=r.attempt_number WHERE r.homework_id=? ORDER BY r.attempt_number DESC,r.id""",(hid,)).fetchall()
    ext=conn.execute("""SELECT l.*,s.first_opened_at,s.last_opened_at,s.student_status,s.student_status_at FROM external_homework_links l LEFT JOIN external_homework_state s ON s.homework_id=l.homework_id AND s.user_id=? WHERE l.homework_id=?""",(int(h['user_id']),hid)).fetchone()
    conn.close()
    preview=student_homework_payload(hid,int(h['user_id']))
    if preview:
        preview=dict(preview);preview['homework']={k:v for k,v in dict(preview['homework']).items() if k not in {'source_reference'}}
    by_attempt={}
    for r in responses:
        by_attempt.setdefault(int(r['attempt_number'] or 1),[]).append(dict(r))
    return {'homework':dict(h),'submissions':[dict(x) for x in subs],'reviews':[dict(x) for x in reviews],'tasks':[dict(x) for x in tasks],'materials':[dict(x) for x in mats],'auto_results':[dict(x) for x in autos],'auto_result':dict(autos[0]) if autos else None,'responses_by_attempt':by_attempt,'external':dict(ext) if ext else None,'student_preview':preview}


def update_homework(homework_id,title=None,description=None,deadline=None,status=None):
    ensure_tables();hid=int(homework_id);allowed_status={'ASSIGNED','SUBMITTED','UNDER_REVIEW','REVISION','REVIEWED','COMPLETED','CANCELLED'}
    conn=connect();row=conn.execute('SELECT id FROM homework WHERE id=?',(hid,)).fetchone()
    if not row:conn.close();return {'status':'not_found'}
    fields=[];params=[]
    if title is not None:
        value=str(title).strip()[:160]
        if not value:conn.close();return {'status':'title_required'}
        fields.append('title=?');params.append(value)
    if description is not None:fields.append('description=?');params.append(str(description).strip())
    if deadline is not None:fields.append('deadline=?');params.append(str(deadline).strip() or None)
    if status is not None:
        st=str(status).upper()
        if st not in allowed_status:conn.close();return {'status':'invalid_status'}
        fields.append('status=?');params.append(st)
    if not fields:conn.close();return {'status':'ok','homework_id':hid,'changed':0}
    fields.append('updated_at=?');params.append(now_iso());params.append(hid)
    conn.execute(f"UPDATE homework SET {','.join(fields)} WHERE id=?",params);conn.commit();conn.close();return {'status':'ok','homework_id':hid,'changed':1}
