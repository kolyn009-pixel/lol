from . import schema
import sqlite3
STATUSES={'NOT_STARTED':'⚪ Не проходили','LEARNING':'🔵 Изучаем','REVIEW':'🟡 Нужно повторить','MASTERED':'🟢 Освоено'}
DEFAULT_PHYSICS=['Механика','Молекулярная физика и термодинамика','Электродинамика','Колебания и волны','Оптика','Квантовая и ядерная физика']
DEFAULT_CHEMISTRY=['Основы химии','Строение вещества','Неорганическая химия','Растворы и реакции','Органическая химия','Расчётные задачи']

def seed(db_path=schema.DB_PATH):
 schema.initialize(db_path); conn=sqlite3.connect(db_path); c=conn.cursor()
 for subject,sections in [('Физика',DEFAULT_PHYSICS),('Химия',DEFAULT_CHEMISTRY)]:
  for i,section in enumerate(sections):
   c.execute('INSERT OR IGNORE INTO learning_topics(subject,study_goal,grade,section,topic,sort_order,formula_key) VALUES(?,?,?,?,?,?,?)',(subject,'',None,section,section,i,section.lower()))
 conn.commit();conn.close()

def set_progress(user_id,topic_id,status,mastery=0,note=None,db_path=schema.DB_PATH):
 now=__import__('datetime').datetime.now().isoformat(timespec='seconds'); conn=sqlite3.connect(db_path);c=conn.cursor();c.execute('''INSERT INTO student_topic_progress(user_id,topic_id,status,mastery,note,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,topic_id) DO UPDATE SET status=excluded.status,mastery=excluded.mastery,note=excluded.note,updated_at=excluded.updated_at''',(user_id,topic_id,status,max(0,min(100,int(mastery))),note,now));conn.commit();conn.close()

def summary(user_id,db_path=schema.DB_PATH):
 conn=sqlite3.connect(db_path);conn.row_factory=sqlite3.Row;c=conn.cursor();c.execute('''SELECT t.id AS topic_id,t.subject,t.section,t.topic,COALESCE(p.status,'NOT_STARTED') status,COALESCE(p.mastery,0) mastery FROM learning_topics t LEFT JOIN student_topic_progress p ON p.topic_id=t.id AND p.user_id=? ORDER BY t.subject,t.sort_order,t.topic''',(user_id,));rows=c.fetchall();conn.close();return rows
