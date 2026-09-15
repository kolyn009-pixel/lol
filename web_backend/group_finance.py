"""Finance primitives for Group Lessons.

Group pricing is per lesson, not hourly. Each student may have a personal
price override inside a group. Group subscriptions are isolated from the
existing individual minute balance and are consumed only by lessons of the
same group.
"""
from __future__ import annotations
from datetime import datetime
import database
from web_backend import group_lessons
VALID_PAYMENT_STATUS={"PENDING","RECEIPT_SENT","PAID","REJECTED","CANCELLED","REFUNDED"};VALID_SUBSCRIPTION_STATUS={"ACTIVE","EXHAUSTED","EXPIRED","CANCELLED","PAUSED"}
def _now():return database.now_iso()
def ensure_schema():
 group_lessons.ensure_schema();c=database.connect();c.executescript("""CREATE TABLE IF NOT EXISTS group_member_prices(group_id INTEGER NOT NULL,user_id INTEGER NOT NULL,price_per_lesson INTEGER NOT NULL,note TEXT,updated_by INTEGER,updated_at TEXT NOT NULL,PRIMARY KEY(group_id,user_id));CREATE TABLE IF NOT EXISTS group_package_options(id INTEGER PRIMARY KEY AUTOINCREMENT,group_id INTEGER NOT NULL,lessons_count INTEGER NOT NULL,total_amount INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1,validity_days INTEGER,sort_order INTEGER NOT NULL DEFAULT 100,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(group_id,lessons_count));CREATE TABLE IF NOT EXISTS group_payments(id INTEGER PRIMARY KEY AUTOINCREMENT,group_id INTEGER NOT NULL,user_id INTEGER NOT NULL,payment_kind TEXT NOT NULL,group_lesson_id INTEGER,package_option_id INTEGER,lessons_count INTEGER NOT NULL DEFAULT 1,unit_price INTEGER NOT NULL,total_amount INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'PENDING',receipt_ref TEXT,created_at TEXT NOT NULL,confirmed_at TEXT,rejected_at TEXT);CREATE TABLE IF NOT EXISTS group_subscriptions(id INTEGER PRIMARY KEY AUTOINCREMENT,group_id INTEGER NOT NULL,user_id INTEGER NOT NULL,source_payment_id INTEGER NOT NULL,lessons_total INTEGER NOT NULL,lessons_remaining INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'ACTIVE',starts_at TEXT NOT NULL,expires_at TEXT,paused_from TEXT,paused_until TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS group_subscription_ledger(id INTEGER PRIMARY KEY AUTOINCREMENT,subscription_id INTEGER NOT NULL,lesson_id INTEGER,delta INTEGER NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(subscription_id,lesson_id,reason));CREATE INDEX IF NOT EXISTS idx_group_payments_user ON group_payments(user_id,status,created_at DESC);CREATE INDEX IF NOT EXISTS idx_group_payments_group ON group_payments(group_id,status,created_at DESC);CREATE INDEX IF NOT EXISTS idx_group_subscriptions_active ON group_subscriptions(group_id,user_id,status,expires_at);""");c.commit();c.close()
def effective_price(group_id,user_id):
 ensure_schema();gid=int(group_id);uid=int(user_id);g=group_lessons.get_group(gid,uid);c=database.connect();r=c.execute("SELECT price_per_lesson FROM group_member_prices WHERE group_id=? AND user_id=?",(gid,uid)).fetchone();c.close();return int(r['price_per_lesson'] if r else g['price_per_lesson'])
def set_personal_price(group_id,user_id,price_per_lesson,teacher_id,note=None):
 ensure_schema();gid=int(group_id);uid=int(user_id);price=int(price_per_lesson)
 if price<0:raise ValueError('invalid_group_price')
 group_lessons.get_group(gid,uid)
 if not database.get_user(uid):raise PermissionError('student_not_found')
 c=database.connect();c.execute("INSERT INTO group_member_prices(group_id,user_id,price_per_lesson,note,updated_by,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(group_id,user_id) DO UPDATE SET price_per_lesson=excluded.price_per_lesson,note=excluded.note,updated_by=excluded.updated_by,updated_at=excluded.updated_at",(gid,uid,price,str(note or '')[:500] or None,int(teacher_id),_now()));c.commit();c.close();return {'status':'ok','group_id':gid,'user_id':uid,'price_per_lesson':price}
def clear_personal_price(group_id,user_id):
 ensure_schema();c=database.connect();c.execute("DELETE FROM group_member_prices WHERE group_id=? AND user_id=?",(int(group_id),int(user_id)));c.commit();c.close();return {'status':'ok','group_id':int(group_id),'user_id':int(user_id)}
def upsert_package_option(group_id,lessons_count,total_amount,validity_days=None,sort_order=100):
 ensure_schema();gid=int(group_id);count=int(lessons_count);total=int(total_amount)
 if count<2 or count>100:raise ValueError('invalid_lessons_count')
 if total<0:raise ValueError('invalid_total_amount')
 days=int(validity_days) if validity_days not in(None,'') else None
 if days is not None and days<1:raise ValueError('invalid_validity_days')
 group_lessons.get_group(gid);now=_now();c=database.connect();c.execute("INSERT INTO group_package_options(group_id,lessons_count,total_amount,active,validity_days,sort_order,created_at,updated_at) VALUES(?,?,?,1,?,?,?,?) ON CONFLICT(group_id,lessons_count) DO UPDATE SET total_amount=excluded.total_amount,active=1,validity_days=excluded.validity_days,sort_order=excluded.sort_order,updated_at=excluded.updated_at",(gid,count,total,days,int(sort_order),now,now));c.commit();c.close();return {'status':'ok','group_id':gid,'lessons_count':count,'total_amount':total,'validity_days':days}
def package_options(group_id,user_id=None):
 ensure_schema();gid=int(group_id);base=effective_price(gid,user_id) if user_id is not None else int(group_lessons.get_group(gid)['price_per_lesson']);c=database.connect();rows=c.execute("SELECT * FROM group_package_options WHERE group_id=? AND active=1 ORDER BY sort_order,lessons_count",(gid,)).fetchall();c.close();out=[{'kind':'SINGLE','lessons_count':1,'total_amount':base,'unit_price':base,'validity_days':None}]
 for r in rows:
  total=int(r['total_amount']);count=int(r['lessons_count']);out.append({'id':int(r['id']),'kind':'PACKAGE','lessons_count':count,'total_amount':total,'unit_price':round(total/count,2),'validity_days':r['validity_days']})
 return out
def create_single_payment(user_id,group_lesson_id):
 ensure_schema();uid=int(user_id);lid=int(group_lesson_id);c=database.connect();lesson=c.execute("SELECT group_id,status FROM group_lessons WHERE id=?",(lid,)).fetchone()
 if not lesson:c.close();raise ValueError('group_lesson_not_found')
 gid=int(lesson['group_id']);part=c.execute("SELECT 1 FROM group_lesson_participants WHERE lesson_id=? AND user_id=?",(lid,uid)).fetchone()
 if not part:c.close();raise PermissionError('not_group_lesson_participant')
 existing=c.execute("SELECT * FROM group_payments WHERE group_lesson_id=? AND user_id=? AND status NOT IN ('REJECTED','CANCELLED','REFUNDED') ORDER BY id DESC LIMIT 1",(lid,uid)).fetchone()
 if existing:c.close();return {'status':'exists','payment':dict(existing)}
 price=effective_price(gid,uid);now=_now();cur=c.execute("INSERT INTO group_payments(group_id,user_id,payment_kind,group_lesson_id,lessons_count,unit_price,total_amount,status,created_at) VALUES(?,?,'SINGLE',?,1,?,?,'PENDING',?)",(gid,uid,lid,price,price,now));pid=int(cur.lastrowid);c.commit();row=c.execute("SELECT * FROM group_payments WHERE id=?",(pid,)).fetchone();c.close();return {'status':'ok','payment':dict(row)}
def create_package_payment(user_id,group_id,package_option_id):
 ensure_schema();uid=int(user_id);gid=int(group_id);oid=int(package_option_id);group_lessons.get_group(gid,uid);c=database.connect();opt=c.execute("SELECT * FROM group_package_options WHERE id=? AND group_id=? AND active=1",(oid,gid)).fetchone()
 if not opt:c.close();raise ValueError('group_package_not_found')
 count=int(opt['lessons_count']);total=int(opt['total_amount']);unit=round(total/count);cur=c.execute("INSERT INTO group_payments(group_id,user_id,payment_kind,package_option_id,lessons_count,unit_price,total_amount,status,created_at) VALUES(?,?,'PACKAGE',?,?,?,?, 'PENDING',?)",(gid,uid,oid,count,unit,total,_now()));pid=int(cur.lastrowid);c.commit();row=c.execute("SELECT * FROM group_payments WHERE id=?",(pid,)).fetchone();c.close();return {'status':'ok','payment':dict(row)}
def mark_receipt_sent(payment_id,receipt_ref=None):
 ensure_schema();pid=int(payment_id);c=database.connect();cur=c.execute("UPDATE group_payments SET status='RECEIPT_SENT',receipt_ref=? WHERE id=? AND status='PENDING'",(str(receipt_ref or '')[:1200] or None,pid));c.commit();c.close()
 if not cur.rowcount:raise ValueError('group_payment_not_pending')
 return {'status':'ok','payment_id':pid}
def approve_payment(payment_id,teacher_id):
 ensure_schema();pid=int(payment_id);now=_now();c=database.connect();p=c.execute("SELECT * FROM group_payments WHERE id=?",(pid,)).fetchone()
 if not p:c.close();raise ValueError('group_payment_not_found')
 if p['status']=='PAID':c.close();return {'status':'ok','payment_id':pid,'already_paid':True}
 if p['status'] not in {'PENDING','RECEIPT_SENT'}:c.close();raise ValueError('group_payment_not_approvable')
 c.execute("UPDATE group_payments SET status='PAID',confirmed_at=? WHERE id=?",(now,pid));sid=None
 if p['payment_kind']=='PACKAGE':
  opt=c.execute("SELECT validity_days FROM group_package_options WHERE id=?",(p['package_option_id'],)).fetchone();expires=(datetime.fromisoformat(now)+__import__('datetime').timedelta(days=int(opt['validity_days']))).isoformat(timespec='seconds') if opt and opt['validity_days'] else None;cur=c.execute("INSERT INTO group_subscriptions(group_id,user_id,source_payment_id,lessons_total,lessons_remaining,status,starts_at,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,'ACTIVE',?,?,?,?)",(int(p['group_id']),int(p['user_id']),pid,int(p['lessons_count']),int(p['lessons_count']),now,expires,now,now));sid=int(cur.lastrowid)
 c.commit();c.close();return {'status':'ok','payment_id':pid,'subscription_id':sid,'approved_by':int(teacher_id)}
def _active_subscription_row(c,group_id,user_id):
 now=_now();return c.execute("SELECT * FROM group_subscriptions WHERE group_id=? AND user_id=? AND status='ACTIVE' AND lessons_remaining>0 AND (expires_at IS NULL OR expires_at>?) AND (paused_until IS NULL OR paused_until<=? OR paused_from>?) ORDER BY id LIMIT 1",(int(group_id),int(user_id),now,now,now)).fetchone()
def financial_status_for_lesson(lesson_id,user_id):
 ensure_schema();lid=int(lesson_id);uid=int(user_id);c=database.connect();lesson=c.execute("SELECT group_id FROM group_lessons WHERE id=?",(lid,)).fetchone()
 if not lesson:c.close();raise ValueError('group_lesson_not_found')
 paid=c.execute("SELECT id FROM group_payments WHERE group_lesson_id=? AND user_id=? AND status='PAID' LIMIT 1",(lid,uid)).fetchone()
 if paid:c.close();return {'status':'PAID','payment_id':int(paid['id']),'covered':True}
 reserved=c.execute("""SELECT l.subscription_id,s.lessons_remaining
                         FROM group_subscription_ledger l
                         JOIN group_subscriptions s ON s.id=l.subscription_id
                        WHERE l.lesson_id=? AND l.reason='LESSON_RESERVE'
                          AND s.user_id=? AND s.group_id=?
                          AND NOT EXISTS(
                              SELECT 1 FROM group_subscription_ledger r
                               WHERE r.subscription_id=l.subscription_id
                                 AND r.lesson_id=l.lesson_id
                                 AND r.reason='LESSON_REFUND'
                          )
                        ORDER BY l.id DESC LIMIT 1""",(lid,uid,int(lesson['group_id']))).fetchone()
 if reserved:c.close();return {'status':'COVERED','subscription_id':int(reserved['subscription_id']),'lessons_remaining':int(reserved['lessons_remaining'] or 0),'covered':True,'reserved':True}
 sub=_active_subscription_row(c,int(lesson['group_id']),uid);c.close()
 if sub:return {'status':'COVERED','subscription_id':int(sub['id']),'lessons_remaining':int(sub['lessons_remaining']),'covered':True}
 return {'status':'UNPAID','covered':False,'price_per_lesson':effective_price(int(lesson['group_id']),uid)}
def reserve_subscription_for_lesson(lesson_id,user_id):
 from web_backend import group_finance_reservations
 return group_finance_reservations.reserve_for_student(lesson_id,user_id)
def refund_subscription_for_lesson(lesson_id):
 from web_backend import group_finance_reservations
 return group_finance_reservations.refund_all_for_lesson(lesson_id)
def group_finance_overview(user_id):
 ensure_schema();uid=int(user_id);c=database.connect();memberships=c.execute("SELECT g.id,g.name,g.subject,g.study_goal,g.price_per_lesson FROM group_members gm JOIN study_groups g ON g.id=gm.group_id WHERE gm.user_id=? AND gm.status='ACTIVE' AND g.active=1 ORDER BY g.name",(uid,)).fetchall();result=[]
 for g in memberships:
  gid=int(g['id']);price=effective_price(gid,uid);subs=c.execute("SELECT * FROM group_subscriptions WHERE group_id=? AND user_id=? ORDER BY id DESC",(gid,uid)).fetchall();result.append({'group_id':gid,'group_name':g['name'],'subject':g['subject'],'study_goal':g['study_goal'],'price_per_lesson':price,'packages':package_options(gid,uid),'subscriptions':[dict(x) for x in subs]})
 c.close();return result