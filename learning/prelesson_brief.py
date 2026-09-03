from . import schema
from .student_progress import get_goal
from .homework_stats import stats as hw_stats
import sqlite3

def build(user_id,lesson_id=None,db_path=schema.DB_PATH):
 conn=sqlite3.connect(db_path);conn.row_factory=sqlite3.Row;c=conn.cursor();c.execute('SELECT name,grade,study_goal,main_subject FROM users WHERE id=?',(user_id,));u=c.fetchone();c.execute('SELECT note FROM student_private_notes WHERE user_id=? ORDER BY pinned DESC,id DESC LIMIT 3',(user_id,));notes=[x['note'] for x in c.fetchall()];c.execute("SELECT subject,section,topic,status,mastery FROM learning_topics t JOIN student_topic_progress p ON p.topic_id=t.id WHERE p.user_id=? AND p.status IN ('REVIEW','LEARNING') ORDER BY p.updated_at DESC LIMIT 5",(user_id,));weak=c.fetchall();conn.close();g=get_goal(user_id,db_path);h=hw_stats(user_id,db_path)
 if not u:return 'Ученик не найден.'
 lines=[f"🧠 <b>Сводка: {u['name']}</b>",f"{u['grade']} класс • {u['main_subject']} • {u['study_goal']}"]
 if g: lines.append(f"🎯 Цель: {g['target_text']}" + (f" ({g['target_score']:.0f})" if g['target_score'] is not None else ''))
 lines.append(f"📝 ДЗ: выполнено {h.get('done') or 0}/{h.get('total') or 0}, просрочено {h.get('overdue') or 0}")
 if weak: lines.append('⚠️ Повторить: '+', '.join(x['topic'] for x in weak))
 if notes: lines.append('📌 Заметки: '+'; '.join(notes))
 return '\n'.join(lines)
