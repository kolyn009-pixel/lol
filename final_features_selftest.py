from __future__ import annotations
import os, shutil, tempfile, sqlite3, sys
from pathlib import Path

BASE=Path(__file__).resolve().parent
src=BASE/'tutor.db'
work=Path(tempfile.mkdtemp(prefix='tutorbot_final_test_'))
db=work/'tutor.db'
shutil.copy2(src,db)

import database
database.DB_NAME=str(db)
import learning.schema as lschema
lschema.DB_PATH=str(db)

# Import after paths are patched.
from core import minute_balance
from final_features import schema
from final_features import curriculum_full,tariffs,ledger,reconcile,week,forecast,business,reports,smart,mock_tests,exam_plans,performance,slot_change

# Rebind default-path learning functions used by curriculum_full by calling with explicit path.
database.create_tables(); minute_balance.ensure_schema(); schema.initialize(); slot_change.ensure_schema(); curriculum_full.seed(str(db)); tariffs.ensure_defaults(); ledger.backfill_current()

con=database.connect()
try:
    # Core final tables exist.
    required={'minute_ledger','tariff_discount_rules','smart_actions','post_lesson_reviews','mock_tests','exam_prep_plans','health_check_runs','slot_change_requests'}
    got={r['name'] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert required<=got, required-got
    # Minute columns exist.
    pcols={r['name'] for r in con.execute('PRAGMA table_info(lesson_packages)')}
    assert {'minutes_total','minutes_used','hourly_rate'}<=pcols
    # Rich curriculum seeded.
    n=con.execute('SELECT COUNT(*) n FROM learning_topics').fetchone()['n']
    assert n>=100, n
    users=con.execute('SELECT id FROM users ORDER BY id LIMIT 1').fetchall()
finally: con.close()

assert len(tariffs.list_rules())>=16
assert isinstance(reconcile.run(),list)
assert 'projected_earned' in forecast.finance()
assert len(week.view())==7
if users:
    uid=users[0]['id']
    assert isinstance(smart.card(uid),str)
    assert isinstance(reports.build(uid),str)
    assert isinstance(performance.projection(uid),dict)
    con=database.connect(); prog=con.execute('SELECT id,study_goal FROM student_programs WHERE user_id=? AND active=1 ORDER BY id LIMIT 1',(uid,)).fetchone(); con.close()
    if prog:
        q=tariffs.package_quote(prog['id'],10)
        assert q['minutes']==q['base_duration']*10
        assert q['discount_percent']==15, q
        mid=mock_tests.assign(uid,prog['id'],'Selftest mock',deadline='2099-01-01',actor=0)
        assert mock_tests.list_for_user(uid)[0]['id']==mid
        mock_tests.complete(mid,primary_score=20,test_score=60,duration_minutes=120,result_comment='selftest')
        assert mock_tests.list_for_user(uid)[0]['status']=='REVIEWED'

print('FINAL FEATURES SELFTEST: OK')
print('Temporary DB:',db)
