"""Original brief placement screens; task bands are editorial, not certification."""
from copy import deepcopy
from learning.entry_diagnostic import questions as english

# Three independent prompts per band, followed by one reading task per band.
DATA={
'de':[
 ('A1','Ich ___ aus Berlin.',['komme','kommt','kommen'],'komme'),
 ('A1','Wir haben ___ Hund.',['einen','ein','einem'],'einen'),
 ('A1','Wo ___ du?',['wohnst','wohnen','wohnt'],'wohnst'),
 ('A2','Gestern ___ ich meine Oma besucht.',['habe','bin','werde'],'habe'),
 ('A2','Ich fahre mit ___ Bus.',['dem','den','der'],'dem'),
 ('A2','Sie bleibt zu Hause, weil sie krank ___.',['ist','sein','hat'],'ist'),
 ('B1','Wenn ich mehr Zeit hätte, ___ ich öfter reisen.',['würde','werde','wurde'],'würde'),
 ('B1','Das ist die Frau, ___ ich gestern geholfen habe.',['der','die','den'],'der'),
 ('B1','Der Brief ___ gestern verschickt.',['wurde','würde','hat'],'wurde'),
 ('B2','___ des Regens fand das Konzert statt.',['Trotz','Wegen','Während'],'Trotz'),
 ('B2','Er tat so, als ___ er nichts davon.',['wüsste','weiß','wissen'],'wüsste'),
 ('B2','Je länger wir warten, ___ schwieriger wird es.',['desto','obwohl','indem'],'desto'),
],
'es':[
 ('A1','Yo ___ estudiante.',['soy','eres','son'],'soy'),
 ('A1','¿Dónde ___ tú?',['vives','vive','vivimos'],'vives'),
 ('A1','Tengo ___ hermana.',['una','un','unos'],'una'),
 ('A2','Ayer ___ al mercado.',['fui','voy','iré'],'fui'),
 ('A2','Este libro es más caro ___ ese.',['que','de','como'],'que'),
 ('A2','Cuando era niña, ___ en Sevilla.',['vivía','viviré','vivo'],'vivía'),
 ('B1','Espero que ___ bien.',['estés','estás','estar'],'estés'),
 ('B1','Si tuviera tiempo, ___ contigo.',['iría','iré','voy'],'iría'),
 ('B1','Busco el libro ___ me recomendaste.',['que','quien','donde'],'que'),
 ('B2','Si lo hubiera sabido, te ___ llamado.',['habría','habré','había'],'habría'),
 ('B2','No creo que ellos ___ razón.',['tengan','tienen','tener'],'tengan'),
 ('B2','Por mucho que ___, no consiguió convencerlos.',['insistió','insistir','insistiendo'],'insistió'),
],
'fa':[
 ('A1','معنی «آب» چیست؟',['вода','хлеб','дом'],'вода'),
 ('A1','من دانشجو ___.',['هستم','هستی','هستند'],'هستم'),
 ('A1','«سلام» یعنی چه؟',['привет','спасибо','до свидания'],'привет'),
 ('A2','دیروز به خانه ___.',['رفتم','می‌روم','خواهم رفت'],'رفتم'),
 ('A2','این کتاب ___ آن کتاب است.',['بهتر از','بهتر به','بهترین از'],'بهتر از'),
 ('A2','هر روز چای ___.',['می‌خورم','خوردم','خورده بودم'],'می‌خورم'),
 ('B1','اگر وقت داشته باشم، به تو ___ می‌کنم.',['کمک','کمک کرد','کمک کرده'],'کمک'),
 ('B1','وقتی رسیدم، او قبلاً ___ بود.',['رفته','می‌رود','برود'],'رفته'),
 ('B1','کتابی ___ خریدم جالب بود.',['که','اما','اگر'],'که'),
 ('B2','کاش دیروز به من ___ بودی.',['گفته','بگویی','می‌گویی'],'گفته'),
 ('B2','با اینکه خسته بود، به کارش ___ داد.',['ادامه','ادامه دادن','ادامه‌ای'],'ادامه'),
 ('B2','این گزارش باید تا فردا آماده ___ باشد.',['شده','کرده','می‌شود'],'شده'),
]}
READING={
'de':[
 ('Anna arbeitet heute nicht. Sie besucht ihre Mutter.','Wen besucht Anna?',['Ihre Mutter.','Ihren Chef.','Ihren Lehrer.'],'Ihre Mutter.'),
 ('Der Zug fährt um zehn. Lea kommt um halb zehn zum Bahnhof, um noch eine Fahrkarte zu kaufen.','Warum kommt Lea früher?',['Sie braucht eine Fahrkarte.','Der Zug fährt früher.','Sie arbeitet dort.'],'Sie braucht eine Fahrkarte.'),
 ('Das Büro bietet zwei Arbeitsschichten an. Eltern wählen oft die frühe Schicht, andere die späte. Beide bleiben bestehen.','Warum gibt es beide Schichten?',['Die Bedürfnisse unterscheiden sich.','Alle wollen spät arbeiten.','Es gibt keine Nachfrage.'],'Die Bedürfnisse unterscheiden sich.'),
 ('Nach Einführung eines neuen Tarifs sank der Stromverbrauch. Gleichzeitig war der Winter milder. Die Daten erlauben keine eindeutige Zuordnung.','Was lässt sich daraus schließen?',['Die Ursache ist nicht eindeutig.','Nur der Tarif war entscheidend.','Das Wetter hatte keinen Einfluss.'],'Die Ursache ist nicht eindeutig.'),
],
'es':[
 ('Me llamo Ana. Vivo en Madrid con mi hermano.','¿Con quién vive Ana?',['Con su hermano.','Con su madre.','Sola.'],'Con su hermano.'),
 ('La tienda abre a las nueve. Hoy Luis llegó a las ocho y media y tuvo que esperar.','¿Por qué esperó Luis?',['La tienda estaba cerrada.','No tenía dinero.','Había perdido el autobús.'],'La tienda estaba cerrada.'),
 ('El museo ofrece visitas por la mañana y por la tarde. Mantiene ambos horarios porque atraen a públicos diferentes.','¿Por qué mantiene ambos horarios?',['Se adaptan a distintas personas.','Nadie va por la mañana.','Todas las entradas son gratis.'],'Se adaptan a distintas personas.'),
 ('Los participantes durmieron mejor tras reducir el uso de pantallas, pero también hicieron más ejercicio. No hubo grupo de comparación.','¿Qué conclusión es prudente?',['No se ha aislado la causa de la mejora.','Las pantallas son la única causa.','El ejercicio no influye.'],'No se ha aislado la causa de la mejora.'),
],
'fa':[
 ('من سارا هستم. در تهران زندگی می‌کنم.','سارا کجا زندگی می‌کند؟',['تهران','شیراز','تبریز'],'تهران'),
 ('علی هر روز با اتوبوس به دانشگاه می‌رود، اما امروز چون دیر بیدار شد، تاکسی گرفت.','چرا علی امروز تاکسی گرفت؟',['دیر بیدار شد.','اتوبوس خراب شد.','دانشگاه تعطیل بود.'],'دیر بیدار شد.'),
 ('کتابخانه ساعت کاری خود را افزایش داد. دانشجویان شاغل از ساعت‌های عصر استفاده کردند و دیگران صبح آمدند.','چرا ساعت‌های مختلف مفید بودند؟',['نیازهای مراجعه‌کنندگان متفاوت بود.','همه صبح می‌آمدند.','کتابخانه خالی بود.'],'نیازهای مراجعه‌کنندگان متفاوت بود.'),
 ('پس از تغییر تعرفه، مصرف برق کاهش یافت. با این حال، هوا نیز گرم‌تر شده بود و نیاز به گرمایش کمتر بود.','کدام نتیجه قابل دفاع است؟',['علت کاهش مصرف هنوز روشن نیست.','تعرفه تنها علت بود.','هوا هیچ تأثیری نداشت.'],'علت کاهش مصرف هنوز روشن نیست.'),
]}


def questions(language,keys=False):
    if language=='en':return english(keys)
    if language not in DATA:raise ValueError('invalid_language')
    rows=[{'id':f'g{i}','band':band,'skill':'grammar','prompt':prompt,'options':options,'answer':answer}
          for i,(band,prompt,options,answer) in enumerate(DATA[language])]
    rows += [{'id':f'r{i}','band':band,'skill':'reading','passage':passage,'prompt':prompt,'options':options,'answer':answer}
             for i,(band,(passage,prompt,options,answer)) in enumerate(zip(('A1','A2','B1','B2'),READING[language]))]
    if not keys:
        for row in rows:row.pop('answer')
    return deepcopy(rows)


def assess(language,answers):
    rows=questions(language,True)
    if not isinstance(answers,dict) or set(answers)!={q['id'] for q in rows}:raise ValueError('diagnostic_incomplete')
    scores={band:{'correct':0,'total':0} for band in ('A1','A2','B1','B2')}
    for q in rows:
        value=answers[q['id']]
        if not isinstance(value,str) or value not in q['options']+['unknown']:raise ValueError('diagnostic_incomplete')
        scores[q['band']]['total']+=1;scores[q['band']]['correct']+=value==q['answer']
    band='A0'
    for b,s in scores.items():
        if s['correct']/s['total']<.75:break
        band=b
    return {'working_band':band,'scores':scores,'correct':sum(s['correct'] for s in scores.values()),'total':len(rows),
            'note':'Предварительный маршрут по коротким заданиям на чтение и грамматику. Аудирование, речь, письмо и уровень C1 этим тестом не подтверждаются.'}
