import os, tempfile
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd); os.unlink(path)
os.environ['TUTORBOT_TEST_DB']=path
import database
database.TEST_DB_NAME=path
database.set_test_mode(True)
database.create_tables()
from learning import homework_flow as h
h.initialize()
uid=database.add_telegram_user(10001,'stage2','Иван',10,'SCHOOL','PHYSICS')
did=h._new_draft(90001,uid,None)
d=h._draft(did); assert h._progress(d)==0
h._touch(did,description='Решить задачи по закону Ома'); assert h._progress(h._draft(did))==20
h._touch(did,topic_grade=8,topic_subject='PHYSICS',topic_key='CURRENT'); assert h._progress(h._draft(did))==40
h._touch(did,formula_decision=0); assert h._progress(h._draft(did))==60
h._touch(did,deadline='NO_DEADLINE'); assert h._progress(h._draft(did))==80
h._touch(did,review_ready=1); assert h._progress(h._draft(did))==100
assert h._topic_title(8,'PHYSICS','CURRENT')
os.unlink(path)
print('STAGE2 HOMEWORK SELFTEST: OK')
