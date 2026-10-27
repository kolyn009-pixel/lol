import json
from database import connect
from learning.entry_diagnostic import questions,assess


def ensure_schema():
    conn=connect()
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS personal_study_entry
          (owner_id INTEGER PRIMARY KEY,answers TEXT NOT NULL,result TEXT NOT NULL,updated_at TEXT NOT NULL)''');conn.commit()
    finally:conn.close()


def result(owner):
    ensure_schema();conn=connect()
    try:
        row=conn.execute('SELECT result FROM personal_study_entry WHERE owner_id=?',(owner,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:conn.close()


def get(owner):return {'questions':questions(),'result':result(owner),'note':'Около 15–20 минут. Без словаря; если не знаешь, выбери «Не знаю». Разговорную часть выполни отдельно.'}


def submit(owner,data):
    from web_backend.self_study import now
    answers=data.get('answers')
    if not isinstance(answers,dict) or set(answers)!={q['id'] for q in questions()}:raise ValueError('diagnostic_incomplete')
    # Explicit "unknown" counts as incorrect, rather than forcing a guess.
    checked={}
    for q in questions(True):
        value=answers[q['id']]
        if not isinstance(value,str) or value not in q['options']+['unknown']:raise ValueError('diagnostic_incomplete')
        checked[q['id']]=value if value!='unknown' else next(x for x in q['options'] if x!=q['answer'])
    output=assess(checked);ensure_schema();conn=connect()
    try:
        conn.execute('''INSERT INTO personal_study_entry VALUES(?,?,?,?) ON CONFLICT(owner_id)
          DO UPDATE SET answers=excluded.answers,result=excluded.result,updated_at=excluded.updated_at''',
          (owner,json.dumps(answers),json.dumps(output,ensure_ascii=False),now()));conn.commit()
    finally:conn.close()
    return output
