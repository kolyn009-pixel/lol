"""Shared formula handbook for student and teacher web apps."""
from __future__ import annotations
import json
from database import connect, now_iso

EDITABLE={
    'subject','section','topic','title','formula_latex','formula_plain','description',
    'variables_json','conditions','units','derivation','example','exam_note',
    'grade_min','grade_max','study_goal','tags_json','sort_order','active'
}

def ensure_tables():
    conn=connect();conn.executescript("""
    CREATE TABLE IF NOT EXISTS formula_book(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subject TEXT NOT NULL,
      section TEXT,
      topic TEXT,
      title TEXT NOT NULL,
      formula_latex TEXT NOT NULL,
      formula_plain TEXT,
      description TEXT,
      variables_json TEXT NOT NULL DEFAULT '[]',
      conditions TEXT,
      units TEXT,
      derivation TEXT,
      example TEXT,
      exam_note TEXT,
      grade_min INTEGER,
      grade_max INTEGER,
      study_goal TEXT,
      tags_json TEXT NOT NULL DEFAULT '[]',
      sort_order INTEGER NOT NULL DEFAULT 100,
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS formula_favorites(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      formula_id INTEGER NOT NULL,
      user_id INTEGER NOT NULL,
      created_at TEXT NOT NULL,
      UNIQUE(formula_id,user_id),
      FOREIGN KEY(formula_id) REFERENCES formula_book(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_formula_filter ON formula_book(subject,section,topic,active,sort_order);
    CREATE INDEX IF NOT EXISTS idx_formula_favorites_user ON formula_favorites(user_id,formula_id);
    """);conn.commit();conn.close()

def _json(value,default=None):
    if value is None:return json.dumps(default if default is not None else [],ensure_ascii=False)
    if isinstance(value,str):
        try:json.loads(value);return value
        except Exception:return json.dumps([value] if value else [],ensure_ascii=False)
    return json.dumps(value,ensure_ascii=False)

def _normalize(fields,creating=False):
    out={}
    for key,val in (fields or {}).items():
        if key not in EDITABLE:continue
        if key in {'variables_json','tags_json'}:val=_json(val,[])
        elif key in {'grade_min','grade_max','sort_order','active'} and val not in (None,''):
            val=int(val)
        elif key not in {'grade_min','grade_max'}:val=str(val or '').strip() if val is not None else None
        out[key]=val
    if creating:
        for key in ('subject','title','formula_latex'):
            if not str(out.get(key) or '').strip():raise ValueError(key+'_required')
    for key in ('grade_min','grade_max'):
        if out.get(key) is not None and not 1<=int(out[key])<=14:raise ValueError('invalid_grade')
    if out.get('grade_min') is not None and out.get('grade_max') is not None and int(out['grade_min'])>int(out['grade_max']):raise ValueError('invalid_grade_range')
    if 'sort_order' in out and int(out['sort_order'])<0:raise ValueError('invalid_sort_order')
    if 'active' in out:out['active']=1 if int(out['active']) else 0
    if 'subject' in out:out['subject']=str(out['subject'] or '').upper()
    if 'study_goal' in out and out['study_goal']:out['study_goal']=str(out['study_goal']).upper()
    return out

def create_formula(fields):
    ensure_tables();data=_normalize(fields,True);now=now_iso();cols=list(data);vals=[data[k] for k in cols];conn=connect();cur=conn.execute(f"INSERT INTO formula_book({','.join(cols)},created_at,updated_at) VALUES({','.join('?' for _ in cols)},?,?)",(*vals,now,now));conn.commit();fid=int(cur.lastrowid);conn.close();return {'status':'ok','id':fid}

def update_formula(formula_id,fields):
    ensure_tables();data=_normalize(fields,False)
    if not data:return {'status':'ok','changed':0,'id':int(formula_id)}
    conn=connect();row=conn.execute('SELECT id FROM formula_book WHERE id=?',(int(formula_id),)).fetchone()
    if not row:conn.close();return {'status':'not_found'}
    pairs=[k+'=?' for k in data];vals=[data[k] for k in data];vals.extend([now_iso(),int(formula_id)]);cur=conn.execute(f"UPDATE formula_book SET {','.join(pairs)},updated_at=? WHERE id=?",vals);conn.commit();conn.close();return {'status':'ok','changed':int(cur.rowcount),'id':int(formula_id)}

def list_formulas(user_id=None,subject=None,section=None,topic=None,search=None,favorites_only=False,limit=300):
    ensure_tables();where=['f.active=1'];params=[];join=''
    if user_id is not None:join=' LEFT JOIN formula_favorites fav ON fav.formula_id=f.id AND fav.user_id=? ';params.append(int(user_id))
    if subject:where.append('f.subject=?');params.append(str(subject).upper())
    if section:where.append('f.section=?');params.append(str(section))
    if topic:where.append('f.topic=?');params.append(str(topic))
    if search:
        q='%'+str(search).strip().lower()+'%';where.append("(LOWER(f.title) LIKE ? OR LOWER(COALESCE(f.description,'')) LIKE ? OR LOWER(COALESCE(f.formula_plain,'')) LIKE ? OR LOWER(COALESCE(f.tags_json,'')) LIKE ?)");params += [q,q,q,q]
    if favorites_only and user_id is not None:where.append('fav.id IS NOT NULL')
    favcol='CASE WHEN fav.id IS NULL THEN 0 ELSE 1 END favorite' if user_id is not None else '0 favorite'
    conn=connect();rows=conn.execute(f"SELECT f.*,{favcol} FROM formula_book f {join} WHERE {' AND '.join(where)} ORDER BY f.subject,f.sort_order,f.section,f.topic,f.id LIMIT ?",(*params,max(1,min(int(limit),500)))).fetchall();conn.close();return [dict(r) for r in rows]

def formula_detail(formula_id,user_id=None):
    ensure_tables();conn=connect();params=[int(formula_id)];join='';fav='0 favorite'
    if user_id is not None:join=' LEFT JOIN formula_favorites x ON x.formula_id=f.id AND x.user_id=? ';params=[int(user_id),int(formula_id)];fav='CASE WHEN x.id IS NULL THEN 0 ELSE 1 END favorite'
    row=conn.execute(f'SELECT f.*,{fav} FROM formula_book f {join} WHERE f.id=? AND f.active=1',params).fetchone();conn.close();return dict(row) if row else None

def set_favorite(formula_id,user_id,value=True):
    ensure_tables();conn=connect();exists=conn.execute('SELECT id FROM formula_book WHERE id=? AND active=1',(int(formula_id),)).fetchone()
    if not exists:conn.close();return {'status':'not_found'}
    if value:conn.execute('INSERT OR IGNORE INTO formula_favorites(formula_id,user_id,created_at) VALUES(?,?,?)',(int(formula_id),int(user_id),now_iso()))
    else:conn.execute('DELETE FROM formula_favorites WHERE formula_id=? AND user_id=?',(int(formula_id),int(user_id)))
    conn.commit();conn.close();return {'status':'ok','favorite':bool(value)}

def facets():
    ensure_tables();conn=connect();subjects=[r[0] for r in conn.execute("SELECT DISTINCT subject FROM formula_book WHERE active=1 ORDER BY subject")];sections=[dict(r) for r in conn.execute("SELECT subject,section,COUNT(*) count FROM formula_book WHERE active=1 AND section IS NOT NULL GROUP BY subject,section ORDER BY subject,section")];topics=[dict(r) for r in conn.execute("SELECT subject,section,topic,COUNT(*) count FROM formula_book WHERE active=1 AND topic IS NOT NULL GROUP BY subject,section,topic ORDER BY subject,section,topic")];conn.close();return {'subjects':subjects,'sections':sections,'topics':topics}
