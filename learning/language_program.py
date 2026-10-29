"""Original self-study material and reviewed external resources. No TV transcripts."""
from copy import deepcopy

LANGUAGES = {
    'es': {'name':'Испанский','locale':'es-ES','start':'С нуля','goal':'База для бытового общения','target_date':'2027-05-01','minutes':40},
    'en': {'name': 'Английский', 'locale': 'en-GB', 'start': 'B1 · самооценка', 'goal': 'C1 · аспирантура', 'target_date': '2027-09-01', 'minutes': 80},
    'de': {'name': 'Немецкий', 'locale': 'de-DE', 'start': 'B1 · самооценка', 'goal': 'Уверенное самостоятельное общение', 'target_date': '2027-05-31', 'minutes': 25},
    'fa': {'name': 'Фарси', 'locale': 'fa-IR', 'start': 'Начальный', 'goal': 'Бытовой разговор', 'target_date': '2027-05-31', 'minutes': 15},
}

ROADMAP = {
 'en': [
  ('Ноябрь–декабрь', 'Восстановить активную речь', 'Ответить на неожиданные вопросы о работе; пересказать новое аудио за 2 минуты.', 'en-01', 'en-02', 'en-03'),
  ('Январь–февраль', 'Сформировать базу B2', 'Объяснить решение, сравнить варианты и поддержать разговор 10 минут.', 'en-04', 'en-05', 'en-06'),
  ('Март–апрель', 'Развить аргументацию', 'Разделять факт и вывод; обсуждать причины, риски и альтернативы.', 'en-07', 'en-08'),
  ('Май–июнь', 'Перейти к академическим задачам', 'Кратко изложить исследование, объяснить метод и ограничения.', 'en-09', 'en-10'),
  ('Июль–август', 'Подготовиться к формату поступления', 'Новый научный материал, вопросы без подготовки, пробное собеседование; письмо по требованиям вуза.', 'en-11', 'en-12'),
 ],
 'de': [
  ('Ноябрь–декабрь', 'Активировать B1', 'Рассказать о рабочей неделе, прошлом опыте и планах.', 'de-01', 'de-02'),
  ('Январь–февраль', 'Решать бытовые задачи', 'Уточнить условия, договориться и объяснить проблему.', 'de-03', 'de-04'),
  ('Март–май', 'Укрепить B2', 'Обсудить мнение и пересказать новую новость с оговорками.', 'de-05', 'de-06'),
  ('Июнь–август', 'Поддерживать и расширять', 'Разговор о работе и образовании без заранее написанного текста.', 'de-07', 'de-08'),
 ],
 'fa': [
  ('Первые 4 недели', 'Буквы, звуки, знакомство', 'Различать знакомые буквы в словах, представиться и переспросить.', 'fa-01', 'fa-02'),
  ('Следующие 4 недели', 'Бытовые диалоги', 'Заказать еду, спросить цену и уточнить маршрут.', 'fa-03', 'fa-04'),
  ('Далее до мая', 'Семья, время, планы', 'Обменяться вопросами и рассказать о своём дне короткими фразами.', 'fa-05', 'fa-06'),
  ('Июнь–август', 'Расширять разговор', 'Понимать короткие ответы и описывать прошедшее событие.', 'fa-07', 'fa-08'),
 ],
}

RESOURCES = [
 {'id':'landman','language':'en','title':'Landman · основной сериал','level':'Живая речь · сложность проверяем по сцене','kind':'Нефтегазовая драма','url':'https://www.paramountplus.com/shows/landman/','why':'Нефтяной бизнес Западного Техаса: работа на промысле, переговоры, деньги и ответственность. Выбор под твою нефтегазовую специальность.','caution':'Акценты, быстрые реплики и грубая речь могут мешать. Начни со сцены на 2–5 минут с английскими субтитрами. Художественная драма не заменяет технические источники. Доступ зависит от страны и подписки.',
  'study_tasks':['Сначала назови участников, их цели и причину конфликта. Не нужно понимать каждое слово.','Повтори сцену с английскими субтитрами. Выбери две разговорные фразы и один отраслевой термин.','Перескажи сцену за минуту: What happened? What was at stake? What would you ask next?','Объясни ту же ситуацию нейтрально, как на рабочей встрече: убери ругань и необоснованную уверенность.'],
  'starter_terms':[('oilfield','нефтяное месторождение / нефтепромысел по контексту'),('drilling rig','буровая установка'),('mineral rights','права на полезные ископаемые; правовой смысл зависит от юрисдикции')],
  'speaking_frames':['The main issue is…','We need to clarify… before making a decision.','From an engineering perspective, I would ask…']},
 {'id':'schwarzes-gold','language':'de','title':'Schwarzes Gold · основной сериал','level':'Живая немецкая речь · историческая драма','kind':'Нефтяной бум и борьба за власть','url':'https://kinescopefilm.de/schwarzes-gold','why':'Близкий по теме выбор: нефтяной бум в Люнебургской пустоши около 1900 года, землевладельцы, рабочие и борьба за богатство. Шесть эпизодов первого сезона.','caution':'Историческая обстановка отличается от современной нефтегазовой отрасли. Смотри в немецком оригинале; доступность ARD и субтитров проверяется в твоём регионе.',
  'study_tasks':['Выбери короткую разговорную сцену. Кто чего добивается и кому это невыгодно?','Пересмотри с немецкими субтитрами, если доступны. Сохрани две фразы для обсуждения и один термин.','Перескажи: Wer will was? Worum geht der Streit? Welche Folgen könnte das haben?','Сравни конфликт с современной отраслью простыми словами; отдели увиденное в драме от проверенных фактов.'],
  'starter_terms':[('das Erdöl','нефть'),('die Bohrung','бурение / скважина по контексту'),('die Förderung','добыча; в других контекстах также поддержка / финансирование')],
  'speaking_frames':['Es geht um…','Meiner Meinung nach fehlt…','Bevor man entscheidet, sollte man…']},
 {'id':'billion-dollar-code','language':'de','title':'The Billion Dollar Code · запасной вариант','level':'Рабочие дискуссии · сложность по сцене','kind':'Технологии, инвестиции и судебный спор','url':'https://www.netflix.com/de/title/81074012','why':'Не про нефть, но близко по инженерной и деловой стороне: разработка технологии, инвесторы, авторство и конфликт с крупной компанией.','caution':'Четыре эпизода; в сериале есть немецкая и английская речь. Для немецкой практики выбирай немецкоязычные сцены. Доступ зависит от региона и подписки.'},
 {'id':'wots','language':'en','title':'Word on the Street','level':'B1–B2 · уровень издателя','kind':'Учебный сериал','url':'https://learnenglish.britishcouncil.org/free-resources/general/video-series/word-street','why':'Дополнительная опора, если художественная сцена пока слишком трудна: короткие видео, расшифровки и упражнения British Council.','caution':'Начни с Jobs или Oxford. Задания издателя выполняются на его сайте.'},
 {'id':'great','language':'en','title':'Britain is GREAT','level':'B2–C1 · уровень издателя','kind':'Познавательная видеосерия','url':'https://learnenglish.britishcouncil.org/free-resources/general/video-series/britain-great','why':'Следующий этап: общество, культура, объяснения и более длинные высказывания.','caution':'Добавлять после освоения более простых материалов; не заменяет академическую подготовку.'},
 {'id':'nico','language':'de','title':'Nicos Weg · B1','level':'B1 · уровень издателя','kind':'Учебный сериал','url':'https://learngerman.dw.com/de/nicos-weg/c-36519687','why':'Восстановление базы через связную историю, упражнения и бытовые ситуации.','caution':'Выбирай B1; A1/A2 используй только для найденных пробелов.'},
 {'id':'jojo','language':'de','title':'Jojo sucht das Glück','level':'B1–B2 · учебная серия DW','kind':'Учебный сериал','url':'https://www.dw.com/jojo','why':'Короткие эпизоды для перехода от учебных диалогов к более живой речи.','caution':'Проверь доступность DW в своей сети. Полные эпизоды открываются у издателя.'},
 {'id':'persian-online','language':'fa','title':'Persian Language Online','level':'Начальный','kind':'Звуки, алфавит и диалоги','url':'https://persianlanguageonline.com/','why':'Для старта полезнее короткие озвученные уроки, чем длинный сериал без понятной опоры.','caution':'Выбираем иранский фарси. Персидское написание осваиваем параллельно с разговором.'},
]

# Format: title, original input, expressions (target / meaning), two comprehension
# questions (prompt, correct, distractor), two retrieval drills (prompt, answer, why),
# and a transfer task. All answer keys stay on the server until submission.
SPECS = {
'en': [
 ('Explain your work',
  'I teach small groups online. My students usually understand an explanation during a lesson, but some struggle to use the same idea a week later. I used to give them more exercises. Now I ask them to explain their reasoning first. This helps me find the point where they get confused. I am still testing the approach; I do not yet know whether it improves their exam results.',
  [('struggle to','испытывать трудности с'),('used to','раньше регулярно делал'),('find out','выяснить')],
  [('What changed in the teacher’s approach?','Students explain their reasoning first.','Students receive more exercises first.'),('What remains uncertain?','The effect on exam results.','Whether lessons are online.')],
  [('Раньше я давал больше упражнений: I ___ give more exercises.','used to','Used to + инфинитив описывает прежнюю привычку.'),('Им трудно объяснить: They ___ explain it.','struggle to','Struggle to + инфинитив: действие даётся трудно.')],
  'Объясни за 60 секунд, что ты преподаёшь. Опора: I teach… / Some students struggle to… / I used to… / Now I… Потом ответь: Why did you change your approach?'),
 ('Tell a clear story',
  'Yesterday a student could not open a homework file. I was preparing another lesson when the message arrived. At first, I thought the link was broken. After checking it, I realised that the file required an account. I sent a different version and asked the student to try again. The problem was solved, but I decided to check access before sending the next assignment.',
  [('at first','сначала'),('after checking','после проверки'),('try again','попробовать снова')],
  [('Why could the student not open the file?','An account was required.','The file had been deleted.'),('What will the teacher change?','Check access before sending files.','Stop assigning homework.')],
  [('Я готовился, когда пришло сообщение: I ___ when the message arrived.','was preparing','Past continuous показывает процесс, во время которого произошло событие.'),('После проверки: ___ it, I found the problem.','after checking','После after можно использовать форму -ing.')],
  'Перескажи историю: ситуация → первая версия → проверка → решение. Затем измени её: что бы ты сделал, если бы новая версия тоже не открылась?'),
 ('Ask and clarify',
  'A: Could you tell me what you mean by independent work? B: I mean work completed without a teacher’s help. A: Does that include using a dictionary? B: Yes, a dictionary is allowed, but a prepared answer is not. A: So, if I understand correctly, I can look up a word, but I should explain the idea myself. B: Exactly. A: Would it be possible to see an example?',
  [('what you mean by','что ты подразумеваешь под'),('if I understand correctly','если я правильно понимаю'),('would it be possible','можно ли было бы')],
  [('What is allowed?','Using a dictionary.','Copying a prepared answer.'),('Why does A restate the rule?','To check understanding.','To reject the task.')],
  [('Если я правильно понимаю: ___, a dictionary is allowed.','if I understand correctly','Фраза позволяет проверить понимание, а не угадать смысл.'),('Что ты подразумеваешь под…: What do you ___ independent work?','mean by','Mean by используется для уточнения значения.')],
  'Ты поступающий. Уточни, что разрешено на экзамене, попроси пример и своими словами проверь понимание. После подсказок повтори без них.'),
 ('Compare options',
  'Our team is choosing between recorded lessons and live workshops. Recordings are easier to fit around work, whereas workshops provide immediate feedback. The cheapest option is not necessarily the most useful one. We could combine both, provided that students have time to prepare. Before deciding, I would ask which problem we are trying to solve: access to explanations or a lack of practice.',
  [('whereas','тогда как'),('not necessarily','не обязательно'),('provided that','при условии что')],
  [('What advantage of workshops is mentioned?','Immediate feedback.','A lower price.'),('What should happen before deciding?','Clarify the problem.','Record every workshop.')],
  [('А не обязательно: The cheapest option is __ the best.','not necessarily','Отделяет возможность от обязательного следствия.'),('При условии что: We can combine them, ___ students prepare.','provided that','Условие, при котором предложение работает.')],
  'Сравни два способа учить язык. Дай по преимуществу и недостатку, выбери один для конкретной ситуации. Используй whereas и provided that.'),
 ('Negotiate and solve',
  'A colleague wants to move a meeting to Friday. I would rather keep Thursday because I have already arranged my lessons around it. However, I could join on Friday morning if we finish before eleven. Instead of simply refusing, I explain the constraint and suggest an alternative. We agree to discuss the urgent question by email and keep the longer meeting on Thursday.',
  [('would rather','предпочёл бы'),('instead of','вместо'),('suggest an alternative','предложить альтернативу')],
  [('Why is Friday difficult?','Lessons have already been arranged.','The colleague is away.'),('What do they agree?','Discuss the urgent issue by email.','Cancel all communication.')],
  [('Я предпочёл бы оставить четверг: I ___ keep Thursday.','would rather','Would rather + инфинитив без to.'),('Вместо отказа: ___ refusing, explain the problem.','instead of','После instead of используем существительное или -ing.')],
  'Откажись от неудобного времени вежливо, объясни ограничение и предложи два решения. Собеседник не принимает первое — ответь на это.'),
 ('Explain a result',
  'Students who completed weekly quizzes received higher final scores. This does not necessarily mean that the quizzes caused the improvement. More motivated students may have been more likely to complete them. To investigate the effect, we would need information about their starting level and study habits. The results are encouraging, but the explanation remains open.',
  [('may have been','возможно, были'),('starting level','исходный уровень'),('does not necessarily mean','не обязательно означает')],
  [('What can the result establish on its own?','An association between completion and scores.','That quizzes caused improvement.'),('What alternative explanation is offered?','Motivated students completed more quizzes.','The final exam was cancelled.')],
  [('Возможно, они были мотивированнее: They ___ more motivated.','may have been','May have + причастие выражает предположение о прошлом.'),('Это не обязательно означает: This ___ that it worked.','does not necessarily mean','Оговорка ограничивает силу вывода.')],
  'Объясни, почему связь между двумя показателями ещё не доказывает причину. Приведи простой пример из преподавания.'),
 ('Disagree with nuance',
  'I agree that online learning can improve access. Nevertheless, access alone does not guarantee participation. A student may have a good connection and still lack a quiet place to study. Rather than arguing that one format is always better, I would examine the conditions under which each format works. The strongest solution may depend on the learners and the task.',
  [('nevertheless','тем не менее'),('under which','при которых'),('depend on','зависеть от')],
  [('What is the writer’s position?','The best format depends on conditions.','Online learning always fails.'),('What does access fail to guarantee?','Participation.','An internet connection.')],
  [('Тем не менее: ___, access is not enough.','nevertheless','Связывает признанное преимущество с ограничением.'),('Зависеть от: Results may ___ the task.','depend on','У depend здесь предлог on.')],
  'Ответь на утверждение: “Все занятия должны быть онлайн”. Сначала признай разумную часть, затем введи ограничение и предложи критерий выбора.'),
 ('Summarise two views',
  'One report argues that frequent tests encourage regular study. Another warns that too much testing can reduce time for deeper learning. These views are not entirely incompatible: both recognise that assessment influences behaviour. The disagreement concerns how often to test and what the tests measure. A balanced policy would use brief checks while protecting time for extended tasks.',
  [('not entirely','не полностью'),('the disagreement concerns','разногласие касается'),('while protecting','при этом сохраняя')],
  [('What do both views recognise?','Assessment influences behaviour.','More tests are always better.'),('What balance is proposed?','Brief checks and extended tasks.','Only one final examination.')],
  [('Разногласие касается частоты: The ___ how often to test.','disagreement concerns','Concerns здесь означает касается.'),('Не полностью несовместимы: They are ___ incompatible.','not entirely','Оговорка позволяет передать частичное совпадение.')],
  'За 90 секунд изложи обе позиции без выбора стороны, затем сформулируй своё решение и его ограничение.'),
 ('Describe a research question',
  'My proposed study asks whether explaining a solution aloud helps students transfer a method to an unfamiliar problem. Previous classroom observations suggest a possible benefit, but they do not establish the effect. I plan to compare two groups using the same materials and different practice tasks. The key outcome will be performance on a new problem rather than recall of the original example.',
  [('proposed study','планируемое исследование'),('rather than','а не / вместо'),('key outcome','основной результат измерения')],
  [('What is the key outcome?','Performance on a new problem.','Recall of the original example.'),('What differs between groups?','Practice tasks.','All learning materials.')],
  [('Планируемое исследование: My ___ asks whether…','proposed study','Proposed показывает, что исследование пока предлагается.'),('Новая задача вместо старой: a new problem ___ the original example.','rather than','Выделяет выбранную альтернативу.')],
  'Представь исследование: вопрос → зачем он нужен → способ проверки → что будешь измерять. Можно использовать тему текста, затем заменить её своей.'),
 ('Discuss limitations',
  'The study involved volunteers from one school, so the findings may not apply to other settings. In addition, the intervention lasted only four weeks. This makes it difficult to distinguish a lasting change from a temporary response to novelty. A follow-up assessment would help, although it would not remove the limitation of the sample. The findings should therefore be interpreted cautiously.',
  [('apply to','быть применимым к'),('distinguish from','отличить от'),('interpreted cautiously','интерпретированы осторожно')],
  [('What would a follow-up help examine?','Whether the change lasts.','Whether volunteers came from many schools.'),('Which limitation would remain?','The sample from one school.','The absence of any assessment.')],
  [('Применимы к другим условиям: The findings may not ___ other settings.','apply to','Apply to: относиться к / быть применимым к.'),('Отличить изменение от новизны: ___ change from novelty.','distinguish','Distinguish A from B.')],
  'Назови два ограничения исследования и предложи улучшение. Затем объясни, какую проблему это улучшение всё равно не решает.'),
 ('Handle an interview challenge',
  'Interviewer: Your sample is small. Why should we trust the findings? Applicant: That is a fair concern. I would treat the project as an exploratory study, not a definitive test. It could reveal practical difficulties and help refine the procedure before a larger trial. Interviewer: What would make you change your hypothesis? Applicant: Consistent evidence against the predicted pattern, particularly on unfamiliar tasks.',
  [('a fair concern','обоснованное замечание'),('exploratory study','поисковое исследование'),('refine the procedure','уточнить процедуру')],
  [('How does the applicant defend the project?','By limiting its claim and explaining its purpose.','By claiming the sample is large.'),('What could challenge the hypothesis?','Consistent evidence against the prediction.','Any difficult interview question.')],
  [('Обоснованное замечание: That is ___.','a fair concern','Признание замечания перед содержательным ответом.'),('Уточнить процедуру: help ___ before a larger trial.','refine the procedure','Refine означает улучшать детали, а не полностью менять цель.')],
  'Ответь на три неожиданных вопроса: Why this topic? What might go wrong? What evidence would change your mind? Сначала с опорами, потом без них.'),
 ('Present and defend a position',
  'Universities should consider several forms of evidence when selecting applicants. An interview can reveal how someone reasons, yet it may also reward confidence rather than preparation. A written task offers a different perspective, although it too is affected by time pressure. No single measure is sufficient. The challenge is to combine measures transparently and examine whether they predict the outcomes the programme actually values.',
  [('several forms of evidence','несколько видов данных'),('no single measure','ни один отдельный показатель'),('the challenge is to','задача состоит в том, чтобы')],
  [('What does the writer recommend?','Combine and evaluate several measures.','Select applicants only by confidence.'),('What should the measures predict?','Outcomes valued by the programme.','Only interview performance.')],
  [('Ни один показатель не достаточен: ___ is sufficient.','no single measure','Single подчёркивает ограниченность одного показателя.'),('Задача состоит в объединении: ___ combine measures.','the challenge is to','Вводит задачу, которую нужно решить.')],
  'Дай двухминутный ответ о справедливом отборе в аспирантуру. Тезис → основания → возражение → ответ → вывод. Затем перескажи позицию, с которой не согласен.'),
],
'de': [
 ('Über die Arbeit sprechen','Ich unterrichte online. Früher habe ich sehr viel erklärt. Heute lasse ich die Lernenden zuerst selbst einen Lösungsweg beschreiben. Dabei merke ich, wo sie Schwierigkeiten haben. Das kostet am Anfang Zeit, aber ich bekomme einen besseren Eindruck von ihrem Verständnis.',
  [('früher','раньше'),('Schwierigkeiten haben','испытывать трудности'),('einen Eindruck bekommen','получить представление')],
  [('Was machen die Lernenden zuerst?','Sie beschreiben einen Lösungsweg.','Sie bekommen sofort mehr Aufgaben.'),('Was erfährt die Lehrkraft?','Wo Schwierigkeiten liegen.','Wie viel die Schüler verdienen.')],
  [('Раньше: ___ habe ich mehr erklärt.','früher','Früher относится к прошлому.'),('Трудности: Sie ___ beim Sprechen.','haben Schwierigkeiten','Schwierigkeiten haben: испытывать трудности.')],
  'Расскажи о работе: Ich unterrichte… / Früher… / Heute… / Dabei… Затем объясни причину изменения.'),
 ('Erlebnisse erzählen','Als ich gestern eine Datei öffnen wollte, bekam ich eine Fehlermeldung. Zuerst dachte ich, dass die Datei beschädigt war. Dann habe ich den Link in einem anderen Browser ausprobiert. Dort hat alles funktioniert. Deshalb werde ich beim nächsten Mal zuerst den Browser prüfen.',
  [('als ich','когда я · событие в прошлом'),('zuerst','сначала'),('deshalb','поэтому')],
  [('Was hat geholfen?','Ein anderer Browser.','Eine neue Datei.'),('Was wird zuerst geprüft?','Der Browser.','Der Stundenplan.')],
  [('Когда я хотел открыть: ___ die Datei öffnen wollte…','als ich','Als вводит однократную ситуацию в прошлом.'),('Поэтому: ___ prüfe ich den Browser.','deshalb','После deshalb в этой структуре идёт спрягаемый глагол.')],
  'Перескажи проблему, две попытки и результат. Потом задай собеседнику вопрос о похожем опыте.'),
 ('Nachfragen und Termine','A: Könnten wir den Termin verschieben? B: Donnerstag wäre möglich, allerdings erst nach fünf. A: Meinen Sie fünf Uhr nachmittags? B: Genau. A: Dann passt es. Wie lange dauert das Gespräch ungefähr? B: Etwa eine halbe Stunde. A: Gut, ich bestätige den Termin noch per E-Mail.',
  [('den Termin verschieben','перенести встречу'),('allerdings','однако'),('ungefähr','примерно')],
  [('Wann ist der Termin möglich?','Am Donnerstag nach fünf.','Am Donnerstag vor fünf.'),('Wie lange dauert das Gespräch?','Etwa dreißig Minuten.','Etwa zwei Stunden.')],
  [('Перенести встречу: Könnten wir ___?','den Termin verschieben','Объект den Termin перед инфинитивом verschieben.'),('Однако: ___ erst nach fünf.','allerdings','Уточнение ограничения.')],
  'Перенеси встречу, уточни время и длительность, повтори договорённость своими словами.'),
 ('Ein Problem lösen','Ich habe einen Kurs gebucht, weil ich mehr sprechen wollte. Leider bestand der Unterricht hauptsächlich aus Vorträgen. Ich habe der Kursleitung erklärt, was ich erwartet hatte, und nach einer anderen Gruppe gefragt. Eine Erstattung war nicht möglich, aber ich konnte kostenlos in einen Gesprächskurs wechseln.',
  [('hauptsächlich','главным образом'),('nach etwas fragen','спросить о чём-либо'),('wechseln','сменить / перейти')],
  [('Was wollte die Person üben?','Sprechen.','Nur Grammatik lesen.'),('Welche Lösung wurde gefunden?','Ein kostenloser Kurswechsel.','Eine vollständige Erstattung.')],
  [('Главным образом: Der Kurs bestand ___ aus Vorträgen.','hauptsächlich','Наречие описывает основной вид деятельности.'),('В другой курс: Ich konnte in einen anderen Kurs ___.','wechseln','Wechseln обозначает переход.')],
  'Объясни несоответствие ожиданиям, попроси решение и отреагируй на отказ вернуть деньги.'),
 ('Meinungen begründen','Digitale Materialien sind praktisch, weil man sie schnell aktualisieren kann. Trotzdem sind gedruckte Bücher für manche Lernende angenehmer. Meiner Ansicht nach hängt die Wahl von der Aufgabe ab. Wenn man etwas gezielt sucht, hilft eine Suchfunktion. Wenn man sich lange konzentrieren möchte, kann Papier Vorteile haben.',
  [('trotzdem','тем не менее'),('meiner Ansicht nach','по моему мнению'),('von etwas abhängen','зависеть от чего-либо')],
  [('Wovon hängt die Wahl ab?','Von der Aufgabe.','Nur vom Alter.'),('Welcher Vorteil wird digital genannt?','Schnelle Aktualisierung.','Keine Ablenkung überhaupt.')],
  [('По моему мнению: ___ hängt es von der Aufgabe ab.','meiner Ansicht nach','После этой фразы в главном предложении глагол стоит на втором месте.'),('Тем не менее: ___ kann Papier helfen.','trotzdem','Вводит контраст.')],
  'Сравни бумажный и электронный учебник. Назови условие, при котором изменишь свой выбор.'),
 ('Nachrichten zusammenfassen','Eine Schule berichtet, dass die Ergebnisse nach einer Stundenplanänderung besser geworden sind. Gleichzeitig wurden jedoch auch die Lerngruppen kleiner. Deshalb lässt sich nicht sicher sagen, welche Änderung entscheidend war. Bevor andere Schulen das Modell übernehmen, sollten sie die Bedingungen genauer untersuchen.',
  [('gleichzeitig','одновременно'),('entscheidend','решающий'),('lässt sich sagen','можно сказать')],
  [('Welche zweite Änderung gab es?','Kleinere Lerngruppen.','Längere Ferien.'),('Was ist unklar?','Welche Änderung entscheidend war.','Ob Ergebnisse berichtet wurden.')],
  [('Одновременно: ___ wurden die Gruppen kleiner.','gleichzeitig','Описывает параллельное событие.'),('Нельзя уверенно сказать: Das ___ nicht sicher sagen.','lässt sich','Lässt sich + инфинитив: можно / возможно сделать.')],
  'Перескажи новость и отдельно назови факт, возможное объяснение и недостающие данные.'),
 ('Studium und Forschung','Ich interessiere mich dafür, wie Menschen komplexe Zusammenhänge verstehen. Besonders spannend finde ich die Frage, ob das eigene Erklären beim Lernen hilft. Ich möchte nicht nur bekannte Aufgaben prüfen, sondern auch neue Situationen untersuchen. Dafür brauche ich eine klare Fragestellung und eine Methode, die zu dieser Frage passt.',
  [('sich interessieren für','интересоваться'),('nicht nur … sondern auch','не только … но и'),('Fragestellung','исследовательский вопрос')],
  [('Was soll untersucht werden?','Auch neue Situationen.','Nur bekannte Antworten.'),('Was muss zur Frage passen?','Die Methode.','Nur der Titel.')],
  [('Интересуюсь: Ich ___ dafür, wie Menschen lernen.','interessiere mich','Sich interessieren — возвратный глагол.'),('Но и: nicht nur Aufgaben, ___ neue Situationen.','sondern auch','Парная конструкция добавления.')],
  'Объясни исследовательский интерес простыми словами. Попроси собеседника уточнить самое непонятное место.'),
 ('Einwände beantworten','A: Ihre Untersuchung dauert nur vier Wochen. Ist das nicht zu kurz? B: Das ist ein berechtigter Einwand. In dieser Zeit kann ich nur kurzfristige Veränderungen beobachten. Um langfristige Wirkungen zu prüfen, wäre eine spätere Befragung sinnvoll. Auch dann müsste ich vorsichtig bleiben, weil nur eine Schule teilnimmt.',
  [('ein berechtigter Einwand','обоснованное возражение'),('langfristig','долгосрочно'),('vorsichtig bleiben','сохранять осторожность')],
  [('Was kann zunächst beobachtet werden?','Kurzfristige Veränderungen.','Alle langfristigen Wirkungen.'),('Welche Einschränkung bleibt?','Nur eine Schule nimmt teil.','Es gibt keine Fragestellung.')],
  [('Обоснованное возражение: Das ist ___.','ein berechtigter Einwand','Признание содержательного замечания.'),('Долгосрочно: Wir wollen ___ Wirkungen prüfen.','langfristige','Прилагательное перед множественным числом без артикля: langfristige.')],
  'Признай ограничение своего плана, предложи улучшение и объясни оставшуюся неопределённость.'),
],
'fa': [
 ('Звуки и знакомство','سلام. من علی هستم. من معلم هستم. شما معلم هستید؟ بله، من هم معلم هستم. خوشبختم.',
  [('سلام','здравствуйте / привет'),('من معلم هستم','я преподаватель'),('خوشبختم','рад знакомству')],
  [('Кто Али?','Преподаватель.','Врач.'),('Что означает من?','Я.','Ты.')],
  [('Привет / здравствуйте','سلام','س + ل + ا + م. Слушай образец носителя; русская запись не передаёт все звуки.'),('Я преподаватель','من معلم هستم','В нейтральной форме связка هستم стоит после именной части.')],
  'Прослушай سلام и معرفی в ресурсе с носителем. Представься двумя фразами и спроси собеседника, преподаватель ли он. Буквы дня: ا ب پ ت; найди их в словах урока.'),
 ('Переспросить и понять','A: اسم شما چیست؟ B: اسم من سارا است. A: ببخشید، متوجه نشدم. لطفاً آهسته‌تر صحبت کنید. B: اسم من سارا است. A: ممنون.',
  [('ببخشید','извините'),('متوجه نشدم','я не понял'),('آهسته‌تر صحبت کنید','говорите медленнее')],
  [('Как зовут собеседницу?','Сара.','Али.'),('Почему просят говорить медленнее?','Не поняли ответ.','Хотят закончить разговор.')],
  [('Извините','ببخشید','Нейтральная вежливая форма.'),('Я не понял','متوجه نشدم','Полезная готовая фраза для восстановления понимания.')],
  'Попроси назвать имя, переспроси и поблагодари. Буквы: ث ج چ ح خ. Сравни ج и چ в озвученных образцах; прочитай имя سارا.'),
 ('Заказать напиток','A: سلام. یک چای، لطفاً. B: چای با شکر؟ A: نه، بدون شکر. B: چیز دیگری می‌خواهید؟ A: نه، ممنون.',
  [('یک چای، لطفاً','один чай, пожалуйста'),('بدون شکر','без сахара'),('نه، ممنون','нет, спасибо')],
  [('Что заказывают?','Чай без сахара.','Кофе с сахаром.'),('Хотят ли что-то ещё?','Нет.','Да.')],
  [('Без сахара','بدون شکر','بدون означает без.'),('Нет, спасибо','نه، ممنون','Короткий вежливый отказ.')],
  'Закажи чай, уточни про сахар и откажись от дополнительного заказа. Буквы: د ذ ر ز ژ. Они не соединяются со следующей буквой слева; посмотри образцы письма.'),
 ('Спросить цену и дорогу','A: ببخشید، ایستگاه مترو کجاست؟ B: نزدیک پارک است. A: دور است؟ B: نه، ده دقیقه پیاده. A: ممنون. بلیت چقدر است؟ B: قیمت را در ایستگاه بپرسید.',
  [('کجاست؟','где находится?'),('چقدر است؟','сколько стоит / сколько это?'),('نزدیک','близко / рядом')],
  [('Где метро?','Около парка.','Внутри школы.'),('Указана ли цена билета?','Нет, её предлагают спросить на станции.','Да, десять.')],
  [('Где находится?','کجاست','В سوالительном употреблении можно поставить знак вопроса: کجاست؟'),('Рядом / близко','نزدیک','После близко к часто используется به; здесь نزدیک پارک است.')],
  'Спроси, где метро, далеко ли оно и сколько стоит билет. Не придумывай цену из диалога. Буквы: س ش ص ض; числа: یک، دو، سه، چهار، پنج.'),
 ('Работа и семья','من معلم هستم و آنلاین کار می‌کنم. برادر من دانشجو است. او آلمانی یاد می‌گیرد. من انگلیسی و فارسی یاد می‌گیرم. ما هر روز کمی تمرین می‌کنیم.',
  [('کار می‌کنم','я работаю'),('یاد می‌گیرم','я учу / изучаю'),('هر روز','каждый день')],
  [('Кто изучает немецкий?','Брат.','Только преподаватель.'),('Как часто они практикуются?','Каждый день понемногу.','Раз в месяц.')],
  [('Каждый день','هر روز','هر — каждый, روز — день.'),('Я работаю','کار می‌کنم','Настоящее время: составной глагол کار کردن.')],
  'Расскажи о работе и одном близком человеке. Задай встречный вопрос. Буквы: ط ظ ع غ ف ق; числа: شش، هفت، هشت، نه، ده.'),
 ('Время и планы','A: فردا وقت دارید؟ B: صبح کار می‌کنم، ولی عصر وقت دارم. A: ساعت شش خوب است؟ B: بله، خوب است. A: پس فردا ساعت شش صحبت می‌کنیم.',
  [('فردا','завтра'),('وقت دارم','у меня есть время'),('ساعت شش','в шесть часов')],
  [('Когда собеседник свободен?','Вечером.','Утром.'),('На сколько договорились?','На шесть.','На десять.')],
  [('Завтра','فردا','Слово времени часто стоит в начале предложения.'),('У меня есть время','وقت دارم','دارم — я имею.')],
  'Договорись о разговоре: сначала откажись от утра, затем предложи вечер. Буквы: ک گ ل م ن; послушай разницу ک и گ.'),
 ('Рассказать о вчерашнем дне','دیروز صبح کار کردم. بعد به پارک رفتم. هوا خوب بود. عصر با دوستم صحبت کردم. امروز می‌خواهم کمی فارسی تمرین کنم.',
  [('دیروز','вчера'),('رفتم','я пошёл'),('می‌خواهم','я хочу')],
  [('Куда пошли после работы?','В парк.','На станцию.'),('Что хотят делать сегодня?','Практиковать фарси.','Покупать билет.')],
  [('Вчера','دیروز','Отличай от امروز — сегодня и فردا — завтра.'),('Я пошёл','رفتم','Прошедшее время от رفتن.')],
  'Три фразы о вчера и одна о сегодняшнем плане. Буквы: و ه ی; повтори весь алфавит в разных позициях и найди соединения в دیروز.'),
 ('Поддержать бытовой разговор','A: چرا فارسی یاد می‌گیرید؟ B: چون می‌خواهم با مردم صحبت کنم. A: چه چیزی برای شما سخت است؟ B: وقتی سریع صحبت می‌کنند، خوب متوجه نمی‌شوم. A: هر روز کمی گوش کنید و سؤال بپرسید.',
  [('چرا؟','почему?'),('چون','потому что'),('سؤال بپرسید','задавайте вопросы')],
  [('Зачем учат фарси?','Чтобы общаться с людьми.','Только для чтения газет.'),('Что пока трудно?','Понимать быструю речь.','Назвать профессию.')],
  [('Почему?','چرا','Вопрос о причине.'),('Потому что','چون','Вводит причину.')],
  'Объясни, зачем учишь фарси, назови трудность и попроси совет. Затем поменяйтесь ролями. Повтори буквы, которые всё ещё путаешь.'),
],
}


def units(language):
    result = []
    for i, spec in enumerate(SPECS[language], 1):
        title, passage, phrases, questions, drills, speaking = spec
        checks = []
        for j, (prompt, correct, distractor) in enumerate(questions):
            # Vary the answer position without randomising across retries.
            options = [correct, distractor] if (i+j) % 2 else [distractor, correct]
            checks.append({'id':f'q{j}', 'kind':'choice', 'prompt':prompt, 'options':options,
                           'answers':[correct], 'explanation':'Сверь ответ с материалом урока: '+correct})
        for j, (prompt, answer, why) in enumerate(drills):
            checks.append({'id':f'd{j}', 'kind':'recall', 'prompt':prompt,
                           'answers':[answer], 'explanation':why})
        result.append({'id':f'{language}-{i:02}', 'language':language, 'number':i, 'title':title,
                       'passage':passage, 'phrases':[{'front':a,'back':b} for a,b in phrases],
                       'checks':checks, 'speaking':speaking, 'minutes':25,
                       'source':'Авторский учебный материал Аделии. Это не текст из сериала.'})
    return result


def lesson(lesson_id, include_keys=False):
    if str(lesson_id).split('-')[0] in ('enb','deb','esb','fab'):
        from learning.route_bridges import get
        item=get(lesson_id)
        if not include_keys:
            for q in item['checks']:q.pop('answers');q.pop('explanation')
        return item
    if str(lesson_id).split('-')[0] in ('enx','dex','esx','fax'):
        from learning.intensive_program import get
        item=get(lesson_id)
        if not include_keys:
            for q in item['checks']:q.pop('answers');q.pop('explanation')
        return item
    if str(lesson_id).startswith(('en0-','de0-','es-')):
        from learning.beginner_languages import units as basics
        code={'en0':'en','de0':'de','es':'es'}[str(lesson_id).split('-')[0]]
        item=next((x for x in basics(code) if x['id']==lesson_id),None)
        if item is None:raise ValueError('lesson_not_found')
        if not include_keys:
            for q in item['checks']:q.pop('answers');q.pop('explanation')
        return item
    language = str(lesson_id).split('-')[0]
    if language not in LANGUAGES:
        raise ValueError('lesson_not_found')
    item = next((x for x in units(language) if x['id']==lesson_id), None)
    if item is None:
        raise ValueError('lesson_not_found')
    item=deepcopy(item)
    if not include_keys:
        for check in item['checks']:
            check.pop('answers');check.pop('explanation')
    return item


def catalogue():
    from learning.intensive_program import additional
    return {language:[{'id':x['id'],'number':x['number'],'title':x['title'],'minutes':x['minutes']}
                      for x in units(language)+additional(language)] for language in ('en','de','fa')}


def serial_protocol(language):
    return {
      'watch':'Посмотри новую сцену 2–5 минут без субтитров. Назови участников, ситуацию и главную проблему.',
      'notice':'Повтори с субтитрами на изучаемом языке. Выбери до трёх выражений, которые пригодятся тебе.',
      'repeat':'Послушай 20–30 секунд ещё раз. Повтори реплики, затем вырази ту же мысль своими словами.',
      'transfer':'Закрой субтитры. Перескажи сцену за 60–90 секунд и скажи, что ты сделал бы на месте героя.',
      'check':'Завтра вспомни выражения без подсказки. Если сюжет почти непонятен даже с субтитрами — выбери более простой материал.',
      'note':'Для фарси в начале используй короткий озвученный диалог вместо полной серии.' if language=='fa' else 'Просмотр и самооценка учитываются отдельно от проверяемых заданий.',
    }
