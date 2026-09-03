import os, sqlite3
from datetime import datetime
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tutor.db')

def initialize(db_path=DB_PATH):
    conn=sqlite3.connect(db_path); c=conn.cursor()
    statements=[
    '''CREATE TABLE IF NOT EXISTS learning_topics(id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, study_goal TEXT NOT NULL DEFAULT '', grade INTEGER, section TEXT NOT NULL, topic TEXT NOT NULL, sort_order INTEGER DEFAULT 0, formula_key TEXT, UNIQUE(subject,study_goal,grade,section,topic))''',
    '''CREATE TABLE IF NOT EXISTS student_topic_progress(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,topic_id INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'NOT_STARTED',mastery INTEGER DEFAULT 0,note TEXT,updated_at TEXT NOT NULL,UNIQUE(user_id,topic_id))''',
    '''CREATE TABLE IF NOT EXISTS learning_diagnostics(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,mode TEXT NOT NULL DEFAULT 'QUICK',subject TEXT NOT NULL,study_goal TEXT,score REAL,target_score REAL,summary TEXT,created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS exam_results(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,subject TEXT NOT NULL,exam_type TEXT NOT NULL DEFAULT 'EGE',exam_date TEXT NOT NULL,primary_score REAL,test_score REAL,max_score REAL,notes TEXT,created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS student_goals(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,subject TEXT NOT NULL,study_goal TEXT,target_text TEXT,target_score REAL,target_date TEXT,status TEXT DEFAULT 'ACTIVE',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS lesson_plans(id INTEGER PRIMARY KEY AUTOINCREMENT,lesson_id INTEGER NOT NULL UNIQUE,user_id INTEGER NOT NULL,plan_text TEXT,status TEXT DEFAULT 'DRAFT',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS student_private_notes(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,lesson_id INTEGER,note TEXT NOT NULL,pinned INTEGER DEFAULT 0,created_by INTEGER,created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS learning_materials(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,subject TEXT NOT NULL,study_goal TEXT,grade INTEGER,section TEXT,topic TEXT,material_type TEXT DEFAULT 'LINK',telegram_file_id TEXT,url TEXT,description TEXT,active INTEGER DEFAULT 1,created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS student_materials(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,material_id INTEGER NOT NULL,assigned_at TEXT NOT NULL,UNIQUE(user_id,material_id))'''
    ]
    for s in statements:c.execute(s)
    for idx in ['CREATE INDEX IF NOT EXISTS idx_topic_progress_user ON student_topic_progress(user_id)','CREATE INDEX IF NOT EXISTS idx_exam_results_user_date ON exam_results(user_id,exam_date)','CREATE INDEX IF NOT EXISTS idx_private_notes_user ON student_private_notes(user_id,created_at)']: c.execute(idx)
    conn.commit(); conn.close()
