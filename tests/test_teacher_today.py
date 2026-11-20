import os,sys,tempfile,types
d=tempfile.mkdtemp(dir='/tmp');path=os.path.join(d,'t.db')
os.environ['TUTORBOT_TEST_DB']=path;os.environ['TUTORBOT_TEST_DATA_DIR']=d
W=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));sys.path.insert(0,W);os.chdir(W)
fp=types.ModuleType('final_features');fp.__path__=[W+'/final_features'];sys.modules['final_features']=fp
import database
database.TEST_DB_NAME=path;database.set_test_mode(True);database.create_tables()
from core import minute_balance,payment_wait_control;minute_balance.ensure_schema()
from final_features import schema as _s;_s.initialize()
from web_backend import teacher_today as T,teacher_portal,group_lessons
F=[]
ra=types.ModuleType('web_backend.receipt_accounting')
def _ens():
    c=database.connect();c.execute("CREATE TABLE IF NOT EXISTS receipt_accounting_ack(receipt_id INTEGER PRIMARY KEY,acknowledged_at TEXT,note TEXT)");c.commit();c.close()
ra.ensure_schema=_ens
sys.modules['web_backend.receipt_accounting']=ra;import web_backend;web_backend.receipt_accounting=ra
def check(c,m):print(('PASS ' if c else 'FAIL ')+m);c or F.append(m)
def fresh():teacher_portal._CACHE.clear()
fresh();r=T.today(1)
check(r['lessons']==[] and len(r['week'])==7 and [a['kind'] for a in r['attention']]==['homework','receipt','request','message'] and all(a['count']==0 and a['items']==[] for a in r['attention']),'empty db -> empty lists')
tz,now=teacher_portal._teacher_now();day=now.date().isoformat()
u=database.add_telegram_user(8001,'s1','Ivan',10,'SCHOOL','PHYSICS')
group_lessons.ensure_schema()
c=database.connect()
c.execute("INSERT INTO lessons(duration_minutes,user_id,study_goal,subject,start_time,end_time,price,payment_status,lesson_status,created_at) VALUES(60,?,'SCHOOL','PHYSICS',?,?,1000,'AWAITING_PAYMENT','SCHEDULED',?)",(u,day+'T15:00:00',day+'T16:00:00',day+'T08:00:00'))
lid=c.execute("select max(id) from lessons").fetchone()[0]
payment_wait_control.ensure_schema()
c.execute("INSERT INTO study_groups(name,subject,study_goal,price_per_lesson,created_at,updated_at) VALUES('G1','MATH','SCHOOL',500,'x','x')")
c.execute("INSERT INTO group_lessons(group_id,start_time,end_time,price_per_student,created_at,updated_at) VALUES(1,?,?,500,'x','x')",(day+'T12:00:00',day+'T13:00:00'))
c.execute("INSERT INTO group_lesson_participants(lesson_id,user_id,created_at,updated_at) VALUES(1,?,'x','x')",(u,))
c.commit()
pid=c.execute("INSERT INTO payments(user_id,total_amount,lessons_count,price_per_lesson,status,created_at,study_goal,subject,payment_type,subtotal) VALUES(?,1000,1,1000,'WAITING','x','SCHOOL','PHYSICS','CARD',1000)",(u,)).lastrowid
c.execute("INSERT INTO receipts(payment_id,user_id,source_platform,file_type,status,created_at) VALUES(?,?,'WEB','jpg','WAITING','x')",(pid,u))
c.commit()
c.close()
fresh();r=T.today(1)
check([x['format'] for x in r['lessons']]==['GROUP','INDIVIDUAL'],'sorted: group 12:00 then individual 15:00: %s'%[x['format'] for x in r['lessons']])
g,i=r['lessons'];check(g['kind']=='group_lesson' and g['group_title']=='G1' and g['members_count']==1 and i['kind']=='lesson' and i['student_name']=='Ivan' and i['user_id']==u,'fields')
check(sum(w['lessons_count'] for w in r['week'])==2 and r['counters']['lessons_today']==2,'week/counters')
fresh();r=T.today(1);rc=[a for a in r['attention'] if a['kind']=='receipt'][0]
check(rc['count']==1 and len(rc['items'])==1 and rc['items'][0]['title']=='Ivan','WAITING receipt -> attention count 1')
import time;n1=T.today(1);check(T.today(1) is n1,'cache hit')
print('FAILED' if F else 'OK',F);sys.exit(1 if F else 0)
