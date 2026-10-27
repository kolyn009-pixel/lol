"""Original practice blocks informed by LOA. Not an official Cambridge course.

Bands are editorial task targets, not certified proficiency or calibrated tests.
"""
from copy import deepcopy

# title, task band, original input, two comprehension items, two short drills,
# expressions, communicative transfer. No publisher text or TV dialogue copied.
DATA={
'en':[
 ('Negotiate a workable plan','B2',
  'Our study group wanted to meet three times a week, but two members worked evenings. Simply reducing the number of meetings would have helped them, yet it would also have removed practice time for everyone else. We agreed to keep one live meeting and exchange short recordings on the other days. After two weeks, we will check whether people actually respond to one another. The new plan is only useful if the recordings lead to a conversation rather than a collection of separate speeches.',
  [('What difficulty did the group face?','Some members worked in the evenings.','Nobody wanted to practise.'),('What will they check?','Whether recordings lead to interaction.','Whether the recordings are long enough to replace all conversation.')],
  [('Мы договорились оставить: We ___ keep one meeting.','agreed to','Agree to + infinitive.'),('А не отдельные речи: a conversation ___ separate speeches.','rather than','Rather than introduces the alternative being rejected.')],
  [('a workable plan','выполнимый план'),('exchange recordings','обмениваться записями'),('respond to one another','отвечать друг другу')],
  'Договорись о занятиях с человеком, у которого другое расписание. Предложи два варианта, попроси выбрать и уточни одно условие.'),
 ('Explain a delay without guessing','B2',
  'A delivery was expected on Tuesday, but it had not arrived by Wednesday morning. The customer blamed the driver. The coordinator explained that the parcel had reached a regional warehouse, but the tracking system did not show what happened afterwards. She promised to request an update by noon rather than promise a delivery time she could not confirm. The customer still wanted an answer immediately. She acknowledged the inconvenience and distinguished what was known from what still needed checking.',
  [('What did tracking confirm?','The parcel reached a regional warehouse.','The driver had lost the parcel.'),('What did the coordinator promise?','To request an update by noon.','That the parcel would arrive by noon.')],
  [('Она признала неудобство: She ___ the inconvenience.','acknowledged','Acknowledge recognises an issue without inventing a cause.'),('Что нужно проверить: what still ___ checking.','needed','Needed agrees with the past narrative.')],
  [('request an update','запросить уточнение'),('confirm a delivery time','подтвердить срок доставки'),('acknowledge the inconvenience','признать причинённые неудобства')],
  'Объясни задержку проекта: два известных факта, один неизвестный, следующий шаг и срок уточнения. Ответь на вопрос: “Can you guarantee it?”'),
 ('Compare evidence, not impressions','B2',
  'Two learners tried different vocabulary routines. One studied a long list on Sunday; the other reviewed a few expressions each day. At the end of the week, both recognised most expressions in a quiz. However, when asked to explain a new situation, they struggled to use them. This suggests that recognition and independent use should be checked separately. It does not prove that either routine is useless: the learners may need practice that connects expressions to their own experiences.',
  [('What could both learners do?','Recognise expressions in a quiz.','Use every expression in a new situation.'),('What is the justified recommendation?','Check recognition and independent use separately.','Stop reviewing vocabulary entirely.')],
  [('Это предполагает, что: This ___ that recognition is not enough.','suggests','Suggests expresses an interpretation, not proof.'),('По отдельности: Check the skills ___.','separately','Separately keeps different measures distinct.')],
  [('independent use','самостоятельное использование'),('a new situation','новая ситуация'),('connect to experience','связать с опытом')],
  'Сравни две учебные привычки. Укажи, что можно измерить, что результат не доказывает и какое новое задание ты бы предложил.'),
 ('Brief an engineering decision','C1',
  'An engineering team is considering two proposals for a monitoring project. The first is cheaper to install but relies on measurements that are collected less frequently. The second offers more detailed observations, although its maintenance requirements remain uncertain. Neither proposal should be described as the obvious winner before the purpose of the monitoring has been agreed. The briefing therefore separates the decision criteria, the available evidence and the unresolved assumptions. It also identifies which missing information could change the recommendation, instead of treating uncertainty as a reason to avoid any decision.',
  [('Why is there no obvious winner?','The monitoring purpose and criteria matter.','The second proposal is always safer.'),('What should the briefing identify?','Information that could change the recommendation.','A guarantee that every assumption is correct.')],
  [('Нерешённые предположения: the ___ assumptions.','unresolved','Unresolved marks an issue still requiring clarification.'),('Могла бы изменить: information that ___ change the recommendation.','could','Could signals a possible influence, not a guaranteed result.')],
  [('decision criteria','критерии решения'),('maintenance requirements','требования к обслуживанию'),('unresolved assumptions','непроверенные предположения')],
  'Дай двухминутный briefing о выборе учебного или исследовательского инструмента: критерии, компромисс, неопределённость, рекомендация. Это языковая задача, не инструкция по эксплуатации оборудования.'),
 ('Defend a research limitation','C1',
  'A candidate presents an exploratory study based on interviews with a small group of volunteers. An examiner argues that the findings cannot represent an entire profession. The candidate accepts this limitation but explains that representation was not the immediate purpose. The interviews were intended to identify questions for a later investigation. Nevertheless, this defence does not make every interpretation equally credible: the candidate still needs to explain how the interviews were analysed and which observations support the proposed categories. A modest claim can be useful, provided its limits and evidential basis are explicit.',
  [('What is the study intended to do?','Identify questions for later investigation.','Represent an entire profession statistically.'),('What must the candidate still explain?','The analysis and supporting observations.','Why a small sample removes the need for evidence.')],
  [('При условии, что: useful, ___ its limits are explicit.','provided','Provided can introduce a condition; provided that is also accepted.'),('Доказательная основа: its ___ basis.','evidential','Evidential concerns the evidence supporting a claim.')],
  [('exploratory study','поисковое исследование'),('a modest claim','ограниченное утверждение'),('evidential basis','доказательная основа')],
  'Ответь на возражение по исследованию. Признай справедливую часть, уточни цель и назови данные, которые нужны для обоснования вывода.'),
 ('Synthesize conflicting priorities','C1',
  'A proposal to extend a city library’s opening hours has attracted support from evening workers and criticism from staff concerned about scheduling. Supporters emphasise access, while critics question whether longer opening hours are the best use of a limited budget. These positions need not be reduced to a choice between caring about visitors and caring about employees. A useful response would compare demand at different times, staffing arrangements and the opportunity cost of other services. A trial could inform the decision, but only if its success criteria are specified before the results are known.',
  [('How should the disagreement be understood?','As competing priorities requiring evidence.','As proof that one side does not care about people.'),('When should success criteria be defined?','Before the trial results are known.','After choosing the most favourable results.')],
  [('Альтернативная стоимость: the ___ cost of other services.','opportunity','Opportunity cost refers to the value of an alternative forgone.'),('До того, как: ___ the results are known.','before','Before keeps the criteria independent of observed outcomes.')],
  [('competing priorities','конкурирующие приоритеты'),('staffing arrangements','организация работы персонала'),('success criteria','критерии успеха')],
  'Сначала нейтрально изложи две позиции. Затем предложи пробное решение и заранее назови три критерия его оценки.'),
],
'de':[
 ('Eine Entscheidung differenziert begründen','C1',
  'Eine Hochschule möchte mehr Lehrveranstaltungen aufzeichnen. Befürworter betonen, dass Studierende dadurch versäumte Inhalte nachholen können. Kritiker befürchten dagegen, dass die persönliche Beteiligung zurückgeht. Beide Seiten beziehen sich auf wichtige Ziele, doch aus ihren Argumenten folgt noch keine eindeutige Entscheidung. Zunächst müsste geklärt werden, welche Veranstaltungen sich für Aufzeichnungen eignen und wie diese tatsächlich genutzt werden. Eine zeitlich begrenzte Erprobung wäre sinnvoll, sofern vorher feststeht, woran ihr Erfolg gemessen wird.',
  [('Was fehlt für eine eindeutige Entscheidung?','Genauere Informationen über Eignung und Nutzung.','Die Zustimmung zu jeder Aufzeichnung.'),('Was ist bei einer Erprobung wichtig?','Vorher festgelegte Erfolgskriterien.','Ein Erfolg unabhängig von den Ergebnissen.')],
  [('При условии что: sinnvoll, ___ die Kriterien feststehen.','sofern','Sofern introduces a condition.'),('Измерить успех: woran der Erfolg ___ wird.','gemessen','Passiv: wird gemessen.')],
  [('versäumte Inhalte nachholen','восполнить пропущенный материал'),('persönliche Beteiligung','личное участие'),('zeitlich begrenzte Erprobung','ограниченное по времени испытание')],
  'Объясни выбор между двумя форматами обучения. Изложи аргументы обеих сторон, оговорку и критерии пробного решения.'),
 ('Eine scheinbar klare Aussage prüfen','C1',
  'In einer Befragung geben viele Beschäftigte an, im Homeoffice konzentrierter zu arbeiten. Daraus wird gelegentlich geschlossen, dass Homeoffice grundsätzlich produktiver sei. Diese Schlussfolgerung geht jedoch über die vorliegenden Angaben hinaus. Die Befragten beschreiben ihre Wahrnehmung; eine unabhängige Messung der Produktivität wurde nicht vorgenommen. Außerdem könnten sich vor allem Personen beteiligt haben, die mit dem Modell zufrieden sind. Die Ergebnisse sind deshalb interessant, sollten aber nicht ohne Weiteres auf alle Tätigkeiten übertragen werden.',
  [('Was wurde unmittelbar erhoben?','Die Wahrnehmung der Befragten.','Eine unabhängige Produktivitätsmessung.'),('Welche Einschränkung wird genannt?','Mögliche Selbstselektion der Teilnehmenden.','Dass niemand zu Hause arbeitet.')],
  [('Выходит за рамки: Die Schlussfolgerung geht darüber ___.','hinaus','Über etwas hinausgehen exceeds its scope.'),('Без дальнейшей проверки: nicht ohne ___ übertragen.','Weiteres','Ohne Weiteres is a fixed expression.')],
  [('vorliegende Angaben','имеющиеся сведения'),('eine Schlussfolgerung ziehen','сделать вывод'),('auf andere Tätigkeiten übertragen','перенести на другие виды деятельности')],
  'Перескажи утверждение из новости, отдели наблюдение от вывода и предложи дополнительную проверку. Не требуется придумывать фактическую новость.'),
 ('Einen Konflikt konstruktiv zusammenfassen','C1',
  'Bei der Planung eines Kulturfestivals fordert eine Gruppe längere Öffnungszeiten, während eine andere auf die Belastung der Anwohner hinweist. Die Diskussion wird zunächst so geführt, als müsse man sich zwischen Kultur und Rücksichtnahme entscheiden. Tatsächlich geht es jedoch um mehrere verhandelbare Bedingungen: Lautstärke, Endzeiten, Besucherlenkung und Kommunikation. Wer den Konflikt zusammenfasst, sollte diese Bedingungen sichtbar machen, statt die Positionen lediglich zu wiederholen. So lassen sich Vorschläge entwickeln, die nicht alle Wünsche erfüllen, aber die wichtigsten Anliegen berücksichtigen.',
  [('Was soll eine Zusammenfassung sichtbar machen?','Verhandelbare Bedingungen.','Nur die lauteste Position.'),('Was können die Vorschläge leisten?','Wichtige Anliegen berücksichtigen.','Garantiert alle Wünsche erfüllen.')],
  [('Учитывать Anliegen: die Anliegen ___.','berücksichtigen','Berücksichtigen means to take into account.'),('Вместо повторения: ___ die Positionen zu wiederholen.','statt','Statt + zu-infinitive expresses an alternative.')],
  [('Rücksichtnahme','внимание к интересам других'),('verhandelbare Bedingungen','условия, которые можно обсудить'),('die wichtigsten Anliegen','главные интересы / запросы')],
  'Нейтрально перескажи конфликт из выбранной сцены сериала, выдели интересы сторон и предложи компромисс без оценки персонажей как хороших или плохих.'),
],
'es':[
 ('Cambiar una reserva','A1',
  'A: Hola. Tengo una reserva para dos personas a las siete. B: ¿A nombre de quién? A: A nombre de Ana. ¿Es posible cambiar la hora? B: Sí, tenemos una mesa a las ocho. A: Perfecto. Muchas gracias. B: Hasta esta tarde.',
  [('На какое время была бронь?','На семь.','На восемь.'),('Какое время предложили взамен?','Восемь.','Шесть.')],
  [('У меня бронь: ___ una reserva.','Tengo','Tengo is the first-person form of tener.'),('Можно изменить время: ¿Es posible ___ la hora?','cambiar','After es posible, use the infinitive.')],
  [('Tengo una reserva','у меня бронь'),('cambiar la hora','изменить время'),('a nombre de Ana','на имя Аны')],
  'Попроси изменить бронь, назови имя и подтверди новое время. Замени время и имя из примера.'),
 ('Pedir ayuda en una tienda','A1',
  'A: Buenos días. Busco una chaqueta. B: ¿De qué color? A: Azul, por favor. B: Esta es pequeña y esta es más grande. A: ¿Puedo probarme la grande? B: Claro. El probador está al fondo. A: Gracias.',
  [('Какой цвет нужен?','Синий.','Красный.'),('Что хочет сделать покупатель?','Примерить большую куртку.','Купить обе куртки сразу.')],
  [('Я ищу куртку: ___ una chaqueta.','Busco','Busco means I am looking for.'),('Можно примерить: ¿Puedo ___ la chaqueta?','probarme','Probarse: to try on clothes.')],
  [('Busco una chaqueta','я ищу куртку'),('más grande','больше'),('el probador','примерочная')],
  'Попроси помочь с покупкой: предмет, цвет, размер и один уточняющий вопрос. Не нужно описывать весь магазин.'),
 ('Organizar un día libre','A1',
  'A: ¿Qué quieres hacer el sábado? B: Quiero visitar el museo. A: Por la mañana trabajo, pero por la tarde tengo tiempo. B: Podemos ir a las cuatro. A: Bien. ¿Dónde nos vemos? B: En la entrada del museo.',
  [('Когда первый собеседник работает?','Утром.','Вечером.'),('Где договорились встретиться?','У входа в музей.','На вокзале.')],
  [('Я хочу посетить: ___ visitar el museo.','Quiero','Querer + infinitive.'),('У меня есть время: ___ tiempo.','Tengo','Tener tiempo means to have time.')],
  [('por la tarde','днём / во второй половине дня'),('Dónde nos vemos','где встретимся'),('la entrada del museo','вход в музей')],
  'Предложи провести выходной вместе. Уточни время и место, затем повтори договорённость своими словами.'),
],
'fa':[
 ('Уточнить заказ','A1',
  'A: سلام. یک چای و یک آب، لطفاً. B: چای با شکر؟ A: نه، بدون شکر. B: آب سرد می‌خواهید؟ A: بله، ممنون. B: چیز دیگری می‌خواهید؟ A: نه، همین کافی است.',
  [('Что заказали кроме чая?','Воду.','Кофе.'),('Какой чай нужен?','Без сахара.','С сахаром.')],
  [('Одна вода: یک ___، لطفاً.','آب','آب — вода.'),('Без сахара: ___ شکر.','بدون','بدون — без.')],
  [('آب سرد','холодная вода'),('همین کافی است','этого достаточно'),('چیز دیگری','что-нибудь ещё')],
  'Закажи два напитка, уточни один параметр и ответь на вопрос, нужно ли что-то ещё.'),
 ('Договориться о разговоре','A1',
  'A: امروز وقت دارید؟ B: امروز نه، ولی فردا عصر وقت دارم. A: ساعت پنج خوب است؟ B: من تا ساعت شش کار می‌کنم. ساعت هفت چطور؟ A: خوب است. فردا ساعت هفت صحبت می‌کنیم.',
  [('Когда собеседник свободен?','Завтра вечером.','Сегодня утром.'),('На какое время договорились?','На семь.','На пять.')],
  [('Сегодня: ___ وقت دارید؟','امروز','امروز — сегодня.'),('Завтра: ___ عصر وقت دارم.','فردا','فردا — завтра.')],
  [('تا ساعت شش','до шести часов'),('ساعت هفت چطور','как насчёт семи'),('فردا عصر','завтра вечером')],
  'Спроси о свободном времени, откажись от одного варианта и подтверди другой. Сначала с текстом, затем без него.'),
 ('Рассказать о выходном','A1',
  'دیروز با دوستم به پارک رفتم. هوا خوب بود. کمی پیاده‌روی کردیم و بعد چای خوردیم. امروز در خانه هستم. می‌خواهم کمی استراحت کنم و فارسی بخوانم.',
  [('Куда ходили вчера?','В парк.','В университет.'),('Где говорящий сегодня?','Дома.','На работе.')],
  [('Вчера: ___ به پارک رفتم.','دیروز','دیروز — вчера.'),('Сегодня: ___ در خانه هستم.','امروز','امروز — сегодня.')],
  [('پیاده‌روی کردیم','мы гуляли пешком'),('استراحت کنم','отдохнуть · в данной конструкции'),('در خانه هستم','я дома')],
  'Расскажи тремя фразами о вчерашнем дне и одной — о плане на сегодня. Затем задай собеседнику вопрос.'),
]}


def additional(language):
    result=[]
    for i,(title,band,passage,questions,drills,phrases,transfer) in enumerate(DATA[language],1):
        checks=[]
        for j,(prompt,answer,other) in enumerate(questions):
            checks.append({'id':f'q{j}','kind':'choice','prompt':prompt,'options':[other,answer] if j%2 else [answer,other],
                           'answers':[answer],'explanation':'Опора в тексте: '+answer})
        for j,(prompt,answer,why) in enumerate(drills):
            checks.append({'id':f'd{j}','kind':'recall','prompt':prompt,'answers':[answer],'explanation':why})
        if language=='en' and i==5:checks[2]['answers'].append('provided that')
        result.append({'id':f'{language}x-{i:02}','language':language,'number':100+i,'title':title,'band':band,
                       'passage':passage,'phrases':[{'front':a,'back':b} for a,b in phrases],'checks':checks,
                       'speaking':transfer,'minutes':25,'source':'Оригинальное задание Аделии. Не официальный материал Cambridge.',
                       'objective':'После блока: '+transfer,
                       'can_do':['Передал основную мысль и важные детали.','Использовал выражения в своей ситуации.','Исправил хотя бы одну трудность после обратной связи.'],
                       'writing_frames':({'en':['The main issue is…','I suggest… because…'],'de':['Einerseits…, andererseits…','Mein Vorschlag wäre…'],'es':['Quiero…','Podemos…'],'fa':['امروز ...','من می‌خواهم ...']})[language],
                       'writing':'Сначала закончи две фразы по материалу. Затем напиши короткий ответ адресату: зачем обращаешься и чего хочешь. Это самостоятельная практика; текст автоматически не оценивается.',
                       'transfer':transfer+' При повторной попытке измени обстоятельства: время, интересы участников или ограничение.',
                       'cycle':[
                         {'stage':'Понять','minutes':5,'task':'Прослушай учебную озвучку без текста, если она доступна, затем проверь понимание по тексту. Озвучка браузера синтетическая.'},
                         {'stage':'Разобрать','minutes':5,'task':'Найди два выражения, объясни их смысл и ответь на вопросы.'},
                         {'stage':'Применить','minutes':10,'task':transfer},
                         {'stage':'Проверить и повторить','minutes':5,'task':'Сверь ответ с целью, разбери обратную связь и повтори с одним изменением ситуации.'}],
                       'block_note':'Три встречи с модулем: понимание; применение через день; перенос на новую ситуацию через неделю. Часы не гарантируют уровень.'})
    return deepcopy(result)


def get(lesson_id):
    for language in DATA:
        item=next((x for x in additional(language) if x['id']==lesson_id),None)
        if item:return item
    raise ValueError('lesson_not_found')
