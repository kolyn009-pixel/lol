"""Authored branching practice, not an AI claim of understanding the learner."""
from copy import deepcopy
BASE={
'en':('You are arranging a meeting. I am your classmate.','When can we meet to practise?',{'clarify':'I mean this week. Which days work for you?','agree':'Good. How long shall we practise?','alternative':'That time is difficult for me. What is another option?'},'Something has changed: I only have ten minutes. What shall we practise first?',['Could you repeat that?','How about tomorrow?']),
'de':('Du planst ein Treffen. Ich bin dein Lernpartner.','Wann können wir zusammen üben?',{'clarify':'Ich meine diese Woche. An welchen Tagen hast du Zeit?','agree':'Gut. Wie lange wollen wir üben?','alternative':'Diese Uhrzeit passt mir nicht. Hast du einen anderen Vorschlag?'},'Es hat sich etwas geändert: Ich habe nur zehn Minuten. Was üben wir zuerst?',['Kannst du das wiederholen?','Wie wäre es morgen?']),
'es':('Quieres organizar una reunión. Soy tu compañero de estudio.','¿Cuándo podemos practicar juntos?',{'clarify':'Me refiero a esta semana. ¿Qué días puedes?','agree':'Bien. ¿Cuánto tiempo vamos a practicar?','alternative':'Esa hora no me viene bien. ¿Qué otra opción propones?'},'Ha cambiado algo: solo tengo diez minutos. ¿Qué practicamos primero?',['¿Puedes repetirlo?','¿Qué tal mañana?']),
'fa':('می‌خواهید برای تمرین با من قرار بگذارید. من هم‌کلاسی شما هستم.','چه زمانی می‌توانیم با هم تمرین کنیم؟',{'clarify':'منظورم این هفته است. چه روزهایی وقت دارید؟','agree':'خوب است. چقدر تمرین کنیم؟','alternative':'این ساعت برای من مناسب نیست. پیشنهاد دیگری دارید؟'},'برنامه عوض شده است: من فقط ده دقیقه وقت دارم. اول چه چیزی را تمرین کنیم؟',['می‌شود تکرار کنید؟','فردا چطور است؟']),
}
COURSE={
'en':('You are choosing a course. I help with enrolment.','What would you like to practise?',{'clarify':'We offer reading and conversation. Which is your priority?','agree':'Good. Would you prefer a short daily session or a longer weekend session?','alternative':'That group is full. What other format could work for you?'},'The available group starts later than you planned. Explain what you can change and what you need to keep.',['I would like to…','My main priority is…']),
'de':('Du wählst einen Kurs. Ich berate dich.','Was möchtest du besonders üben?',{'clarify':'Es gibt Lesen und Konversation. Was ist dir wichtiger?','agree':'Möchtest du täglich kurz oder am Wochenende länger üben?','alternative':'Diese Gruppe ist voll. Welches andere Format wäre möglich?'},'Die freie Gruppe beginnt später als geplant. Erkläre, was du ändern kannst und was wichtig bleibt.',['Ich möchte…','Mir ist wichtig, dass…']),
'es':('Estás eligiendo un curso. Te ayudo a elegir.','¿Qué te gustaría practicar?',{'clarify':'Ofrecemos lectura y conversación. ¿Qué prefieres?','agree':'¿Prefieres practicar un poco cada día o más tiempo el fin de semana?','alternative':'Ese grupo está completo. ¿Qué otro formato te serviría?'},'El grupo disponible empieza más tarde. Explica qué puedes cambiar y qué necesitas mantener.',['Me gustaría…','Para mí es importante…']),
'fa':('می‌خواهید یک کلاس انتخاب کنید. من به شما کمک می‌کنم.','دوست دارید چه چیزی را بیشتر تمرین کنید؟',{'clarify':'کلاس خواندن و گفت‌وگو داریم. کدام برای شما مهم‌تر است؟','agree':'دوست دارید هر روز کمی تمرین کنید یا آخر هفته بیشتر؟','alternative':'این گروه پر شده است. چه روش دیگری برای شما مناسب است؟'},'گروه جدید دیرتر شروع می‌شود. توضیح دهید چه چیزی را می‌توانید تغییر دهید و چه چیزی برایتان مهم است.',['می‌خواهم ...','برای من مهم است که ...']),
}
DATA={}
for language in BASE:
 for kind,bank,title,band in [('meeting',BASE,'Договориться о практике','A1–A2'),('course',COURSE,'Выбрать формат обучения','A2–B1')]:
  role,opening,branches,change,frames=bank[language]
  DATA[language+'-'+kind]={'language':language,'title':title,'band':band,'role':role,'opening':opening,'branches':branches,'change':change,'frames':frames}
DATA['en-research']={'language':'en','title':'Собеседование в аспирантуру','band':'B2–C1','role':'You are an applicant. I ask about your proposed research. Use a real interest or clearly label an imagined example.','opening':'What question would you like to investigate, and why does it matter?', 'branches':{'clarify':'By a research question, I mean something you could investigate with evidence. Could you narrow your proposal?','agree':'What evidence would help you answer that question?','alternative':'Suppose those data were unavailable. What other approach could you consider?'},'change':'Your initial results disagree with your expectation. How would you investigate that, and what could you conclude?','frames':['My proposed question is…','A limitation would be…']}
DATA['en-energy']={'language':'en','title':'Обсудить исследование в энергетике','band':'B2–C1','role':'We discuss a hypothetical energy research proposal. Practise language and reasoning; do not give equipment operating instructions.','opening':'Which energy-related issue interests you, and what would you want to learn about it?', 'branches':{'clarify':'Could you explain that issue to someone outside your field?','agree':'What evidence would make your proposal convincing?','alternative':'Suppose the budget were smaller. Which part of the study would you prioritise?'},'change':'A colleague offers a different explanation for the same findings. How would you compare the explanations fairly?','frames':['One possible explanation is…','We would need to compare…']}


def scenario(identifier):
 if identifier not in DATA:raise ValueError('conversation_not_found')
 return deepcopy(DATA[identifier])


def prompt(material,answers,turn):
 if turn==0:return material['opening']
 if turn==1:return material['branches'][answers[0]['intention']]
 return material['change']
