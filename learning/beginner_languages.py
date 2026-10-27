"""Small original foundation modules for a diagnosis-led starting route."""
DATA={
 'en':[
  ('Знакомство','Hello. My name is Anna. I am a student. I live in Moscow. I am learning English.', 'My name is','Меня зовут','I am a student','Я студентка'),
  ('Обычный день','I work from home. I start at nine. I have lunch at one. In the evening I read or watch a film.', 'I work from home','Я работаю из дома','in the evening','вечером'),
  ('Вопросы','Where do you live? I live near the station. Do you work here? Yes, I do. What do you like? I like music.', 'Where do you live','Где ты живёшь','I like music','Мне нравится музыка'),
  ('Вчера и завтра','Yesterday I visited a friend. We cooked dinner. Tomorrow I am going to study. I want to practise speaking.', 'Yesterday','вчера','Tomorrow','завтра'),
  ('Опыт','I have lived here for two years. I moved here in 2024. I have never studied abroad, but I would like to try.', 'for two years','в течение двух лет','I would like to','я хотела бы'),
  ('Выбор и причины','This course is cheaper than that one. However, the other course has more practice. I will choose it because I need to speak more.', 'cheaper than','дешевле, чем','because','потому что'),
 ],
 'es':[
  ('Знакомство','Hola. Me llamo Ana. Soy estudiante. Vivo en Moscú. Estoy aprendiendo español.', 'Hola','Привет','Me llamo Ana','Меня зовут Ана'),
  ('Попросить повторить','Perdón, no entiendo. ¿Puede repetir, por favor? Más despacio, por favor. Gracias.', 'No entiendo','Я не понимаю','Más despacio, por favor','Помедленнее, пожалуйста'),
  ('О себе','Soy de Rusia. Hablo ruso y un poco de inglés. Quiero aprender español para viajar.', 'Soy de Rusia','Я из России','Quiero aprender español','Я хочу выучить испанский'),
  ('В кафе','Buenos días. Un café, por favor. ¿Con leche? Sí, con leche. ¿Algo más? No, gracias.', 'Un café, por favor','Кофе, пожалуйста','No, gracias','Нет, спасибо'),
  ('Время','¿Qué hora es? Son las dos. Hoy trabajo. Mañana tengo tiempo para estudiar.', 'Hoy','сегодня','Mañana','завтра'),
  ('Дорога','Perdón, ¿dónde está la estación? Está cerca del parque. ¿Está lejos? No, está a cinco minutos.', 'Dónde está la estación','Где находится станция','Está cerca','Это рядом'),
  ('Обычный день','Trabajo por la mañana. Como a la una. Por la tarde estudio español. Por la noche descanso.', 'por la mañana','утром','estudio español','я учу испанский'),
  ('Простой разговор','¿Por qué aprendes español? Porque quiero hablar con la gente. ¿Qué te gusta? Me gusta viajar.', 'Me gusta viajar','Мне нравится путешествовать','Porque','Потому что'),
 ]}


def units(language):
    result=[]
    for i,(title,passage,a,meaning_a,b,meaning_b) in enumerate(DATA[language],1):
        checks=[]
        for j,(expression,meaning) in enumerate(((a,meaning_a),(b,meaning_b))):
            checks.extend([
              {'id':f'q{j}','kind':'choice','prompt':'Как передать: '+meaning+'?',
               'options':[a,b] if j==0 else [b,a],'answers':[expression],'explanation':expression+' — '+meaning},
              {'id':f'd{j}','kind':'recall','prompt':'Вспомни выражение: '+meaning,'answers':[expression],
               'explanation':'Используй выражение из материала: '+expression}])
        result.append({'id':('en0' if language=='en' else 'es')+f'-{i:02}', 'language':language,'number':i,
                       'title':title,'passage':passage,'phrases':[{'front':a,'back':meaning_a},{'front':b,'back':meaning_b}],
                       'checks':checks,'speaking':'Прочитай вслух, затем замени имя, место или обстоятельства своими. Ответь двумя-тремя фразами без подсказки.',
                       'minutes':20,'source':'Авторский начальный материал. Для произношения нужны озвученные образцы; аудио здесь пока нет.'})
    return result
