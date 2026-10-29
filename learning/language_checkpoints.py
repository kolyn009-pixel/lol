"""Parallel, original short checks. These are not a standardised CEFR test."""
from copy import deepcopy


def form(language, label, passage, comprehension, recall):
    checks=[]
    for i,(prompt,answer,other) in enumerate(comprehension):
        options=[answer,other] if i%2 else [other,answer]
        checks.append({'id':f'c{i}','kind':'choice','skill':'comprehension','prompt':prompt,
                       'options':options,'answers':[answer],'explanation':'Смысл материала: '+answer})
    for i,(prompt,answer,explanation) in enumerate(recall):
        checks.append({'id':f'r{i}','kind':'recall','skill':'recall','prompt':prompt,
                       'answers':[answer],'explanation':explanation})
    return {'id':language+'-'+label,'language':language,'label':label,'passage':passage,'checks':checks}


FORMS = [
 form('en','A',
  'A library offered evening study sessions for adults who worked during the day. Attendance rose in the first month, but some visitors said the room was too noisy for reading. The library then introduced two separate areas: one for discussion and one for quiet work. Attendance stayed about the same, while complaints about noise decreased. The staff do not yet know whether visitors are learning more; they have only measured attendance and complaints.',
  [('Why were sessions held in the evening?','Some visitors worked during the day.','The library was closed during the day.'),('What changed after separate areas were introduced?','There were fewer noise complaints.','Attendance doubled.'),('What remains unknown?','Whether learning improved.','Whether anyone attended.')],
  [('Раньше я учился по вечерам: I ___ study in the evenings.','used to','Used to + инфинитив описывает прежнюю привычку.'),('Сначала я проверил время: ___, I checked the time.','at first','At first — сначала; порядок действий можно выразить и first, который здесь тоже допустим.'),('Зависит от задачи: It may ___ the task.','depend on','Depend on — зависеть от.')]),
 form('en','B',
  'A community centre introduced online booking because people had complained about long queues. Queues became shorter, but several older visitors found the website confusing. The centre kept online booking and added a telephone service. More people were able to book, although staff now spent longer answering calls. The manager has not yet calculated the total cost, so it is too early to claim that the new system saves money.',
  [('Why was online booking introduced?','People complained about queues.','Staff wanted fewer visitors.'),('What was added later?','Telephone booking.','A second website.'),('Which conclusion is not yet supported?','The system saves money overall.','Some users found the website confusing.')],
  [('Раньше я звонил заранее: I ___ call in advance.','used to','Used to + инфинитив: прежняя привычка.'),('Сначала я проверил адрес: ___, I checked the address.','at first','В этом контексте также подходит first.'),('Зависит от стоимости: It may ___ the cost.','depend on','Depend on — зависеть от.')]),
 form('en','C',
  'A museum gave visitors a free audio guide to help them understand the exhibitions. Surveys showed that users liked the guide, but many stopped listening when the recordings became long. The museum shortened the recordings and added optional details. Completion rates increased. However, the survey included only people who chose to use the guide, so it cannot show whether all visitors would benefit from it.',
  [('What problem was noticed?','Many users stopped during long recordings.','Visitors could not enter the museum.'),('What did the museum change?','It shortened the recordings.','It removed all optional details.'),('What limits the conclusion?','The survey covered only guide users.','Nobody completed a recording.')],
  [('Раньше я слушал длинные записи: I ___ listen to long recordings.','used to','Used to + инфинитив: прежняя привычка.'),('Сначала я проверил громкость: ___, I checked the volume.','at first','Здесь также допустимо first.'),('Зависит от темы: It may ___ the topic.','depend on','Depend on — зависеть от.')]),
 form('de','A',
  'Eine Stadtbibliothek öffnet jetzt auch am Sonntag. Viele Berufstätige finden das praktisch. Einige Mitarbeitende wünschen sich jedoch einen freien Tag unter der Woche. Die Leitung möchte das Angebot drei Monate lang testen. Erst danach will sie entscheiden, ob die Sonntagsöffnung dauerhaft bleibt.',
  [('Wer findet die neue Öffnung praktisch?','Viele Berufstätige.','Nur Kinder.'),('Was wünschen sich einige Mitarbeitende?','Einen freien Tag unter der Woche.','Längere Sonntagsdienste.'),('Ist die dauerhafte Öffnung schon beschlossen?','Nein, zuerst wird getestet.','Ja, ohne weiteren Test.')],
  [('Раньше я читал дома: ___ habe ich zu Hause gelesen.','früher','Früher — раньше.'),('Тем не менее я прихожу: ___ komme ich.','trotzdem','В главном предложении после trotzdem стоит спрягаемый глагол.'),('Это зависит от задачи: Das hängt ___ der Aufgabe ab.','von','Abhängen von + дательный падеж.')]),
 form('de','B',
  'Ein Sportverein bietet seit kurzem Kurse am frühen Morgen an. Das hilft Menschen, die abends arbeiten. Manche Trainerinnen und Trainer finden den frühen Beginn allerdings anstrengend. Der Verein prüft das Angebot zunächst sechs Wochen lang. Danach sollen Teilnahmezahlen und Rückmeldungen gemeinsam ausgewertet werden.',
  [('Wem helfen die frühen Kurse?','Menschen, die abends arbeiten.','Nur Menschen ohne Arbeit.'),('Was finden manche Trainer anstrengend?','Den frühen Beginn.','Die Rückmeldungen per E-Mail.'),('Worauf soll die Entscheidung beruhen?','Auf Teilnahmezahlen und Rückmeldungen.','Nur auf dem ersten Kurstag.')],
  [('Раньше я тренировался вечером: ___ habe ich abends trainiert.','früher','Früher — раньше.'),('Тем не менее я участвую: ___ nehme ich teil.','trotzdem','После trotzdem глагол занимает вторую позицию.'),('Это зависит от времени: Das hängt ___ der Zeit ab.','von','Abhängen von + дательный падеж.')]),
 form('de','C',
  'Ein Unternehmen erlaubt seinem Team, an zwei Tagen pro Woche von zu Hause zu arbeiten. Viele sparen dadurch Zeit für den Arbeitsweg. Einige vermissen jedoch den direkten Austausch. Nach einer Testphase möchte die Leitung nicht nur die Produktivität, sondern auch die Zusammenarbeit beurteilen. Eine endgültige Entscheidung gibt es noch nicht.',
  [('Welcher Vorteil wird genannt?','Weniger Zeit für den Arbeitsweg.','Mehr Urlaubstage.'),('Was vermissen einige?','Den direkten Austausch.','Eine längere Fahrt.'),('Was wird nach dem Test beurteilt?','Produktivität und Zusammenarbeit.','Nur die Zahl der Computer.')],
  [('Раньше я работал в офисе: ___ habe ich im Büro gearbeitet.','früher','Früher — раньше.'),('Тем не менее я спрашиваю: ___ frage ich nach.','trotzdem','Trotzdem вводит контраст.'),('Это зависит от команды: Das hängt ___ dem Team ab.','von','Abhängen von + дательный падеж.')]),
 form('fa','A',
  'سلام. من مریم هستم. من معلم هستم. امروز صبح کار می‌کنم. عصر وقت دارم. می‌خواهم با دوستم فارسی تمرین کنم.',
  [('Как зовут говорящую?','Марьям.','Сара.'),('Когда она работает?','Утром.','Вечером.'),('Что она хочет делать вечером?','Практиковать фарси с другом.','Купить билет.')],
  [('Завтра','فردا','فردا — завтра.'),('Нет, спасибо','نه، ممنون','Короткий вежливый отказ.'),('Извините','ببخشید','Вежливое обращение перед вопросом.')]),
 form('fa','B',
  'سلام. اسم من رضا است. من دانشجو هستم. امروز صبح به دانشگاه می‌روم. عصر با برادرم صحبت می‌کنم. او آلمانی یاد می‌گیرد.',
  [('Как зовут говорящего?','Реза.','Али.'),('Куда он идёт утром?','В университет.','В парк.'),('Кто учит немецкий?','Его брат.','Его преподаватель.')],
  [('Завтра','فردا','فردا — завтра.'),('Нет, спасибо','نه، ممنون','Короткий вежливый отказ.'),('Извините','ببخشید','Вежливое обращение перед вопросом.')]),
 form('fa','C',
  'من نرگس هستم. در خانه کار می‌کنم. امروز عصر به پارک می‌روم. بعد با دوستم چای می‌خورم. فردا صبح وقت دارم.',
  [('Где работает говорящая?','Дома.','В университете.'),('Куда она идёт вечером?','В парк.','На вокзал.'),('Когда у неё есть время?','Завтра утром.','Только сегодня ночью.')],
  [('Завтра','فردا','فردا — завтра.'),('Нет, спасибо','نه، ممنون','Короткий вежливый отказ.'),('Извините','ببخشید','Вежливое обращение перед вопросом.')]),
]

# Accept a valid alternative rather than flag a correct short answer as an error.
for item in FORMS:
    if item['language']=='en':
        item['checks'][4]['answers'].append('first')


def checkpoint(form_id, keys=False):
    result=next((deepcopy(x) for x in FORMS if x['id']==form_id),None)
    if result is None:raise ValueError('checkpoint_not_found')
    if not keys:
        for q in result['checks']:
            q.pop('answers');q.pop('explanation')
    return result
