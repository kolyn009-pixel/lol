"""Survey-based planning; preferences are not evidence of proficiency."""
from copy import deepcopy
from datetime import date
import hashlib
import json
from database import connect
from learning.language_program import LANGUAGES, RESOURCES, catalogue

TOPICS={'travel':'Путешествия','oil':'Нефть и энергетика','technology':'Технологии','science':'Наука','sport':'Спорт','history':'История','everyday':'Повседневная жизнь','art':'Искусство','nature':'Природа'}
GENRES={'drama':'Драма','comedy':'Комедия','adventure':'Приключения','documentary':'Документальное','romance':'Отношения'}
FORMATS={'speaking':'Разговор','video':'Видео и сериалы','reading':'Чтение','short':'Короткие задания'}
MINUTES=(15,20,30,45,60,90,120,150,180)

def valid_minutes(value,count=1):
    return type(value) is int and max(15,5*count)<=value<=180

LEVELS=('unknown','A0','A1','A2','B1','B2','C1')
TAGS={'landman':({'oil','everyday'},{'drama'},'adult'),
      'schwarzes-gold':({'oil','history'},{'drama'},'adult'),
      'billion-dollar-code':({'technology','science'},{'drama'},'adult'),
      'wots':({'travel','everyday'},{'documentary'},'all'),
      'great':({'art','history','travel'},{'documentary'},'all'),
      'nico':({'everyday','travel'},{'drama'},'all'),
      'jojo':({'everyday'},{'drama'},'adult'),
      'persian-online':({'everyday'},{'short'},'all')}
EXTRA=[
 {'id':'ministerio','language':'es','title':'El Ministerio del Tiempo','level':'Живая испанская речь · сложность по сцене','kind':'Приключения и история','url':'https://www.rtve.es/play/videos/el-ministerio-del-tiempo/','why':'Путешествия во времени и испанская история. Подходит для интереса к приключениям.','caution':'RTVE указывает 12+. Для начального уровня нужны короткие сцены с опорами. Доступ зависит от региона.'},
 {'id':'valeria','language':'es','title':'Valeria','level':'Живая испанская речь · сложность по сцене','kind':'Драма, отношения, комедия','url':'https://www.netflix.com/es/title/80212986','why':'Дружба, отношения и повседневные разговоры взрослых.','caution':'В испанском каталоге Netflix указано 18+. Доступ зависит от региона и подписки.'}]
TAGS.update({'ministerio':({'history','travel'},{'adventure'},'teen'),'valeria':({'everyday'},{'drama','comedy','romance'},'adult')})
for item in EXTRA:
    item.update(study_tasks=['Выбери сцену на 2–5 минут. Назови цели участников и перескажи своими словами.'],starter_terms=[],speaking_frames=[])


def ensure_schema():
    conn=connect()
    try:conn.execute('CREATE TABLE IF NOT EXISTS personal_study_preferences(owner_id INTEGER PRIMARY KEY,data TEXT NOT NULL)');conn.commit()
    finally:conn.close()


def stored(owner):
    ensure_schema();conn=connect()
    try:
        row=conn.execute('SELECT data FROM personal_study_preferences WHERE owner_id=?',(owner,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:conn.close()


def questionnaire(owner):
    return {'saved':stored(owner),'courses':[{'code':c,'name':v['name']} for c,v in LANGUAGES.items()],
            'topics':TOPICS,'genres':GENRES,'formats':FORMATS,'minutes':MINUTES,
            'note':'Выбирай интересы и удобный формат. Уровень по самооценке не заменяет диагностику.'}


def save(owner,data):
    codes=data.get('courses');priority=data.get('priority');minutes=data.get('daily_minutes')
    if not isinstance(codes,list) or not 1<=len(codes)<=4 or any(c not in LANGUAGES for c in codes) or len(set(codes))!=len(codes):raise ValueError('invalid_preferences')
    if priority not in codes or not valid_minutes(minutes,len(codes)):raise ValueError('invalid_preferences')
    age=data.get('age_group')
    if age not in ('child','teen','adult'):raise ValueError('invalid_preferences')
    clean={'courses':codes,'priority':priority,'daily_minutes':minutes,'age_group':age}
    for key,allowed in (('topics',TOPICS),('genres',GENRES),('formats',FORMATS)):
        values=data.get(key,[])
        if not isinstance(values,list) or len(values)>len(allowed) or any(not isinstance(x,str) or x not in allowed for x in values):raise ValueError('invalid_preferences')
        clean[key]=list(dict.fromkeys(values))
    goals=data.get('goals',{});levels=data.get('levels',{});dates=data.get('target_dates',{})
    if not all(isinstance(x,dict) for x in (goals,levels,dates)):raise ValueError('invalid_preferences')
    clean.update(goals={},levels={},target_dates={})
    for code in codes:
        goal=goals.get(code,'Уверенное общение');level=levels.get(code,'unknown');deadline=dates.get(code,'')
        if not isinstance(goal,str) or not 1<=len(goal.strip())<=160 or level not in LEVELS or not isinstance(deadline,str):raise ValueError('invalid_preferences')
        if deadline:
            try:parsed=date.fromisoformat(deadline)
            except ValueError:raise ValueError('invalid_preferences') from None
            if not date(2026,1,1)<=parsed<=date(2036,12,31):raise ValueError('invalid_preferences')
        clean['goals'][code]=goal.strip();clean['levels'][code]=level;clean['target_dates'][code]=deadline
    custom=data.get('custom_series',[])
    if not isinstance(custom,list) or len(custom)>5:raise ValueError('invalid_preferences')
    clean['custom_series']=[]
    for item in custom:
        if not isinstance(item,dict) or item.get('language') not in codes:raise ValueError('invalid_preferences')
        title=item.get('title')
        if not isinstance(title,str) or not 1<=len(title.strip())<=120:raise ValueError('invalid_preferences')
        clean['custom_series'].append({'title':title.strip(),'language':item['language']})
    from web_backend.self_study import ensure_schema as core_schema,now
    core_schema();ensure_schema();conn=connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT settings FROM personal_study_profiles WHERE owner_id=?',(owner,)).fetchone()
        settings=json.loads(row[0]) if row else {}
        for code in codes:settings.pop(code,None)
        conn.execute('INSERT INTO personal_study_profiles VALUES(?,?,?,?) ON CONFLICT(owner_id) DO UPDATE SET daily_minutes=excluded.daily_minutes,settings=excluded.settings,updated_at=excluded.updated_at',(owner,minutes,json.dumps(settings),now()))
        conn.execute('INSERT INTO personal_study_preferences VALUES(?,?) ON CONFLICT(owner_id) DO UPDATE SET data=excluded.data',(owner,json.dumps(clean,ensure_ascii=False)));conn.commit()
    finally:conn.close()
    return clean


def customise_profile(owner,base):
    cfg=stored(owner)
    count=len(cfg['courses']) if cfg else len(base['languages'])
    base['budget_min_minutes']=max(15,5*count)
    base['budget_max_minutes']=180
    base['budget_options']=[n for n in MINUTES if n>=base['budget_min_minutes']]
    if not cfg:return base
    # The ordinary profile endpoint can change the budget after the survey.
    conn=connect()
    try:row=conn.execute('SELECT daily_minutes,settings FROM personal_study_profiles WHERE owner_id=?',(owner,)).fetchone()
    finally:conn.close()
    minutes=row[0] if row and valid_minutes(row[0],len(cfg['courses'])) else cfg['daily_minutes']
    codes=cfg['courses'];allocation={c:minutes//len(codes) for c in codes}
    if len(codes)>1:
        priority_minutes=min(minutes-5*(len(codes)-1),max(minutes//len(codes),round(minutes*.6)))
        other=(minutes-priority_minutes)//(len(codes)-1)
        allocation={c:other for c in codes};allocation[cfg['priority']]=minutes-other*(len(codes)-1)
    else:allocation[codes[0]]=minutes
    cfg=deepcopy(cfg);cfg['daily_minutes']=minutes
    overrides=json.loads(row['settings']) if row else {}
    base['preferences']=cfg;base['daily_minutes']=minutes
    base['languages']={c:{**LANGUAGES[c],**base['languages'].get(c,{}),'goal':cfg['goals'][c],
                         'start':'Уровень не проверен' if cfg['levels'][c]=='unknown' else cfg['levels'][c]+' · самооценка',
                         'target_date':overrides.get(c,{}).get('target_date',cfg['target_dates'][c]),'minutes':allocation[c]} for c in codes}
    return base


def custom_resources(owner,cfg):
    result=[]
    for item in cfg.get('custom_series',[]):
        key=hashlib.sha256((str(owner)+':'+item['language']+':'+item['title']).encode()).hexdigest()[:20]
        result.append({'id':'custom-'+key,'language':item['language'],'title':item['title'],'level':'Твой выбор · сложность ещё не проверена',
          'kind':'Добавлено тобой','url':'','why':'Можно заниматься по уже любимому сериалу.','caution':'Название, озвучка и возрастной рейтинг не проверены. Для ребёнка выбор подтверждает взрослый.',
          'study_tasks':['Выбери понятную сцену на 2–5 минут.','Назови участников, их цели и конфликт.','Выбери до трёх выражений и перескажи сцену своими словами.'],
          'starter_terms':[],'speaking_frames':[]})
    return result


def owned_resource(owner,resource_id):
    cfg=stored(owner)
    if cfg:
        return next((x for x in custom_resources(owner,cfg) if x['id']==resource_id),None)


def adapt(owner,p,attempts):
    from learning.beginner_languages import units as basics
    from web_backend.self_study_placement import result as placement_result
    cfg=p['preferences'];all_courses=catalogue();all_courses['es']=basics('es')
    courses={};roadmap={}
    for code in cfg['courses']:
        level=cfg['levels'][code]
        diagnostic=placement_result(owner,code)
        if diagnostic:
            level=diagnostic['working_band']
            p['languages'][code]['start']='Рабочий ориентир '+level+' · чтение/грамматика'
            if level=='B2' and cfg['levels'][code]=='C1':
                level='C1'
                p['languages'][code]['start']='B2: стартовая проверка пройдена; C1 по самооценке — пробуем сложные задания, уровень не подтверждён'
        items=all_courses[code]
        if code=='en':
            start=0 if level in ('unknown','A0','A1') else 3 if level=='A2' else 6
            items=basics('en')[start:]+items
            if level=='C1':
                from learning.intensive_program import additional
                items=[x for x in additional('en') if x['band']=='C1']+all_courses['en'][8:12]
        if code=='de' and level in ('unknown','A0','A1','A2'):
            items=basics('de')+items
        if code=='de' and level=='C1':
            from learning.intensive_program import additional
            items=additional('de')
        courses[code]=[{k:item[k] for k in ('id','number','title','minutes')} for item in items]
        roadmap[code]=[['Точка старта',p['languages'][code]['start'],'Диагностика уточняет уровень; самооценка не подтверждает CEFR.'],
                       ['Ближайшие недели',cfg['goals'][code],'Короткие занятия по интересам, повторения и пересказ.'],
                       ['Каждые четыре недели','Проверить результат на новом материале','Знакомые повторы учитывать отдельно.']]
        p['languages'][code]['content_note']=('Есть шесть начальных модулей немецкого; переход от них к B1 ещё требует дополнительного материала. ' if code=='de' and level in ('A0','A1','A2','unknown') else '')+'Добавлен первый интенсивный блок с целями, речью, коротким письмом и переносом. Полный курс до целевого уровня ещё не сформирован.'
        if code=='es' and level in ('B1','B2','C1'):
            p['languages'][code]['content_note']='Испанские модули пока начальные: можно повторить основу, но для твоего стартового результата нужны новые материалы более высокого уровня. Это ещё не подходящий полный маршрут.'
        recent=[a for a in attempts if a['language']==code][-3:]
        accuracy=sum(a['correct'] for a in recent)/sum(a['total'] for a in recent) if recent else None
        p['languages'][code]['practice_focus']=('Снизь сложность: разбор примера и короткие ответы с опорой.' if accuracy is not None and accuracy<.6 else
           'Попробуй перенос: объясни новую ситуацию без подсказки.' if accuracy is not None and accuracy>=.85 else 'Чередуй новый материал и повторение ошибок.')
        p['languages'][code]['session_minutes']=min(15 if cfg['age_group']=='child' else 25,p['languages'][code]['minutes'])
        if 'short' in cfg['formats']:p['languages'][code]['session_minutes']=min(10,p['languages'][code]['session_minutes'])
        for chosen,text in (('speaking','Начни с короткого устного ответа с опорой.'),('video','Для практики используй короткую сцену и пересказ.'),('reading','После чтения объясни основную мысль своими словами.')):
            if chosen in cfg['formats']:p['languages'][code]['practice_focus']+=' '+text
    resources=[]
    for item in deepcopy(RESOURCES+EXTRA):
        if item['language'] not in cfg['courses']:continue
        topics,genres,age=TAGS.get(item['id'],(set(),set(),'adult'))
        if age=='adult' and cfg['age_group']!='adult':continue
        if age=='teen' and cfg['age_group']=='child':continue
        item['match_score']=2*len(set(cfg['topics'])&topics)+len(set(cfg['genres'])&genres)
        item['match_reason']='Совпадение с выбранными интересами и жанрами.' if item['match_score'] else 'Дополнительный материал на выбранном языке.'
        resources.append(item)
    resources.sort(key=lambda x:-x['match_score'])
    return courses,roadmap,custom_resources(owner,cfg)+resources
