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
        if out.get(key) is not None and not 1<=int(out[key])<=11:raise ValueError('invalid_grade')
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

STARTER_FORMULAS=[
 {'subject':'PHYSICS','section':'Механика','topic':'Кинематика','title':'Равномерное движение','formula_latex':r's = vt','formula_plain':'s = v*t','description':'Путь при постоянной скорости.','variables_json':['s — путь, м','v — скорость, м/с','t — время, с'],'grade_min':7,'grade_max':11,'tags_json':['механика','кинематика'],'sort_order':10},
 {'subject':'PHYSICS','section':'Механика','topic':'Динамика','title':'Второй закон Ньютона','formula_latex':r'\vec F = m\vec a','formula_plain':'F = m*a','description':'Равнодействующая сил сообщает телу ускорение.','variables_json':['F — сила, Н','m — масса, кг','a — ускорение, м/с²'],'grade_min':7,'grade_max':11,'study_goal':'EGE','tags_json':['механика','динамика'],'sort_order':20},
 {'subject':'PHYSICS','section':'Механика','topic':'Энергия','title':'Кинетическая энергия','formula_latex':r'E_k = \frac{mv^2}{2}','formula_plain':'Ek = m*v^2/2','description':'Энергия движущегося тела.','variables_json':['Ek — энергия, Дж','m — масса, кг','v — скорость, м/с'],'grade_min':7,'grade_max':11,'tags_json':['энергия'],'sort_order':30},
 {'subject':'PHYSICS','section':'Электродинамика','topic':'Постоянный ток','title':'Закон Ома','formula_latex':r'I = \frac{U}{R}','formula_plain':'I = U/R','description':'Связь силы тока, напряжения и сопротивления участка цепи.','variables_json':['I — сила тока, А','U — напряжение, В','R — сопротивление, Ом'],'grade_min':8,'grade_max':11,'study_goal':'OGE','tags_json':['электричество','закон Ома'],'sort_order':40},
 {'subject':'PHYSICS','section':'Молекулярная физика','topic':'Количество теплоты','title':'Нагревание и охлаждение','formula_latex':r'Q = cm\Delta T','formula_plain':'Q = c*m*deltaT','description':'Количество теплоты при изменении температуры без фазового перехода.','variables_json':['Q — количество теплоты, Дж','c — удельная теплоёмкость','m — масса, кг','ΔT — изменение температуры'],'grade_min':8,'grade_max':11,'tags_json':['теплота'],'sort_order':50},
 {'subject':'CHEMISTRY','section':'Расчёты','topic':'Количество вещества','title':'Количество вещества через массу','formula_latex':r'n = \frac{m}{M}','formula_plain':'n = m/M','description':'Расчёт количества вещества по массе и молярной массе.','variables_json':['n — количество вещества, моль','m — масса, г','M — молярная масса, г/моль'],'grade_min':8,'grade_max':11,'study_goal':'OGE','tags_json':['моль','расчёты'],'sort_order':10},
 {'subject':'CHEMISTRY','section':'Растворы','topic':'Массовая доля','title':'Массовая доля вещества','formula_latex':r'\omega = \frac{m_{\text{в-ва}}}{m_{\text{р-ра}}}','formula_plain':'w = m(вещества)/m(раствора)','description':'Доля растворённого вещества в массе раствора.','variables_json':['ω — массовая доля','m вещества — масса растворённого вещества','m раствора — масса раствора'],'grade_min':8,'grade_max':11,'study_goal':'OGE','tags_json':['растворы','массовая доля'],'sort_order':20},
 {'subject':'CHEMISTRY','section':'Газы','topic':'Молярный объём','title':'Объём газа при н.у.','formula_latex':r'V = nV_m','formula_plain':'V = n*Vm','description':'Связь объёма газа и количества вещества через молярный объём.','variables_json':['V — объём газа, л','n — количество вещества, моль','Vm — молярный объём, л/моль'],'conditions':'Для школьных задач при нормальных условиях используют Vm = 22,4 л/моль.','grade_min':8,'grade_max':11,'study_goal':'OGE','tags_json':['газы','молярный объём'],'sort_order':30}
]

def seed_starter_formulas():
    """Add a small curated starter set without duplicating existing records."""
    ensure_tables();created=[]
    for item in STARTER_FORMULAS:
        conn=connect();row=conn.execute("SELECT id FROM formula_book WHERE subject=? AND title=? AND formula_plain=? LIMIT 1",(item['subject'],item['title'],item['formula_plain'])).fetchone();conn.close()
        if row:continue
        created.append(int(create_formula(item)['id']))
    return {'status':'ok','created':len(created),'formula_ids':created}
