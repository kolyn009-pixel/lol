"""Isolated smoke test for Stage 7 formula handbook.
Run only with ADELIA_DB_PATH pointing at a disposable database.
"""
from __future__ import annotations
import json, os

path=os.environ.get('ADELIA_DB_PATH','')
if not path or os.path.exists(path):
    raise SystemExit('Set ADELIA_DB_PATH to a NEW disposable sqlite path before running this test')

from database import connect
from web_backend.formula_book import create_formula,list_formulas,formula_detail,update_formula,seed_starter_formulas
from web_backend.formula_import import create_draft,draft,update_item,approve_item,commit
from web_backend.stage7_api import Stage7Mixin
from web_backend import api_v2

assert issubclass(api_v2.Handler,Stage7Mixin)
conn=connect()
# Minimal user table required by favorites/FKs in installations where database.initialize is not called.
conn.execute('CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, active INTEGER DEFAULT 1)')
conn.execute("INSERT OR IGNORE INTO users(id,name,active) VALUES(1,'Test',1)")
conn.commit();conn.close()

seed=seed_starter_formulas();assert seed['status']=='ok'
seed2=seed_starter_formulas();assert seed2['created']==0

school=create_formula({'subject':'PHYSICS','title':'School only','formula_latex':'F=ma','formula_plain':'F=ma','education_level':'SCHOOL','grade_min':9,'grade_max':9})['id']
college=create_formula({'subject':'PHYSICS','title':'College only','formula_latex':'pV=nRT','formula_plain':'pV=nRT','education_level':'COLLEGE','course_min':1,'course_max':2})['id']
assert any(x['id']==school for x in list_formulas(education_level='SCHOOL'))
assert not any(x['id']==college for x in list_formulas(education_level='SCHOOL'))
assert any(x['id']==college for x in list_formulas(education_level='COLLEGE'))
assert formula_detail(college)['course_max']==2
assert update_formula(school,{'description':'updated'})['status']=='ok'
assert formula_detail(school)['description']=='updated'

for bad in (
 {'subject':'PHYSICS','title':'bad','formula_latex':'x','education_level':'SCHOOL','grade_min':12},
 {'subject':'PHYSICS','title':'bad','formula_latex':'x','education_level':'COLLEGE','course_min':3},
 {'subject':'CHEMISTRY','title':'bad','formula_latex':'x','education_level':'COLLEGE','course_min':1},
):
    try:create_formula(bad);raise AssertionError('invalid scope accepted')
    except ValueError:pass

payload=json.dumps([{'subject':'PHYSICS','title':'Imported college','formula_latex':'A=B','formula_plain':'A=B','education_level':'COLLEGE','course_min':1,'course_max':2}],ensure_ascii=False).encode()
r=create_draft(payload,'formulas.json');assert r['items']==1
job=r['job_id'];item=draft(job)['items'][0];assert item['education_level']=='COLLEGE' and item['course_max']==2
update_item(item['id'],{'title':'Imported edited'});approve_item(item['id'],True)
out=commit(job);assert out['created']==1
again=commit(job);assert again['created']==0 and again['already_imported']
assert formula_detail(out['formula_ids'][0])['title']=='Imported edited'
print('STAGE7_FORMULA_SELFTEST_OK')
