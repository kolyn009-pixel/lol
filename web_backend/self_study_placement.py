"""Private mandatory family entry checks. OWNER routes may opt in."""
from datetime import datetime,timedelta,timezone
import json
from zoneinfo import ZoneInfo
from database import connect
from learning.family_placement import questions,assess
from learning.language_program import LANGUAGES


def clock():return datetime.now(timezone.utc)


def ensure_schema():
    conn=connect()
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS personal_study_placement
          (owner_id INTEGER NOT NULL,language TEXT NOT NULL,answers TEXT NOT NULL,result TEXT NOT NULL,updated_at TEXT NOT NULL,
           PRIMARY KEY(owner_id,language))''');conn.commit()
    finally:conn.close()


def result(owner,language):
    if language not in LANGUAGES:raise ValueError('invalid_language')
    ensure_schema();conn=connect()
    try:row=conn.execute('SELECT result,updated_at FROM personal_study_placement WHERE owner_id=? AND language=?',(owner,language)).fetchone()
    finally:conn.close()
    if row:return {**json.loads(row[0]),'assessed_at':row['updated_at']}
    if language=='en':
        from web_backend.self_study_entry import result as previous
        old=previous(owner)
        if old:
            conn=connect()
            try:stamp=conn.execute('SELECT updated_at FROM personal_study_entry WHERE owner_id=?',(owner,)).fetchone()[0]
            finally:conn.close()
            return {**old,'language':'en','legacy':True,'assessed_at':stamp}
    return None


def recommendations(owner,language,output):
    from web_backend.self_study import profile
    p=profile(owner);minutes=p['languages'].get(language,{}).get('minutes',15)
    level=output['working_band'];next_band={'A0':'A1','A1':'A2','A2':'B1','B1':'B2','B2':'C1'}.get(level,'C1')
    weeks=4
    assessed=datetime.fromisoformat(output['assessed_at']) if output.get('assessed_at') else clock()
    review_date=assessed.astimezone(ZoneInfo('Europe/Moscow')).date()+timedelta(weeks=weeks)
    texts={'A0':'Представиться и провести простой диалог с опорами','A1':'Обсудить знакомую бытовую ситуацию','A2':'Пересказать короткую историю и объяснить планы','B1':'Объяснить мнение и поддержать разговор на знакомую тему','B2':'Разобрать сложный текст и защитить позицию с примерами'}
    return {'working_band':level,'suggested_next_band':next_band,'daily_minutes':minutes,
            'goal':texts.get(level,texts['B2']),'review_date':review_date.isoformat(),'review_due':clock().astimezone(ZoneInfo('Europe/Moscow')).date()>=review_date,
            'note':'Предлагаем цель на четыре недели. Следующий уровень — направление работы; срок достижения уточняется по новым заданиям и всем четырём навыкам.',
            'advanced_check_needed':level=='B2','course_choice':'Начни с выбранного языка; при малом бюджете сделай его главным, а остальные оставь для короткой практики.'}


def status(owner):
    from web_backend.self_study import profile
    p=profile(owner);results={code:result(owner,code) for code in p['languages']}
    pending=[code for code,value in results.items() if value is None] if owner<0 else []
    return {'required':owner<0,'pending':pending,'results':{c:{**r,'recommendation':recommendations(owner,c,r)} for c,r in results.items() if r},
            'note':'Перед обучением семьи нужна стартовая проверка каждого выбранного языка. Твой OWNER-аккаунт освобождён от обязательной проверки.'}


def require(owner,language):
    if owner<0 and result(owner,language) is None:raise ValueError('placement_required')


def get(owner,language):
    return {'language':language,'questions':questions(language),'result':result(owner,language),
            'note':'Без словаря. «Не знаю» — нормальный ответ. Тест выбирает стартовый маршрут, а не выдаёт сертификат. Результат может быть ниже или выше самооценки.'}


def submit(owner,data):
    language=data.get('language');answers=data.get('answers');out=assess(language,answers)
    # Preserve the established English route and its richer grammar/reading report.
    if language=='en':
        from web_backend.self_study_entry import submit as english_submit
        english_submit(owner,{'answers':answers})
    out.update(language=language,assessed_at=clock().isoformat())
    out['recommendation']=recommendations(owner,language,out)
    ensure_schema();conn=connect()
    try:
        conn.execute('''INSERT INTO personal_study_placement VALUES(?,?,?,?,?) ON CONFLICT(owner_id,language)
          DO UPDATE SET answers=excluded.answers,result=excluded.result,updated_at=excluded.updated_at''',
          (owner,language,json.dumps(answers),json.dumps(out,ensure_ascii=False),out['assessed_at']));conn.commit()
    finally:conn.close()
    return out
