"""Original scaffolds and transfer exercises; practice, not CEFR assessment."""
from copy import deepcopy
HELP={
'en':{'explain':'Сначала назови, кто действует и что происходит. Затем добавь одну причину или ограничение. Не переводи длинное русское предложение целиком: собери ответ из коротких частей.', 'example':'I can meet on Friday, but only after six.', 'meaning':'Я могу встретиться в пятницу, но только после шести.', 'frames':['I can…','The reason is…','Could we…?'], 'task':'Вы уже договорились о встрече, но хотите перенести её. Выбери вежливую просьбу.', 'options':['Could we meet a little later?','We met yesterday.','I have never been there.'], 'answer':'Could we meet a little later?', 'why':'Could we + начальная форма глагола — вежливое предложение изменить совместный план.'},
'de':{'explain':'Начни с короткой главной фразы: кто, действие, важная деталь. В обычном утверждении личная форма глагола стоит на втором месте. Длинную мысль можно разделить на два предложения.', 'example':'Ich kann am Freitag kommen, aber erst nach sechs.', 'meaning':'Я могу прийти в пятницу, но только после шести.', 'frames':['Ich kann…','Für mich ist wichtig…','Könnten wir…?'], 'task':'Ты хочешь вежливо перенести совместную встречу. Выбери просьбу.', 'options':['Könnten wir uns etwas später treffen?','Wir haben uns gestern getroffen.','Ich wohne hier.'], 'answer':'Könnten wir uns etwas später treffen?', 'why':'Könnten wir…? выражает вежливое предложение, а не сообщение о прошлом.'},
'es':{'explain':'Скажи одну простую мысль: что ты хочешь или можешь сделать. Потом добавь время. Местоимение yo часто можно опустить: форму лица уже показывает глагол.', 'example':'Puedo ir el viernes, pero después de las seis.', 'meaning':'Я могу прийти в пятницу, но после шести.', 'frames':['Quiero…','Puedo…','¿Podemos…?'], 'task':'Хочешь предложить встретиться чуть позже. Выбери подходящую просьбу.', 'options':['¿Podemos quedar un poco más tarde?','Nos vimos ayer.','Vivo cerca.'], 'answer':'¿Podemos quedar un poco más tarde?', 'why':'¿Podemos + инфинитив? предлагает совместное действие; más tarde означает позже.'},
'fa':{'explain':'Собери короткую фразу по образцу. В персидском глагол обычно находится в конце предложения. Сначала можно прочитать с опорой, затем закрыть её и повторить вслух.', 'example':'من فردا وقت دارم.', 'meaning':'У меня завтра есть время.', 'frames':['من ... هستم.','من ... می‌خواهم.','فردا چطور است؟'], 'task':'Предложи перенести встречу на завтра. Выбери подходящую фразу.', 'options':['فردا چطور است؟','دیروز آمدم.','این کتاب است.'], 'answer':'فردا چطور است؟', 'why':'فردا означает завтра, а چطور است؟ — как насчёт…? Другие варианты говорят о прошлом или предмете.'}}

# Exact-pattern transfer bank. No claim that unrelated generic drills repair an error.
TRANSFER={
'used to':('Before university, Maya ___ take the bus every morning.',['used to','is used to','use to'],'used to','Прошлая привычка: used to + начальная форма глагола.'),
'struggle to':('I sometimes ___ explain a new idea without an example.',['struggle to','struggle for','struggled that'],'struggle to','Struggle to + глагол: испытывать трудности с действием.'),
'provided that':('You may use this room ___ you leave it tidy.',['provided that','although','despite'],'provided that','Provided that вводит условие: при условии, что.'),
'could we':('___ move our discussion to Friday?',['Could we','We could that','Could to'],'Could we','Could we + глагол: вежливая просьба о совместном действии.'),
'ich möchte':('___ einen Tee, bitte.',['Ich möchte','Ich mögen','Ich möchten'],'Ich möchte','Ich möchte — я хотел(а) бы. После ich форма möchte.'),
'me gustaría':('___ practicar un poco cada día.',['Me gustaría','Me gustan','Me gusto'],'Me gustaría','Me gustaría + инфинитив: мне хотелось бы что-то делать.'),
'می‌خواهم':('من یک چای ___.',['می‌خواهم','می‌خواهد','می‌خواهید'],'می‌خواهم','С местоимением من используется форма первого лица می‌خواهم.')}


def scaffold(language):
 if language not in HELP:raise ValueError('invalid_language')
 return deepcopy(HELP[language])


def transfer(answer):
 from web_backend.self_study import normalise
 item=next((v for k,v in TRANSFER.items() if normalise(k)==normalise(answer)),None)
 if not item:return None
 prompt,options,correct,why=item
 return {'prompt':prompt,'options':options,'answer':correct,'why':why}
