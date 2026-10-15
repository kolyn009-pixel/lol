"""Add reviewed handbook entries once; never overwrite teacher-edited formulas."""
from pathlib import Path
import json
import re
from web_backend import formula_book

CATALOG=Path(__file__).resolve().parents[1]/'data/formulas/physics_handbook_20261015.json'
def seed():
    source=json.loads(CATALOG.read_text(encoding='utf-8'));formula_book.ensure_tables()
    conn=formula_book.connect();created=linked=0
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS formula_catalog_seeds(seed_key TEXT PRIMARY KEY,formula_id INTEGER NOT NULL,source_page INTEGER NOT NULL,created_at TEXT NOT NULL)')
        conn.commit();conn.execute('BEGIN IMMEDIATE')
        existing={}
        clean=lambda value:re.sub(r'\s+','',str(value or ''))
        for row in conn.execute('SELECT id,subject,formula_latex FROM formula_book'):
            existing.setdefault((row['subject'],clean(row['formula_latex'])),int(row['id']))
        for item in source['items']:
            if conn.execute('SELECT 1 FROM formula_catalog_seeds WHERE seed_key=?',(item['seed_key'],)).fetchone():continue
            key=(item['subject'],clean(item['formula_latex']));fid=existing.get(key)
            if not fid:
                fields=formula_book._validate_effective(formula_book._normalize(item,True));columns=list(fields)
                cur=conn.execute(f"INSERT INTO formula_book({','.join(columns)},created_at,updated_at) VALUES({','.join('?' for _ in columns)},?,?)",(*[fields[k] for k in columns],formula_book.now_iso(),formula_book.now_iso()))
                fid=int(cur.lastrowid);existing[key]=fid;created+=1
            else:linked+=1
            conn.execute('INSERT INTO formula_catalog_seeds VALUES(?,?,?,?)',(item['seed_key'],fid,item['source_pdf_page'],formula_book.now_iso()))
        conn.commit();return {'created':created,'linked_existing':linked,'reviewed_entries':len(source['items'])}
    except Exception:conn.rollback();raise
    finally:conn.close()
if __name__=='__main__':print(json.dumps(seed(),ensure_ascii=False))
