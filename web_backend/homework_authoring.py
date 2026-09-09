"""Canonical homework authoring for manual, interactive and external assignments."""
from database import connect, get_user, create_homework, now_iso
from web_backend.library import link_to_homework, link_task_to_homework
from web_backend.assessment import configure_task
from web_backend.external_homework import attach_external_link, detect_provider
from web_backend.homework_notifications import enqueue

MODES={"MANUAL","INTERACTIVE","EXTERNAL"}


def _notify_assigned(user_id,homework_id,title,deadline,mode):
    mode_label={"MANUAL":"обычное ДЗ","INTERACTIVE":"интерактивное ДЗ","EXTERNAL":"внешний вариант"}.get(str(mode).upper(),"домашнее задание")
    text=f"📚 Новое домашнее задание\n\n«{title}»\nТип: {mode_label}"
    if deadline:text+=f"\n⏰ Срок: {deadline}"
    text+="\n\nОткрой Аделию, чтобы посмотреть задание и материалы 💜"
    enqueue(f"homework-assigned:{int(homework_id)}:{int(user_id)}",'STUDENT','HOMEWORK_ASSIGNED',text,int(user_id),f"/app/?homework={int(homework_id)}",'Открыть ДЗ',{'homework_id':int(homework_id),'mode':str(mode).upper()})


def create_assignment(user_id,title,description,deadline=None,lesson_id=None,mode="MANUAL",task_ids=None,material_ids=None,external_url=None,external_title=None,task_settings=None):
    user=get_user(int(user_id))
    if not user:return {"status":"student_not_found"}
    mode=str(mode or "MANUAL").upper()
    if mode not in MODES:return {"status":"invalid_mode"}
    title=str(title or "Домашнее задание").strip()[:160]
    description=str(description or '').strip()
    task_ids=[int(x) for x in (task_ids or [])]
    material_ids=[int(x) for x in (material_ids or [])]
    if mode=="MANUAL" and not description and not material_ids:return {"status":"description_required"}
    if mode=="INTERACTIVE" and not task_ids:return {"status":"tasks_required"}
    if mode=="EXTERNAL" and not str(external_url or '').strip():return {"status":"external_url_required"}
    clean_deadline=str(deadline).strip() or None if deadline is not None else None
    hid=create_homework(int(user_id),user['study_goal'] or 'GENERAL',user['main_subject'] or 'PHYSICS',description or title,title=title,lesson_id=int(lesson_id) if lesson_id else None,deadline=clean_deadline)
    conn=connect();source_type={'MANUAL':'CUSTOM','INTERACTIVE':'TASK_BANK','EXTERNAL':'EXTERNAL_LINK'}[mode];homework_type={'MANUAL':'MAIN','INTERACTIVE':'INTERACTIVE','EXTERNAL':'EXTERNAL'}[mode]
    source_url=str(external_url).strip() if mode=='EXTERNAL' else None
    source_reference=detect_provider(source_url) if source_url else None
    conn.execute("UPDATE homework SET homework_type=?,source_type=?,source_reference=?,source_url=?,updated_at=? WHERE id=?",(homework_type,source_type,source_reference,source_url,now_iso(),int(hid)));conn.commit();conn.close()
    for mid in material_ids:link_to_homework(mid,int(hid))
    settings={int(x.get('task_id')):x for x in (task_settings or []) if x.get('task_id') is not None}
    for tid in task_ids:
        link_task_to_homework(tid,int(hid));cfg=settings.get(tid,{})
        configure_task(int(hid),tid,points=cfg.get('points',1),answer_type=cfg.get('answer_type','TEXT'),tolerance=cfg.get('tolerance'),required=cfg.get('required',True))
    provider=None
    if mode=='EXTERNAL':provider=attach_external_link(int(hid),source_url,external_title or title).get('provider')
    _notify_assigned(int(user_id),int(hid),title,clean_deadline,mode)
    return {"status":"ok","homework_id":int(hid),"mode":mode,"tasks":len(task_ids),"materials":len(material_ids),"provider":provider}
