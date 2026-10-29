"""Editorial learning sequences; completion is not CEFR certification."""
from copy import deepcopy

BANDS=('A1','A2','B1','B2','C1')

def ids(prefix,first,last):return [f'{prefix}-{n:02}' for n in range(first,last+1)]

MAP={
 'en':{'A1':ids('en0',1,3),'A2':ids('en0',4,6),'B1':ids('enb',1,3)+ids('en',1,4),
       'B2':ids('en',5,8)+ids('enx',1,3),'C1':ids('en',9,12)+ids('enx',4,6)},
 'de':{'A1':ids('de0',1,6),'A2':ids('deb',1,3),'B1':ids('de',1,4),'B2':ids('de',5,8),'C1':ids('dex',1,3)},
 'es':{'A1':ids('es',1,8)+ids('esx',1,3),'A2':ids('esb',1,3),'B1':ids('esb',4,6),'B2':ids('esb',7,9),'C1':ids('esb',10,12)},
 'fa':{'A1':ids('fa',1,8)+ids('fax',1,3),'A2':ids('fab',1,3),'B1':ids('fab',4,6),'B2':[],'C1':[]},
}
OBJECTIVES={
 'A1':['Представиться и задать простой вопрос.','Попросить повторить и подтвердить понимание.'],
 'A2':['Рассказать о событии и плане.','Уточнить условие и решить простую бытовую задачу.'],
 'B1':['Связно объяснить решение и его причины.','Сравнить варианты и поддержать разговор на знакомую тему.'],
 'B2':['Аргументировать с оговорками.','Отделить наблюдение от вывода и договориться об условиях.'],
 'C1':['Точно передать сложную позицию и ограничения.','Синтезировать разные доводы и ответить на возражение.'],
}

# Each transition uses a fresh passage that does not appear in its lesson block.
GATES={
'en':{
 'A1':('My name is Eva. I live near the park. I work in a shop. On Sunday I visit my brother. He lives near the station.',
        ('Who does Eva visit on Sunday?','Her brother.','Her teacher.'),('Where does her brother live?','Near the station.','In the shop.'),
        ('Возле парка: ___ the park.','near'),('В воскресенье: ___ Sunday.','on')),
 'A2':('Yesterday Noah missed his usual train. He took a later one and called the office. Tomorrow he is going to leave home earlier. He has already put his ticket in his bag.',
        ('What did Noah do after missing the train?','Took a later train and called the office.','Went home without calling.'),('What is his plan?','Leave home earlier.','Stop using trains.'),
        ('Вчера он опоздал: Yesterday he ___ his train.','missed'),('Собирается выйти: is ___ to leave.','going')),
 'B1':('A student chose a weekend workshop because weekday classes conflicted with work. The workshop offered less individual feedback, so she arranged to compare notes with a classmate afterwards. She will review the choice after two meetings rather than commit for a year.',
        ('Why choose the weekend?','Weekday classes conflicted with work.','It promised unlimited feedback.'),('How will she address a limitation?','Compare notes with a classmate.','Avoid reviewing her work.'),
        ('Сравнить записи: ___ notes.','compare'),('Пересмотреть выбор: ___ the choice.','review')),
 'B2':('A company introduced quiet working hours. Staff reported better concentration, but deadlines also became less demanding during the trial. The report recommends extending the trial and measuring both workload and completed tasks before attributing the change to quiet hours alone.',
        ('What complicates the conclusion?','Workload changed during the trial.','No staff gave feedback.'),('What is recommended?','Measure workload and completed tasks.','Assume quiet hours caused everything.'),
        ('Прежде чем приписывать: ___ attributing the change.','before'),('Продлить пробный период: ___ the trial.','extending')),
 'C1':('A proposal to digitise an archive is presented as a choice between access and preservation. This framing obscures questions about selection, maintenance and the cost of sustaining both formats. A limited pilot could clarify these trade-offs, provided that its criteria distinguish public demand from the ease of producing attractive usage figures.',
        ('What does the text challenge?','An oversimplified framing of the decision.','The value of any public access.'),('What should evaluation distinguish?','Public demand from convenient usage figures.','Preservation from the need for any criteria.'),
        ('Компромиссы: these trade-___.','offs'),('При условии что: ___ that its criteria distinguish.','provided')),
},
'de':{
 'A1':('Ich heiße Emil und wohne in Hamburg. Meine Schwester wohnt in Bremen. Am Samstag besuche ich sie. Wir trinken zusammen Tee und gehen in den Park.',
        ('Wann besucht Emil seine Schwester?','Am Samstag.','Am Montag.'),('Was trinken sie?','Tee.','Kaffee.'),
        ('Я живу: Ich ___ in Hamburg.','wohne'),('В субботу: ___ Samstag.','Am')),
 'A2':('Gestern wollte Nora nach der Arbeit einkaufen. Der Laden war schon geschlossen. Deshalb ist sie heute früher losgegangen. Sie hat eine Liste mitgenommen, damit sie nichts vergisst.',
        ('Warum konnte Nora gestern nicht einkaufen?','Der Laden war geschlossen.','Sie hatte keine Liste.'),('Was macht sie heute anders?','Sie geht früher los.','Sie geht erst nachts.'),
        ('Уже закрыт: ___ geschlossen.','schon'),('Она взяла список: eine Liste ___.','mitgenommen')),
 'B1':('Paul möchte einen Sprachkurs besuchen. Der Abendkurs liegt näher, bietet aber wenig Gesprächszeit. Deshalb entscheidet er sich für einen Wochenendkurs. Nach zwei Terminen will er prüfen, ob die längere Fahrt durch mehr Übung ausgeglichen wird.',
        ('Warum wählt Paul den Wochenendkurs?','Er erwartet mehr Gesprächsübung.','Die Fahrt ist kürzer.'),('Wann will er die Wahl überprüfen?','Nach zwei Terminen.','Erst nach einem Jahr.'),
        ('Проверить выбор: die Wahl ___.','überprüfen'),('Разговорная практика: mehr ___.','Gesprächsübung')),
 'B2':('Nach einer Änderung der Arbeitszeiten berichten Beschäftigte von weniger Stress. Gleichzeitig wurde die Zahl der Projekte verringert. Der Bericht empfiehlt daher, beide Veränderungen getrennt zu untersuchen, bevor die neuen Arbeitszeiten als alleinige Ursache gelten.',
        ('Was erschwert die Zuordnung?','Auch die Zahl der Projekte wurde verringert.','Es gab keine Veränderung.'),('Was empfiehlt der Bericht?','Beide Veränderungen getrennt untersuchen.','Nur die Arbeitszeiten betrachten.'),
        ('Единственная причина: die ___ Ursache.','alleinige'),('Поэтому: Der Bericht empfiehlt ___.','daher')),
 'C1':('Die Diskussion über ein digitales Archiv wird häufig auf Reichweite und Kosten verengt. Dabei bleibt offen, welche Inhalte erschlossen und wie langfristige Pflegekosten getragen werden sollen. Ein Pilotprojekt wäre nur dann aussagekräftig, wenn seine Kriterien vorab festgelegt würden und bloße Zugriffszahlen nicht mit tatsächlichem Nutzen gleichgesetzt würden.',
        ('Was kritisiert der Text?','Eine verengte Betrachtung des Vorhabens.','Jede Form digitaler Archive.'),('Was darf nicht gleichgesetzt werden?','Zugriffszahlen und tatsächlicher Nutzen.','Vorab festgelegte Kriterien und Planung.'),
        ('Заранее: ___ festgelegt.','vorab'),('Приравнивать: mit Nutzen ___ werden.','gleichgesetzt')),
},
'es':{
 'A1':('Me llamo Lucía. Vivo cerca de la estación. Trabajo por la mañana y estudio por la tarde. El domingo visito a mi hermana. A las seis tomamos un café.',
        ('¿Cuándo estudia Lucía?','Por la tarde.','Por la mañana.'),('¿A quién visita el domingo?','A su hermana.','A su profesora.'),
        ('Я живу: ___ cerca de la estación.','Vivo'),('Днём: por la ___.','tarde')),
 'A2':('Ayer Clara perdió el autobús y llegó tarde a una reunión. Llamó para avisar y acordó otra hora. Mañana va a salir antes de casa y llevará la dirección escrita en una libreta.',
        ('¿Qué hizo Clara al llegar tarde?','Llamó para avisar.','No habló con nadie.'),('¿Qué piensa cambiar mañana?','Salir antes.','Cancelar todas las reuniones.'),
        ('Вчера позвонила: Ayer ___.','llamó'),('До выхода: ___ de salir.','antes')),
 'B1':('Diego eligió un curso de fin de semana porque trabajaba por las tardes. El viaje era más largo, pero había más tiempo para conversar. Decidió probar dos clases y valorar después si el esfuerzo merecía la pena. No quería comprometerse durante un año sin conocer el grupo.',
        ('¿Por qué eligió el fin de semana?','Trabajaba por las tardes.','El viaje era más corto.'),('¿Cómo evaluará su decisión?','Probará dos clases antes de decidir.','Pagará un año sin conocer el grupo.'),
        ('Стоило усилий: merecía la ___.','pena'),('Обязаться: No quería ___.','comprometerse')),
 'B2':('Tras cambiar el horario, el equipo declaró sentirse menos cansado. Sin embargo, durante el mismo periodo se redujo la carga de trabajo. Antes de atribuir la mejora al horario, el informe propone comparar periodos con cargas semejantes y recoger datos sobre tareas completadas.',
        ('¿Qué limita la conclusión?','También cambió la carga de trabajo.','No se cambió el horario.'),('¿Qué comparación propone?','Periodos con cargas semejantes.','Solo opiniones favorables.'),
        ('Рабочая нагрузка: la ___ de trabajo.','carga'),('Прежде чем приписывать: ___ de atribuir.','antes')),
 'C1':('Presentar la digitalización de un archivo como una oposición entre acceso y conservación simplifica en exceso el problema. La selección de contenidos y el mantenimiento a largo plazo merecen criterios propios. Un proyecto piloto sería informativo siempre que no se confundieran las cifras de visitas con la utilidad efectiva para públicos diversos.',
        ('¿Qué cuestiona el texto?','Una oposición demasiado simple.','La necesidad de conservar archivos.'),('¿Qué no debe confundirse?','Las visitas y la utilidad efectiva.','El mantenimiento y los criterios propios.'),
        ('В долгосрочной перспективе: a largo ___.','plazo'),('При условии что: siempre ___.','que')),
},
'fa':{
 'A1':('من مینا هستم. در تهران زندگی می‌کنم. صبح کار می‌کنم و عصر فارسی می‌خوانم. روز جمعه به خانه خواهرم می‌روم. با هم چای می‌خوریم.',
        ('Когда Мина учится?','Вечером.','Утром.'),('К кому она идёт в пятницу?','К сестре.','К учителю.'),
        ('Утро: ___.','صبح'),('Сестра: ___.','خواهر')),
 'A2':('دیروز اتوبوس را از دست دادم و دیر به کلاس رسیدم. به معلم پیام دادم و علت را توضیح دادم. فردا می‌خواهم زودتر از خانه بیرون بروم. آدرس کلاس را هم در دفترم نوشته‌ام.',
        ('Что произошло вчера?','Человек опоздал на автобус.','Класс отменили.'),('Что собирается изменить завтра?','Выйти из дома раньше.','Больше не учиться.'),
        ('Раньше: ___.','زودتر'),('Завтра: ___.','فردا')),
 'B1':('سارا کلاس آخر هفته را انتخاب کرد، چون عصرها کار می‌کرد. راه این کلاس دورتر بود، اما فرصت بیشتری برای گفت‌وگو داشت. تصمیم گرفت بعد از دو جلسه بررسی کند که آیا این رفت‌وآمد ارزشش را دارد. نمی‌خواست بدون شناخت گروه، برای یک سال ثبت‌نام کند.',
        ('Почему выбран курс выходного дня?','Вечером Сара работала.','Он был ближе.'),('Когда она оценит выбор?','После двух занятий.','Только через год.'),
        ('После двух занятий: بعد از دو ___.','جلسه'),('Возможность для разговора: فرصت برای ___.','گفت‌وگو')),
}}


def stages(language):
    if language not in MAP:raise ValueError('invalid_language')
    from learning.language_program import lesson
    return [{'band':band,'objectives':OBJECTIVES[band],
             'lessons':[{k:item[k] for k in ('id','number','title','minutes')} for item in map(lesson,MAP[language][band])],
             'coverage':'starter_block' if MAP[language][band] else 'missing',
             'coverage_note':'Первый последовательный блок, не полный объём уровня. Аудирование и речь требуют отдельных проверок.' if MAP[language][band] else 'Материалы этой ступени ещё не готовы. Автоматического перехода здесь нет.'}
            for band in BANDS]


def challenge(language,band,keys=False):
    try:passage,q0,q1,d0,d1=GATES[language][band]
    except (KeyError,TypeError):raise ValueError('route_materials_missing') from None
    checks=[]
    for i,(prompt,answer,other) in enumerate((q0,q1)):
        checks.append({'id':f'q{i}','kind':'choice','prompt':prompt,'options':[answer,other] if i%2 else [other,answer],'answers':[answer]})
    for i,(prompt,answer) in enumerate((d0,d1)):
        checks.append({'id':f'd{i}','kind':'recall','prompt':prompt,'answers':[answer]})
    if not keys:
        for q in checks:q.pop('answers')
    return deepcopy({'language':language,'band':band,'passage':passage,'checks':checks,
        'note':'Новый текст для перехода внутри программы: чтение и языковые конструкции. Повтор будет тренировкой на знакомом. Это не экзамен CEFR и не проверка всех четырёх навыков.'})
