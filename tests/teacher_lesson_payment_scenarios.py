import os,sys,tempfile,types
d=tempfile.mkdtemp(dir='/tmp'); path=os.path.join(d,'t.db')
os.environ['TUTORBOT_TEST_DB']=path; os.environ['TUTORBOT_TEST_DATA_DIR']=d
W=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0,W); os.chdir(W)
fp=types.ModuleType('final_features'); fp.__path__=[W+'/final_features']; sys.modules['final_features']=fp
import database
database.TEST_DB_NAME=path; database.set_test_mode(True); database.create_tables()
from core import minute_balance, payment_reversal, payment_wait_control; minute_balance.ensure_schema()
from final_features import schema as _s; _s.initialize()
from final_features import ledger
from web_backend import push_events, teacher_lesson_payment as T
SENT=[]
push_events.student_and_parents=lambda *a,**k: SENT.append((a,k)) or {'ok':1}
F=[]
def check(c,msg): print(('PASS ' if c else 'FAIL ')+msg); c or F.append(msg)
def q(sql,*a):
    c=database.connect(); r=[dict(x) for x in c.execute(sql,a).fetchall()]; c.close(); return r
n=[0]
def user():
    n[0]+=1; return database.add_telegram_user(7000+n[0],'u%d'%n[0],'U',10,'SCHOOL','PHYSICS')
def lesson(u,price=1000,day=1):
    c=database.connect(); c.execute("INSERT INTO lessons(duration_minutes,user_id,study_goal,subject,start_time,end_time,price,payment_status,lesson_status,created_at) VALUES(60,?,'SCHOOL','PHYSICS',?,?,?,'AWAITING_PAYMENT','CONFIRMED','2026-01-01')",(u,'2026-12-%02dT10:00'%day,'2026-12-%02dT11:00'%day,price)); c.commit(); i=c.execute('select max(id) from lessons').fetchone()[0]; c.close(); return i
A=999
u=user(); L=lesson(u)
# 1
code,r=T.handle({'lesson_id':L,'action':'paid','lessons_count':4},A); print(r)
lp=q('select * from lessons where id=?',L)[0]; pk=q('select * from lesson_packages where id=?',r.get('package_id'))
check(code==200 and lp['payment_status']=='PAID','1 paid N=4 -> PAID')
check(pk and pk[0]['lessons_total']==4 and pk[0]['lessons_used']==1 and pk[0]['status']=='ACTIVE','1 package 4/1 ACTIVE')
check(r['balance_lessons_after']==3 and r['amount']==4000 and r['lessons_count']==4,'1 balance 3, amount 4000')
check(len(SENT)==1 and SENT[0][0][5]=='pay-ok-%d'%r['payment_id'] and 'На балансе занятий: 3.' in SENT[0][0][2],'1 notify once with pay-ok key')
check(ledger.derived_balance(u)['paid']==180,'1 ledger credit 180 min (=3 lessons)')
check(database.retry_uncredited_payments()==0 and ledger.derived_balance(u)['paid']==180,'1 retry does not double-credit')
# 2
code2,r2=T.handle({'lesson_id':L,'action':'paid','lessons_count':4},A)
check(code2==200 and r2['already_paid'] and r2['payment_id']==r['payment_id'] and r2['package_id']==r['package_id'],'2 repeat -> already_paid same ids')
check(len(q('select id from lesson_packages where user_id=?',u))==1 and len(SENT)==1,'2 no 2nd package, no 2nd notify')
check(database.confirm_manual_lesson_payment(L,None,with_created=True)[2] is False,'2 db created=False on repeat')
# 3
L2=lesson(u,day=2)
for bad in (0,101,'x',2.5,True):
    c,rr=T.handle({'lesson_id':L2,'action':'paid','lessons_count':bad},A); check(c==400 and rr['error']=='invalid_lessons_count' and 'от 1 до 100' in rr['message'],'3 N=%r -> 400'%(bad,))
c,rr=T.handle({'lesson_id':L2,'action':'paid','lessons_count':3,'amount':1000},A); check(c==400 and rr['error']=='amount_must_divide_by_lessons','3 amount not divisible -> 400')
L0=lesson(u,price=0,day=3); c,rr=T.handle({'lesson_id':L0,'action':'paid'},A); check(c==400 and rr['message']=='Укажите сумму','3 price 0 no amount -> Укажите сумму')
c,rr=T.handle({'lesson_id':L0,'action':'paid','amount':1500},A); check(c==200 and rr['amount']==1500,'3 price 0 + amount -> ok')
# 4
SENT.clear(); c,rr=T.handle({'lesson_id':L2,'action':'await'},A)
check(c==200 and rr=={'status':'ok','action':'await','lesson_id':L2,'already_confirmed':False},'4 await ok')
check(payment_wait_control.suppress_auto_cancel(L2) and not payment_wait_control.pending_teacher_decision(L2),'4 wait flag set (suppress_auto_cancel)')
check(SENT==[],'4 no student/parent notify on await')
bal_before=T.balance_lessons(u); led_before=ledger.derived_balance(u)['paid']
c,r4=T.handle({'lesson_id':L2,'action':'paid','lessons_count':1},A); check(c==200 and r4['balance_lessons_after']==bal_before and len(SENT)==1,'4 paid N=1 ok, balance unchanged')
# 5 reverse first (package) payment
bal_pre=T.balance_lessons(u)
rv=payment_reversal.reverse(r['payment_id'],actor_id=A,source='TEST')
lp=q('select * from lessons where id=?',L)[0]
check(lp['payment_status']=='AWAITING_PAYMENT' and lp['package_id'] is None,'5 lesson back to AWAITING_PAYMENT')
check(T.balance_lessons(u)==bal_pre-3,'5 package balance removed (%d->%d)'%(bal_pre,T.balance_lessons(u)))
check(ledger.derived_balance(u)['paid']==led_before-180,'5 ledger restored (net 0 for reversed payment)')
rv2=payment_reversal.reverse(r4['payment_id'],actor_id=A,source='TEST')
check(q('select payment_status from lessons where id=?',L2)[0]['payment_status']=='AWAITING_PAYMENT','5 single reverse -> AWAITING_PAYMENT')
check(ledger.derived_balance(u)['paid']==0,'5 ledger total 0 after reversing PAID-lesson payments except L0 (%d)'%ledger.derived_balance(u)['paid'])
# 6
u2=user(); L6=lesson(u2); p=database.create_payment(u2,'SCHOOL','PHYSICS',1,1000)
cc=database.connect(); cc.execute('update payments set lesson_id=? where id=?',(L6,p)); cc.commit(); cc.close()
c,rr=T.handle({'lesson_id':L6,'action':'paid'},A); check(c==409 and rr['message']=='По этому занятию уже выставлен счёт — подтвердите его в разделе «Оплаты»','6 WAITING invoice -> 409')
check(T.handle({'lesson_id':L6,'action':'x'},A)[0]==400 and T.handle({'action':'paid'},A)[0]==400,'bad action / no lesson -> 400')
# legacy endpoint path
from web_backend.finance_reporting import mark_lesson_paid
L7=lesson(u2,day=7); u3=user(); L8=lesson(u3,day=8)
check(mark_lesson_paid(L8)['status']=='ok' and q('select lessons_total from lesson_packages where user_id=?',u3)[0]['lessons_total']==1,'legacy default N=1')
u4=user(); L9=lesson(u4,day=9); mark_lesson_paid(L9,None,lessons_count=5); check(q('select lessons_total from lesson_packages where user_id=?',u4)[0]['lessons_total']==5,'legacy N=5')
print('FAILED:',F) if F else print('ALL PASS')
