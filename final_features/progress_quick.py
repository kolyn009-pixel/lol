from __future__ import annotations
from datetime import datetime
import database
from learning import curriculum
from . import schema

LEVEL_MAP={'STARTED':('LEARNING',25),'NEEDS_WORK':('REVIEW',35),'GOOD':('REVIEW',70),'MASTERED':('MASTERED',100)}

def topics_for_student(user_id, lesson_id=None):
    schema.initialize(); c=database.connect()
    try:
        u=c.execute('SELECT grade FROM users WHERE id=?',(int(user_id),)).fetchone(); grade=int(u['grade']) if u and u['grade'] is not None else None
        goal=subject=None
        if lesson_id:
            l=c.execute('SELECT study_goal,subject FROM lessons WHERE id=?',(int(lesson_id),)).fetchone()
            if l: goal=l['study_goal']; subject=l['subject']
        if not goal:
            p=c.execute("SELECT study_goal,subject FROM student_programs WHERE user_id=? AND active=1 ORDER BY is_primary DESC,id LIMIT 1",(int(user_id),)).fetchone()
            if p:goal,subject=p['study_goal'],p['subject']
        subj_ru={'PHYSICS':'Физика','CHEMISTRY':'Химия'}.get(str(subject).upper(),subject)
        params=[int(user_id)]; wh=[]
        if subj_ru: wh.append('t.subject=?');params.append(subj_ru)
        if str(goal).upper() in ('EGE','OGE'):
            wh.append("t.study_goal=?");params.append(str(goal).upper())
        else:
            wh.append("t.study_goal='' ")
            if grade:wh.append('t.grade=?');params.append(grade)
        sql='''SELECT t.id topic_id,t.subject,t.study_goal,t.grade,t.section,t.topic,t.sort_order,
                      COALESCE(p.status,'NOT_STARTED') status,COALESCE(p.mastery,0) mastery,p.note
               FROM learning_topics t LEFT JOIN student_topic_progress p ON p.topic_id=t.id AND p.user_id=?'''
        if wh:sql+=' WHERE '+' AND '.join(wh)
        sql+=' ORDER BY t.grade,t.sort_order,t.section,t.topic'
        rows=c.execute(sql,params).fetchall()
        if not rows and grade:
            rows=c.execute('''SELECT t.id topic_id,t.subject,t.study_goal,t.grade,t.section,t.topic,t.sort_order,COALESCE(p.status,'NOT_STARTED') status,COALESCE(p.mastery,0) mastery,p.note FROM learning_topics t LEFT JOIN student_topic_progress p ON p.topic_id=t.id AND p.user_id=? WHERE t.grade=? ORDER BY t.subject,t.sort_order''',(int(user_id),grade)).fetchall()
        return rows
    finally:c.close()

def save_review(lesson_id,user_id,marks,rating=None,summary=None,homework_note=None,actor=None):
    schema.initialize(); now=datetime.now().isoformat(timespec='seconds'); c=database.connect()
    try:
        c.execute('''INSERT INTO post_lesson_reviews(lesson_id,user_id,rating,summary,homework_note,created_by,created_at,updated_at)
                     VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(lesson_id) DO UPDATE SET rating=excluded.rating,summary=excluded.summary,homework_note=excluded.homework_note,updated_at=excluded.updated_at''',(int(lesson_id),int(user_id),rating,summary,homework_note,actor,now,now))
        review=c.execute('SELECT id FROM post_lesson_reviews WHERE lesson_id=?',(int(lesson_id),)).fetchone()['id']
        for topic_id,level,comment in marks:
            status,mastery=LEVEL_MAP.get(level,('LEARNING',50))
            c.execute('INSERT OR REPLACE INTO post_lesson_topic_marks(review_id,topic_id,level,comment,created_at) VALUES(?,?,?,?,?)',(review,int(topic_id),level,comment,now))
            c.execute('''INSERT INTO student_topic_progress(user_id,topic_id,status,mastery,note,updated_at) VALUES(?,?,?,?,?,?)
                         ON CONFLICT(user_id,topic_id) DO UPDATE SET status=excluded.status,mastery=excluded.mastery,note=excluded.note,updated_at=excluded.updated_at''',(int(user_id),int(topic_id),status,mastery,comment,now))
        c.execute('UPDATE lessons SET post_lesson_reviewed=1 WHERE id=?',(int(lesson_id),)); c.commit(); return review
    finally:c.close()
