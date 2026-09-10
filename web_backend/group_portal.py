"""Facade for Group Lessons web/mobile surfaces."""
from __future__ import annotations
from datetime import datetime,timedelta
import database
from web_backend import group_lessons,group_finance,group_runtime_v2,group_trials_and_coaching

def _now():return database.now_iso()
def ensure_schema():
 group_runtime_v2.ensure_schema();group_trials_and_coaching.ensure_schema();c=database.connect();c.executescript("""CREATE TABLE IF NOT EXISTS open_learning_events (id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,event_type TEXT NOT NULL DEFAULT 'MOCK_EXAM',subject TEXT,grade_min INTEGER,grade_max INTEGER,starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,price_per_student INTEGER NOT NULL DEFAULT 0,max_participants INTEGER,registration_deadline TEXT,status TEXT NOT NULL DEFAULT 'OPEN',board_url TEXT,telemost_conference_id TEXT,telemost_join_url TEXT,created_by INTEGER,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS open_event_groups(event_id INTEGER NOT NULL,group_id INTEGER NOT NULL,PRIMARY KEY(event_id,group_id),FOREIGN KEY(event_id) REFERENCES open_learning_events(id) ON DELETE CASCADE,FOREIGN KEY(group_id) REFERENCES study_groups(id) ON DELETE CASCADE);CREATE TABLE IF NOT EXISTS open_event_participants(event_id INTEGER NOT NULL,user_id INTEGER NOT NULL,source_group_id INTEGER,status TEXT NOT NULL DEFAULT 'REGISTERED',payment_status TEXT NOT NULL DEFAULT 'UNPAID',teacher_decision TEXT NOT NULL DEFAULT 'PENDING',access_granted INTEGER NOT NULL DEFAULT 0,result_score REAL,result_max REAL,result_note TEXT,registered_at TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(event_id,user_id),FOREIGN KEY(event_id) REFERENCES open_learning_events(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(source_group_id) REFERENCES study_groups(id) ON DELETE SET NULL);CREATE INDEX IF NOT EXISTS idx_open_events_time ON open_learning_events(starts_at,status);CREATE INDEX IF NOT EXISTS idx_open_event_participant ON open_event_participants(user_id,status,event_id);CREATE INDEX IF NOT EXISTS idx_group_chat_time ON group_chat_messages(group_id,created_at,id);""");c.commit();c.close()
def teacher_groups_overview():
 ensure_schema();c=database.connect();rows=c.execute("""SELECT g.*,(SELECT COUNT(*) FROM group_members m WHERE m.group_id=g.id AND m.status IN ('ACTIVE','PAUSED')) AS member_count,(SELECT COUNT(*) FROM group_homework h JOIN group_homework_delivery d ON d.homework_id=h.id LEFT JOIN group_homework_submissions s ON s.homework_id=h.id AND s.user_id=d.user_id WHERE h.group_id=g.id AND d.state='ASSIGNED' AND s.id IS NULL) AS homework_missing,(SELECT COUNT(*) FROM group_schedule_proposals p WHERE p.group_id=g.id AND p.status='VOTING') AS open_votes FROM study_groups g WHERE g.active=1 ORDER BY g.name""").fetchall();c.close();return [{**dict(r),'health':group_health(int(r['id']))} for r in rows]
def group_health(group_id):
 ensure_schema();gid=int(group_id);c=database.connect();members=int(c.execute("SELECT COUNT(*) n FROM group_members WHERE group_id=? AND status IN ('ACTIVE','PAUSED')",(gid,)).fetchone()['n']);paused=int(c.execute("SELECT COUNT(*) n FROM group_members WHERE group_id=? AND status='PAUSED'",(gid,)).fetchone()['n']);unpaid=int(c.execute("SELECT COUNT(*) n FROM group_lesson_participants p JOIN group_lessons l ON l.id=p.lesson_id WHERE l.group_id=? AND l.start_time>=? AND p.payment_status NOT IN ('PAID','COVERED','WAIVED') AND p.attendance_status<>'PAUSED'",(gid,_now())).fetchone()['n']);missing=int(c.execute("SELECT COUNT(*) n FROM group_homework h JOIN group_homework_delivery d ON d.homework_id=h.id LEFT JOIN group_homework_submissions s ON s.homework_id=h.id AND s.user_id=d.user_id WHERE h.group_id=? AND d.state='ASSIGNED' AND s.id IS NULL",(gid,)).fetchone()['n']);waiting=int(c.execute("SELECT COUNT(*) n FROM group_schedule_proposals WHERE group_id=? AND status='VOTING'",(gid,)).fetchone()['n']);c.close();return {'members':members,'paused':paused,'unpaid_upcoming':unpaid,'homework_missing':missing,'open_schedule_votes':waiting}
def teacher_group_cabinet(group_id):
 gid=int(group_id);g=group_lessons.get_group(gid);c=database.connect();upcoming=[dict(r) for r in c.execute("SELECT * FROM group_lessons WHERE group_id=? AND start_time>=? ORDER BY start_time LIMIT 20",(gid,_now())).fetchall()];proposals=[dict(r) for r in c.execute("SELECT * FROM group_schedule_proposals WHERE group_id=? ORDER BY created_at DESC LIMIT 20",(gid,)).fetchall()];hw=[dict(r) for r in c.execute("SELECT * FROM group_homework WHERE group_id=? ORDER BY created_at DESC LIMIT 20",(gid,)).fetchall()];recs=group_trials_and_coaching.open_recommendations_for_teacher(gid);c.close();return {'group':g,'health':group_health(gid),'upcoming_lessons':upcoming,'schedule_proposals':proposals,'homework':hw,'coaching_recommendations':recs}
def student_groups(user_id):
 ensure_schema();c=database.connect();rows=c.execute("SELECT g.*,m.status AS membership_status,m.joined_at FROM group_members m JOIN study_groups g ON g.id=m.group_id WHERE m.user_id=? AND m.status IN ('ACTIVE','PAUSED') AND g.active=1 ORDER BY g.name",(int(user_id),)).fetchall();c.close();return [dict(r) for r in rows]
def student_group_summary(user_id,group_id):
 uid=int(user_id);gid=int(group_id);g=group_lessons.get_group(gid,uid)
 if not g.get('my_membership'):
  c=database.connect();m=c.execute("SELECT * FROM group_members WHERE group_id=? AND user_id=? AND status IN ('ACTIVE','PAUSED')",(gid,uid)).fetchone();c.close()
  if not m:raise PermissionError('not_group_member')
 c=database.connect();upcoming=[dict(r) for r in c.execute("SELECT l.*,p.payment_status,p.attendance_status,p.access_granted FROM group_lessons l JOIN group_lesson_participants p ON p.lesson_id=l.id WHERE l.group_id=? AND p.user_id=? AND l.start_time>=? ORDER BY l.start_time LIMIT 12",(gid,uid,_now())).fetchall()];c.close();return {'group':g,'pause':group_runtime_v2.active_pause(gid,uid),'upcoming_lessons':upcoming,'finance':group_finance.group_finance_overview(uid)}
def post_group_message(group_id,sender_user_id,sender_role,body):
 ensure_schema();gid=int(group_id);role=str(sender_role or '').upper();text=str(body or '').strip()
 if role not in {'STUDENT','TEACHER'}:raise ValueError('invalid_sender_role')
 if not text:raise ValueError('message_required')
 if len(text)>4000:raise ValueError('message_too_long')
 g=group_lessons.get_group(gid)
 if g['chat_mode']=='CLOSED':raise ValueError('group_chat_closed')
 uid=int(sender_user_id) if sender_user_id is not None else None
 if role=='STUDENT':
  if g['chat_mode']=='ANNOUNCEMENTS':raise PermissionError('group_chat_read_only')
  c=database.connect();m=c.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=? AND status IN ('ACTIVE','PAUSED')",(gid,uid)).fetchone();c.close()
  if not m:raise PermissionError('not_group_member')
 c=database.connect();cur=c.execute("INSERT INTO group_chat_messages(group_id,sender_user_id,sender_role,body,created_at) VALUES(?,?,?,?,?)",(gid,uid,role,text,_now()));mid=int(cur.lastrowid);c.commit();c.close();return {'status':'ok','message_id':mid}
def group_chat(group_id,user_id=None,limit=100):
 ensure_schema();gid=int(group_id);viewer=int(user_id) if user_id is not None else None
 if viewer is not None:
  c=database.connect();m=c.execute("SELECT 1 FROM group_members WHERE group_id=? AND user_id=? AND status IN ('ACTIVE','PAUSED')",(gid,viewer)).fetchone();c.close()
  if not m:raise PermissionError('not_group_member')
 c=database.connect();rows=c.execute("SELECT m.id,m.sender_user_id,m.sender_role,m.body,m.created_at,COALESCE(p.display_name,u.name) AS sender_name FROM group_chat_messages m LEFT JOIN users u ON u.id=m.sender_user_id LEFT JOIN student_social_profiles p ON p.user_id=m.sender_user_id WHERE m.group_id=? AND m.deleted_at IS NULL ORDER BY m.id DESC LIMIT ?",(gid,max(1,min(int(limit),300)))).fetchall();c.close();out=[]
 for r in reversed(rows):
  item=dict(r);item['mine']=viewer is not None and item.get('sender_user_id') is not None and int(item['sender_user_id'])==viewer;out.append(item)
 return out
def create_open_event(title,starts_at,duration_minutes,*,event_type='MOCK_EXAM',subject=None,grade_min=None,grade_max=None,price_per_student=0,max_participants=None,registration_deadline=None,group_ids=None,board_url=None,created_by=None):
 ensure_schema();title=str(title or '').strip();duration=int(duration_minutes);price=int(price_per_student or 0)
 if len(title)<2:raise ValueError('event_title_required')
 if duration<30 or duration>480:raise ValueError('invalid_duration')
 start=datetime.fromisoformat(str(starts_at));end=start+timedelta(minutes=duration);now=_now();c=database.connect();cur=c.execute("INSERT INTO open_learning_events(title,event_type,subject,grade_min,grade_max,starts_at,ends_at,price_per_student,max_participants,registration_deadline,status,board_url,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,'OPEN',?,?,?,?)",(title,str(event_type or 'MOCK_EXAM').upper(),subject,int(grade_min) if grade_min is not None else None,int(grade_max) if grade_max is not None else None,start.isoformat(),end.isoformat(),price,int(max_participants) if max_participants else None,registration_deadline,board_url,int(created_by) if created_by is not None else None,now,now));eid=int(cur.lastrowid);c.commit();c.close();return {'status':'ok','event_id':eid}
def open_events_for_student(user_id):
 from web_backend import event_campaign
 return event_campaign.feed(int(user_id))
def register_open_event(event_id,user_id,source_group_id=None):
 from web_backend import event_campaign
 return event_campaign.register(int(event_id),int(user_id))
def decide_open_event_participant(event_id,user_id,allowed):
 ensure_schema();c=database.connect();cur=c.execute("UPDATE open_event_participants SET teacher_decision=?,updated_at=? WHERE event_id=? AND user_id=? AND status='REGISTERED'",('APPROVED' if allowed else 'EXCLUDED',_now(),int(event_id),int(user_id)));c.commit();c.close()
 if not cur.rowcount:raise ValueError('event_participant_not_found')
 return {'status':'ok','allowed':bool(allowed)}
def start_open_event(event_id,telemost_join_url=None,board_url=None):
 ensure_schema();eid=int(event_id);now=_now();c=database.connect();event=c.execute("SELECT * FROM open_learning_events WHERE id=?",(eid,)).fetchone()
 if not event:c.close();raise ValueError('event_not_found')
 pending=int(c.execute("SELECT COUNT(*) n FROM open_event_participants WHERE event_id=? AND status='REGISTERED' AND teacher_decision='PENDING'",(eid,)).fetchone()['n'])
 if pending:c.close();raise ValueError('participant_decisions_pending')
 c.execute("UPDATE open_learning_events SET status='IN_PROGRESS',telemost_join_url=COALESCE(?,telemost_join_url),board_url=COALESCE(?,board_url),updated_at=? WHERE id=?",(telemost_join_url,board_url,now,eid));c.execute("UPDATE open_event_participants SET access_granted=CASE WHEN teacher_decision='APPROVED' THEN 1 ELSE 0 END,updated_at=? WHERE event_id=?",(now,eid));c.commit();c.close();return {'status':'ok','event_id':eid}
def open_event_access(event_id,user_id):
 ensure_schema();c=database.connect();row=c.execute("SELECT e.title,e.status,e.telemost_join_url,e.board_url,p.teacher_decision,p.access_granted,p.payment_status FROM open_learning_events e JOIN open_event_participants p ON p.event_id=e.id WHERE e.id=? AND p.user_id=?",(int(event_id),int(user_id))).fetchone();c.close()
 if not row:raise PermissionError('event_not_available')
 allowed=bool(row['access_granted']) and row['status']=='IN_PROGRESS';return {'allowed':allowed,'title':row['title'],'payment_status':row['payment_status'],'meeting_url':row['telemost_join_url'] if allowed else None,'board_url':row['board_url'] if allowed else None}
def save_open_event_result(event_id,user_id,score,max_score=None,note=None):
 ensure_schema();c=database.connect();cur=c.execute("UPDATE open_event_participants SET result_score=?,result_max=?,result_note=?,updated_at=? WHERE event_id=? AND user_id=?",(float(score),float(max_score) if max_score is not None else None,str(note or '')[:2000] or None,_now(),int(event_id),int(user_id)));c.commit();c.close()
 if not cur.rowcount:raise ValueError('event_participant_not_found')
 return {'status':'ok'}
def teacher_schedule_cards(from_time=None,to_time=None):
 ensure_schema();start=str(from_time or _now());end=str(to_time or (datetime.fromisoformat(start)+timedelta(days=30)).isoformat());c=database.connect();cards=[]
 for r in c.execute("SELECT l.id,l.group_id,l.start_time,l.end_time,l.status,g.name,(SELECT COUNT(*) FROM group_lesson_participants p WHERE p.lesson_id=l.id AND p.attendance_status<>'PAUSED') AS participants FROM group_lessons l JOIN study_groups g ON g.id=l.group_id WHERE l.start_time>=? AND l.start_time<=? ORDER BY l.start_time",(start,end)).fetchall():cards.append({'kind':'GROUP','id':int(r['id']),'start_time':r['start_time'],'end_time':r['end_time'],'title':f"👥 {r['name']}",'status':r['status'],'participants':int(r['participants'])})
 for r in c.execute("SELECT * FROM open_learning_events WHERE starts_at>=? AND starts_at<=? ORDER BY starts_at",(start,end)).fetchall():n=int(c.execute("SELECT COUNT(*) n FROM open_event_participants WHERE event_id=? AND status='REGISTERED'",(int(r['id']),)).fetchone()['n']);cards.append({'kind':'OPEN_EVENT','id':int(r['id']),'start_time':r['starts_at'],'end_time':r['ends_at'],'title':f"📝 {r['title']}",'status':r['status'],'participants':n})
 c.close();cards.sort(key=lambda x:x['start_time']);return cards
