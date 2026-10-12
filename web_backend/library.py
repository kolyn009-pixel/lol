"""Shared materials library and task bank for WEB, Telegram and VK."""
import json
from database import connect, now_iso


def ensure_tables():
    conn=connect();conn.executescript("""
    CREATE TABLE IF NOT EXISTS materials(
      id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,description TEXT,subject TEXT,
      grade_min INTEGER,grade_max INTEGER,material_type TEXT NOT NULL DEFAULT 'FILE',file_path TEXT,
      external_url TEXT,original_filename TEXT,mime_type TEXT,size_bytes INTEGER,
      tags_json TEXT NOT NULL DEFAULT '[]',active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS material_access(
      id INTEGER PRIMARY KEY AUTOINCREMENT,material_id INTEGER NOT NULL,user_id INTEGER,
      access_scope TEXT NOT NULL DEFAULT 'STUDENT',created_at TEXT NOT NULL,
      UNIQUE(material_id,user_id,access_scope),FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS homework_material_links(
      id INTEGER PRIMARY KEY AUTOINCREMENT,homework_id INTEGER NOT NULL,material_id INTEGER NOT NULL,
      note TEXT,created_at TEXT NOT NULL,UNIQUE(homework_id,material_id),
      FOREIGN KEY(homework_id) REFERENCES homework(id) ON DELETE CASCADE,
      FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS material_collections(
      id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,description TEXT,subject TEXT,grade INTEGER,
      collection_type TEXT NOT NULL DEFAULT 'BOOK',active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS collection_materials(
      id INTEGER PRIMARY KEY AUTOINCREMENT,collection_id INTEGER NOT NULL,material_id INTEGER NOT NULL,sort_order INTEGER DEFAULT 100,
      UNIQUE(collection_id,material_id),FOREIGN KEY(collection_id) REFERENCES material_collections(id) ON DELETE CASCADE,
      FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS task_bank(
      id INTEGER PRIMARY KEY AUTOINCREMENT,collection_id INTEGER,subject TEXT NOT NULL,grade INTEGER,study_goal TEXT,
      section TEXT,topic TEXT,source_label TEXT,task_number TEXT,title TEXT,statement TEXT NOT NULL,answer TEXT,solution TEXT,
      difficulty INTEGER DEFAULT 2,tags_json TEXT NOT NULL DEFAULT '[]',active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT,
      FOREIGN KEY(collection_id) REFERENCES material_collections(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS homework_task_links(
      id INTEGER PRIMARY KEY AUTOINCREMENT,homework_id INTEGER NOT NULL,task_id INTEGER NOT NULL,sort_order INTEGER DEFAULT 100,
      UNIQUE(homework_id,task_id),FOREIGN KEY(homework_id) REFERENCES homework(id) ON DELETE CASCADE,
      FOREIGN KEY(task_id) REFERENCES task_bank(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_materials_subject_grade ON materials(subject,grade_min,grade_max,active);
    CREATE INDEX IF NOT EXISTS idx_material_access_user ON material_access(user_id,access_scope);
    CREATE INDEX IF NOT EXISTS idx_task_bank_filter ON task_bank(subject,grade,study_goal,topic,active);
    """);conn.commit();conn.close()


def create_material(title,description="",subject=None,grade_min=None,grade_max=None,material_type="FILE",file_path=None,external_url=None,original_filename=None,mime_type=None,size_bytes=None,tags=None):
    ensure_tables();conn=connect();now=now_iso();cur=conn.execute("""INSERT INTO materials(title,description,subject,grade_min,grade_max,material_type,file_path,external_url,original_filename,mime_type,size_bytes,tags_json,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",(str(title).strip(),str(description or '').strip(),subject,grade_min,grade_max,str(material_type or 'FILE').upper(),file_path,external_url,original_filename,mime_type,int(size_bytes) if size_bytes is not None else None,json.dumps(tags or [],ensure_ascii=False),now,now));conn.commit();mid=cur.lastrowid;conn.close();return int(mid)


def create_collection(title,description='',subject=None,grade=None,collection_type='BOOK'):
    ensure_tables();conn=connect();now=now_iso();cur=conn.execute("INSERT INTO material_collections(title,description,subject,grade,collection_type,active,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?)",(str(title).strip(),str(description or '').strip(),subject,int(grade) if grade else None,str(collection_type or 'BOOK').upper(),now,now));conn.commit();cid=cur.lastrowid;conn.close();return int(cid)


def add_material_to_collection(collection_id,material_id,sort_order=100):
    ensure_tables();conn=connect();conn.execute("INSERT OR REPLACE INTO collection_materials(collection_id,material_id,sort_order) VALUES(?,?,?)",(int(collection_id),int(material_id),int(sort_order)));conn.commit();conn.close()


def grant_student(material_id,user_id):
    ensure_tables();conn=connect();conn.execute("INSERT OR IGNORE INTO material_access(material_id,user_id,access_scope,created_at) VALUES(?,?, 'STUDENT', ?)",(int(material_id),int(user_id),now_iso()));conn.commit();conn.close()


def link_to_homework(material_id,homework_id,note=None):
    ensure_tables();conn=connect();conn.execute("INSERT OR IGNORE INTO homework_material_links(homework_id,material_id,note,created_at) VALUES(?,?,?,?)",(int(homework_id),int(material_id),str(note or '').strip() or None,now_iso()));conn.commit();conn.close()


def add_task(subject,statement,grade=None,study_goal=None,section=None,topic=None,collection_id=None,source_label=None,task_number=None,title=None,answer=None,solution=None,difficulty=2,tags=None):
    ensure_tables();conn=connect();now=now_iso();cur=conn.execute("""INSERT INTO task_bank(collection_id,subject,grade,study_goal,section,topic,source_label,task_number,title,statement,answer,solution,difficulty,tags_json,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",(int(collection_id) if collection_id else None,str(subject).upper(),int(grade) if grade else None,study_goal,section,topic,source_label,task_number,title,str(statement).strip(),answer,solution,int(difficulty or 2),json.dumps(tags or [],ensure_ascii=False),now,now));conn.commit();tid=cur.lastrowid;conn.close();return int(tid)


def link_task_to_homework(task_id,homework_id,sort_order=100):
    ensure_tables();conn=connect();conn.execute("INSERT OR REPLACE INTO homework_task_links(homework_id,task_id,sort_order) VALUES(?,?,?)",(int(homework_id),int(task_id),int(sort_order)));conn.commit();conn.close()


def list_materials(user_id=None,subject=None,search=None,limit=100):
    ensure_tables();conn=connect();conn.create_function("CASEFOLD",1,lambda v:str(v or "").casefold());where=["m.active=1"];params=[];join=""
    if user_id is not None:join=" JOIN material_access a ON a.material_id=m.id ";where.append("a.user_id=?");params.append(int(user_id))
    if subject:where.append("m.subject=?");params.append(str(subject).upper())
    if search:
      where.append("(CASEFOLD(m.title) LIKE ? OR CASEFOLD(COALESCE(m.description,'')) LIKE ? OR CASEFOLD(m.tags_json) LIKE ?)");q='%'+str(search).casefold()+'%';params += [q,q,q]
    rows=conn.execute(f"SELECT DISTINCT m.* FROM materials m {join} WHERE {' AND '.join(where)} ORDER BY m.updated_at DESC,m.id DESC LIMIT ?",(*params,int(limit))).fetchall();conn.close();return [dict(r) for r in rows]


def list_collections(subject=None,limit=100):
    ensure_tables();conn=connect();sql="SELECT * FROM material_collections WHERE active=1";params=[]
    if subject:sql+=" AND subject=?";params.append(str(subject).upper())
    sql+=" ORDER BY updated_at DESC,id DESC LIMIT ?";params.append(int(limit));rows=conn.execute(sql,params).fetchall();conn.close();return [dict(r) for r in rows]


def list_tasks(subject=None,grade=None,topic=None,search=None,collection_id=None,limit=100):
    ensure_tables();conn=connect();where=["active=1"];params=[]
    if subject:where.append("subject=?");params.append(str(subject).upper())
    if grade:where.append("grade=?");params.append(int(grade))
    if topic:where.append("topic=?");params.append(str(topic))
    if collection_id:where.append("collection_id=?");params.append(int(collection_id))
    if search:
      where.append("(LOWER(statement) LIKE ? OR LOWER(COALESCE(title,'')) LIKE ? OR LOWER(COALESCE(topic,'')) LIKE ?)");q='%'+str(search).casefold()+'%';params += [q,q,q]
    rows=conn.execute(f"SELECT * FROM task_bank WHERE {' AND '.join(where)} ORDER BY difficulty,topic,id LIMIT ?",(*params,int(limit))).fetchall();conn.close();return [dict(r) for r in rows]

