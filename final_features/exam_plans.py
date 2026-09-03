from __future__ import annotations
from datetime import date,datetime
import database
from learning import curriculum, exam_results
from . import schema


def generate(user_id, program_id, exam_date, target_score=None, minutes_per_week=180):
    schema.initialize(); p=database.get_student_program(int(program_id)); d=datetime.fromisoformat(str(exam_date)).date() if 'T' in str(exam_date) else datetime.strptime(str(exam_date),'%Y-%m-%d').date(); weeks=max(1,(d-date.today()).days//7)
    topics=curriculum.summary(user_id); remaining=[r for r in topics if r['status']!='MASTERED' and (not p or r['subject'].upper().startswith(('ФИЗ' if p['subject']=='PHYSICS' else 'ХИМ')))]
    latest=exam_results.history(user_id); score=latest[-1]['test_score'] if latest else None
    needed=len(remaining); capacity=weeks*int(minutes_per_week); suggested=max(30,round(capacity/max(needed,1)))
    warning='⚠️ Темп плотный: стоит увеличить минуты в неделю.' if needed and suggested<75 else '✅ Темп выглядит реалистично.'
    summary=f"🎯 План до экзамена\n\nДо экзамена: {weeks} нед.\nТекущий балл: {score if score is not None else 'нет данных'}\nЦель: {target_score if target_score is not None else 'не задана'}\nТем не освоено: {needed}\nМинут в неделю: {minutes_per_week}\nОриентир на тему: {suggested} мин\n\n{warning}"
    c=database.connect(); now=datetime.now().isoformat(timespec='seconds')
    try:
        c.execute("UPDATE exam_prep_plans SET status='ARCHIVED' WHERE user_id=? AND program_id=? AND status='ACTIVE'",(int(user_id),int(program_id)))
        c.execute('INSERT INTO exam_prep_plans(user_id,program_id,exam_type,exam_date,target_score,minutes_per_week,status,generated_summary,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(int(user_id),int(program_id),p['study_goal'] if p else 'EGE',d.isoformat(),target_score,int(minutes_per_week),'ACTIVE',summary,now,now)); c.commit()
    finally:c.close()
    return summary
