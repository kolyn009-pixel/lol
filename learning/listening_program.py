"""Publisher-hosted recordings: no media copies, invented transcripts or TTS scores."""
from copy import deepcopy
SOURCES={
 'bc-table':{'language':'en','title':'Booking a table · British Council','level':'A1 · издатель',
 'url':'https://learnenglish.britishcouncil.org/free-resources/listening/a1/booking-table','mode':'checked',
 'instruction':'Прослушай обе части телефонного разговора. Пока не открывай Transcript. После первого прослушивания вернись и ответь.',
 'review':'В первом звонке согласовали раннее время для небольшой группы. Во втором изменили число гостей и перенесли время. Различай количество людей и время.',
 'checks':[{'id':'people','prompt':'Сколько гостей будет после второго звонка?','options':['4','6','8'],'answer':'6'},
           {'id':'time','prompt':'На какое время окончательно договорились?','options':['19:30','20:00','21:00'],'answer':'20:00'}]},
 'dw-nico':{'language':'de','title':'Nicos Weg · Deutsche Welle','level':'Выбери A1/A2/B1 на сайте издателя','url':'https://learngerman.dw.com/de/nicos-weg/c-36519687','mode':'guided',
 'instruction':'Выбери эпизод своего уровня. Сначала слушай 30–90 секунд без субтитров. Сохрани название и время фрагмента, чтобы повторить тот же отрывок.',
 'review':'Включи субтитры у издателя. Найди места, где не распознал границы слов. Снова прослушай тот же фрагмент.'},
 'rtve-ministerio':{'language':'es','title':'El Ministerio del Tiempo · RTVE','level':'Живая речь; для начала нужен очень короткий фрагмент с опорами','url':'https://www.rtve.es/play/videos/el-ministerio-del-tiempo/','mode':'guided',
 'instruction':'Выбери доступную серию и фрагмент 30–60 секунд. Запиши серию и таймкод. Это сложный дополнительный материал, не начальный курс. Учитывай возрастной рейтинг и региональную доступность.',
 'review':'Проверь смысл по испанским субтитрам, если они доступны. Отдели слова, которые узнал на слух, от понятых только после чтения.'},
 'persian-beginner':{'language':'fa','title':'Persian Language Online · Beginner','level':'Начальный · издатель','url':'https://persianlanguageonline.com/courses/beginner/','mode':'guided',
 'instruction':'У издателя требуется регистрация на бесплатный курс. Выбери Hello или Good Morning. Сначала прослушай диалог без текста. Запиши урок и фрагмент.',
 'review':'Сравни с Persian Text и Transliteration у издателя. Повтори трудное место, затем послушай ещё раз без текста.'},
}


def source(identifier,keys=False,reveal=False):
 if identifier not in SOURCES:raise ValueError('listening_not_found')
 out=deepcopy(SOURCES[identifier]);out['id']=identifier
 if not keys:
  for q in out.get('checks',[]):q.pop('answer')
 if not reveal:out.pop('review')
 return out
