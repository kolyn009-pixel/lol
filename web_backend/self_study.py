"""Private teacher learning records; independent of pupils, lessons and billing."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import re
import unicodedata
from uuid import UUID

from database import connect
from learning.language_program import LANGUAGES, ROADMAP, RESOURCES, catalogue, lesson


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ensure_schema():
    conn=connect()
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS personal_study_profiles (
          owner_id INTEGER PRIMARY KEY, daily_minutes INTEGER NOT NULL DEFAULT 120,
          settings TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS personal_study_attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL,
          request_id TEXT NOT NULL, lesson_id TEXT NOT NULL, language TEXT NOT NULL,
          answers TEXT NOT NULL, correct INTEGER NOT NULL, total INTEGER NOT NULL,
          feedback TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(owner_id,request_id));
        CREATE INDEX IF NOT EXISTS idx_personal_study_attempts
          ON personal_study_attempts(owner_id,language,lesson_id,id);
        CREATE TABLE IF NOT EXISTS personal_study_drafts (
          owner_id INTEGER NOT NULL, lesson_id TEXT NOT NULL,
          answers TEXT NOT NULL, updated_at TEXT NOT NULL,
          PRIMARY KEY(owner_id,lesson_id));
        ''')
        conn.commit()
    finally:
        conn.close()


def _language(value):
    if value not in LANGUAGES:
        raise ValueError('invalid_language')
    return value


def normalise(value):
    value=unicodedata.normalize('NFKC',str(value)).casefold()
    value=value.replace('ي','ی').replace('ك','ک').replace('\u200c',' ')
    value=''.join(c for c in value if not unicodedata.category(c).startswith(('P','M')))
    return ' '.join(value.split())


def profile(owner_id):
    ensure_schema();conn=connect()
    try:
        row=conn.execute('SELECT * FROM personal_study_profiles WHERE owner_id=?',(owner_id,)).fetchone()
        daily=row['daily_minutes'] if row else (60 if owner_id<0 else 120)
        if owner_id<0 and daily not in (60,90,120):daily=120
        settings=json.loads(row['settings']) if row else {}
        codes=('en','es') if owner_id<0 else ('en','de','fa')
        allocation={'en':80,'de':25,'fa':15} if daily==120 else {'en':120,'de':40,'fa':20}
        if owner_id<0:allocation={60:{'en':45,'es':15},90:{'en':70,'es':20},120:{'en':95,'es':25}}[daily]
        base={'daily_minutes':daily,'languages':{
            code:{**spec, **({'start':'Нужна диагностика','goal':'B2 · общение и самостоятельное использование','target_date':'2027-05-01'} if owner_id<0 and code=='en' else {}), **settings.get(code,{}),'minutes':allocation[code]}
            for code,spec in LANGUAGES.items() if code in codes}}
        from web_backend.self_study_preferences import customise_profile
        return customise_profile(owner_id,base)
    finally:
        conn.close()


def save_profile(owner_id,data):
    daily=data.get('daily_minutes')
    from web_backend.self_study_preferences import MINUTES,stored
    allowed=MINUTES if stored(owner_id) else ((60,90,120) if owner_id<0 else (120,180))
    if type(daily) is not int or daily not in allowed:
        raise ValueError('invalid_daily_minutes')
    dates=data.get('target_dates',{})
    if not isinstance(dates,dict) or set(dates)-set(LANGUAGES):
        raise ValueError('invalid_target_dates')
    # Validate the entire request before mutating the existing profile.
    settings={}
    current=profile(owner_id)
    for code in current['languages']:
        raw=dates.get(code,current['languages'][code]['target_date'])
        if raw=='' and current.get('preferences'):
            settings[code]={'target_date':''};continue
        if not isinstance(raw,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):
            raise ValueError('invalid_target_date')
        parsed=date.fromisoformat(raw)
        if not date(2026,1,1)<=parsed<=date(2036,12,31):
            raise ValueError('invalid_target_date')
        settings[code]={'target_date':raw}
    conn=connect()
    try:
        conn.execute('''INSERT INTO personal_study_profiles VALUES(?,?,?,?)
          ON CONFLICT(owner_id) DO UPDATE SET daily_minutes=excluded.daily_minutes,
          settings=excluded.settings,updated_at=excluded.updated_at''',
          (owner_id,daily,json.dumps(settings,ensure_ascii=False),now()))
        conn.commit()
    finally:
        conn.close()
    return profile(owner_id)


def overview(owner_id):
    p=profile(owner_id);conn=connect()
    try:
        attempts=[dict(x) for x in conn.execute('''SELECT id,lesson_id,language,correct,total,created_at
          FROM personal_study_attempts WHERE owner_id=? ORDER BY id''',(owner_id,))]
        draft_ids=[x['lesson_id'] for x in conn.execute('SELECT lesson_id FROM personal_study_drafts WHERE owner_id=?',(owner_id,))]
    finally:
        conn.close()
    courses=catalogue()
    roadmap=ROADMAP
    if owner_id<0 and not p.get('preferences'):
        from learning.beginner_languages import units as basics
        from web_backend.self_study_placement import result as placement_result
        diagnostic=placement_result(owner_id,'en')
        band=diagnostic['working_band'] if diagnostic else None
        foundation=basics('en')
        start=0 if band in (None,'A0','A1') else 3 if band=='A2' else 6
        from learning.intensive_program import additional
        english=foundation[start:]+courses['en'][:8]+[x for x in additional('en') if x['band']=='B2']
        courses={'en':english,'es':basics('es')}
        courses={code:[{key:item[key] for key in ('id','number','title','minutes')} for item in items] for code,items in courses.items()}
        roadmap={
          'en':[['После диагностики','Восстановить нужную базу','Точка старта по чтению и грамматике; отдельно проверить речь и аудирование.'],
                ['До февраля','Укрепить A2–B1','Короткие диалоги, рассказы о событиях, понимание новых записей.'],
                ['Март–апрель','Работать над B2','Обсуждение мнений, аргументация, новые материалы и контроль каждые четыре недели.']],
          'es':[['Первые недели','Звуки и знакомство','Приветствие, имя, простые вопросы; слушать образцы носителей.'],
                ['Далее до мая','Бытовая база','Еда, время, дорога, рассказ о себе. Цель B2 относится к английскому.']]}
        p['diagnostic']=diagnostic
        p['diagnostic_required']=diagnostic is None
        p['languages']['en']['start']=('Рабочий ориентир '+band+' · грамматика/чтение') if band else 'Нужна диагностика'

    personal_resources=None
    if p.get('preferences'):
        from web_backend.self_study_preferences import adapt
        courses,roadmap,personal_resources=adapt(owner_id,p,attempts)
    for code,items in courses.items():
        for item in items:
            records=[a for a in attempts if a['lesson_id']==item['id']]
            item['attempt_count']=len(records)
            item['first']=records[0] if records else None
            item['latest']=records[-1] if records else None
            item['passed']=bool(records and records[-1]['correct']/records[-1]['total']>=0.75)
            item['draft']=item['id'] in draft_ids
        remaining=[i for i in items if not i['passed']]
        p['languages'][code]['next_lesson']=(remaining or items)[0]['id']
        p['languages'][code]['completed']=sum(i['passed'] for i in items)
        p['languages'][code]['total']=len(items)
    return {'owner_id':int(owner_id),'profile':p,'courses':courses,'roadmap':roadmap,
            'resources':personal_resources if personal_resources is not None else ([r for r in RESOURCES if r['language'] in p['languages'] and r['id'] not in ('landman','schwarzes-gold','billion-dollar-code')] if owner_id<0 else RESOURCES),'history':list(reversed(attempts[-30:])),
            'measurement_note':'Процент — результат конкретных заданий. Повторные попытки учитываются отдельно. Это не оценка CEFR.',
            'release_stage':2}


def _answers(data,item,complete=False):
    values=data.get('answers')
    if not isinstance(values,dict) or set(values)-{q['id'] for q in item['checks']}:
        raise ValueError('invalid_answers')
    result={}
    for key,value in values.items():
        if not isinstance(value,str) or len(value)>1000:
            raise ValueError('invalid_answers')
        result[key]=value.strip()
    if complete and any(not result.get(q['id']) for q in item['checks']):
        raise ValueError('answer_all_questions')
    return result


def get_lesson(owner_id,lesson_id):
    item=lesson(lesson_id)
    ensure_schema();conn=connect()
    try:
        row=conn.execute('SELECT answers,updated_at FROM personal_study_drafts WHERE owner_id=? AND lesson_id=?',
                         (owner_id,lesson_id)).fetchone()
        item['draft']=json.loads(row['answers']) if row else {}
        item['draft_saved_at']=row['updated_at'] if row else None
        return item
    finally:
        conn.close()


def save_draft(owner_id,data):
    item=lesson(data.get('lesson_id'));answers=_answers(data,item)
    ensure_schema();conn=connect()
    try:
        stamp=now()
        conn.execute('''INSERT INTO personal_study_drafts VALUES(?,?,?,?)
          ON CONFLICT(owner_id,lesson_id) DO UPDATE SET answers=excluded.answers,updated_at=excluded.updated_at''',
          (owner_id,item['id'],json.dumps(answers,ensure_ascii=False),stamp))
        conn.commit();return {'status':'saved','saved_at':stamp}
    finally:
        conn.close()


def submit(owner_id,data):
    item=lesson(data.get('lesson_id'),include_keys=True)
    answers=_answers(data,item,complete=True)
    request_id=data.get('request_id')
    try:
        if not isinstance(request_id,str):raise ValueError()
        UUID(request_id)
    except (ValueError,AttributeError):
        raise ValueError('invalid_request_id') from None
    ensure_schema();conn=connect()
    try:
        # Serialise retries: lost HTTP responses cannot create extra attempts.
        conn.execute('BEGIN IMMEDIATE')
        previous=conn.execute('SELECT * FROM personal_study_attempts WHERE owner_id=? AND request_id=?',
                              (owner_id,request_id)).fetchone()
        if previous:
            if previous['lesson_id']!=item['id'] or json.loads(previous['answers'])!=answers:
                raise ValueError('request_conflict')
            return json.loads(previous['feedback'])
        results=[]
        for question in item['checks']:
            accepted=question['answers']
            correct=normalise(answers[question['id']]) in {normalise(a) for a in accepted}
            results.append({'id':question['id'],'prompt':question['prompt'],
                            'submitted':answers[question['id']],'correct':correct,
                            'expected':accepted[0],'explanation':question['explanation']})
        count=sum(x['correct'] for x in results);total=len(results)
        number=conn.execute('SELECT COUNT(*) FROM personal_study_attempts WHERE owner_id=? AND lesson_id=?',
                            (owner_id,item['id'])).fetchone()[0]+1
        response={'lesson_id':item['id'],'correct':count,'total':total,'passed':count/total>=.75,
                  'attempt_number':number,'first_attempt':number==1,'results':results,
                  'note':'Первая попытка' if number==1 else 'Повтор знакомого материала; сравнивай отдельно от новых заданий.'}
        conn.execute('''INSERT INTO personal_study_attempts
          (owner_id,request_id,lesson_id,language,answers,correct,total,feedback,created_at)
          VALUES(?,?,?,?,?,?,?,?,?)''',(owner_id,request_id,item['id'],item['language'],
          json.dumps(answers,ensure_ascii=False),count,total,json.dumps(response,ensure_ascii=False),now()))
        conn.execute('DELETE FROM personal_study_drafts WHERE owner_id=? AND lesson_id=?',(owner_id,item['id']))
        conn.commit();return response
    except Exception:
        conn.rollback();raise
    finally:
        conn.close()

