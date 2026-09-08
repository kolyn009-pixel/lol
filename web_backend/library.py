"""Shared materials library for web, Telegram and VK.

Files are stored once on disk; database rows describe access, subject, grade,
tags and source. Bots and the website can reference the same material id.
"""

import json
from pathlib import Path
from database import connect, now_iso

STORAGE_ROOT = Path("/opt/tutorbot/storage/library")


def ensure_tables():
    conn = connect()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS materials (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      subject TEXT,
      grade_min INTEGER,
      grade_max INTEGER,
      material_type TEXT NOT NULL DEFAULT 'FILE',
      file_path TEXT,
      external_url TEXT,
      original_filename TEXT,
      mime_type TEXT,
      size_bytes INTEGER,
      tags_json TEXT NOT NULL DEFAULT '[]',
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS material_access (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      material_id INTEGER NOT NULL,
      user_id INTEGER,
      access_scope TEXT NOT NULL DEFAULT 'STUDENT',
      created_at TEXT NOT NULL,
      UNIQUE(material_id,user_id,access_scope),
      FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS homework_material_links (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      homework_id INTEGER NOT NULL,
      material_id INTEGER NOT NULL,
      note TEXT,
      created_at TEXT NOT NULL,
      UNIQUE(homework_id,material_id),
      FOREIGN KEY(homework_id) REFERENCES homework(id) ON DELETE CASCADE,
      FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_materials_subject_grade ON materials(subject,grade_min,grade_max,active);
    CREATE INDEX IF NOT EXISTS idx_material_access_user ON material_access(user_id,access_scope);
    """)
    conn.commit(); conn.close()


def create_material(title, description="", subject=None, grade_min=None, grade_max=None,
                    material_type="FILE", file_path=None, external_url=None,
                    original_filename=None, mime_type=None, size_bytes=None, tags=None):
    ensure_tables()
    conn=connect(); now=now_iso()
    cur=conn.execute("""
      INSERT INTO materials(title,description,subject,grade_min,grade_max,material_type,file_path,
      external_url,original_filename,mime_type,size_bytes,tags_json,active,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)
    """,(str(title).strip(),str(description or '').strip(),subject,grade_min,grade_max,
          str(material_type or 'FILE').upper(),file_path,external_url,original_filename,mime_type,
          int(size_bytes) if size_bytes is not None else None,json.dumps(tags or [],ensure_ascii=False),now,now))
    conn.commit(); mid=cur.lastrowid; conn.close(); return int(mid)


def grant_student(material_id,user_id):
    ensure_tables(); conn=connect()
    conn.execute("INSERT OR IGNORE INTO material_access(material_id,user_id,access_scope,created_at) VALUES(?,?, 'STUDENT', ?)",(int(material_id),int(user_id),now_iso()))
    conn.commit(); conn.close()


def link_to_homework(material_id,homework_id,note=None):
    ensure_tables(); conn=connect()
    conn.execute("INSERT OR IGNORE INTO homework_material_links(homework_id,material_id,note,created_at) VALUES(?,?,?,?)",(int(homework_id),int(material_id),str(note or '').strip() or None,now_iso()))
    conn.commit(); conn.close()


def list_materials(user_id=None, subject=None, search=None, limit=100):
    ensure_tables(); conn=connect(); where=["m.active=1"]; params=[]
    join=""
    if user_id is not None:
        join=" JOIN material_access a ON a.material_id=m.id "
        where.append("a.user_id=?"); params.append(int(user_id))
    if subject:
        where.append("m.subject=?"); params.append(str(subject).upper())
    if search:
        where.append("(LOWER(m.title) LIKE ? OR LOWER(COALESCE(m.description,'')) LIKE ? OR LOWER(m.tags_json) LIKE ?)")
        q='%'+str(search).lower()+'%'; params += [q,q,q]
    rows=conn.execute(f"SELECT DISTINCT m.* FROM materials m {join} WHERE {' AND '.join(where)} ORDER BY m.updated_at DESC,m.id DESC LIMIT ?",(*params,int(limit))).fetchall()
    conn.close(); return [dict(r) for r in rows]
