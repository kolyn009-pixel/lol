"""Original low-stakes placement tasks; estimates reading/grammar only."""
from copy import deepcopy

SPECS={
 'A1':[
 ('She ___ a student.',['is','are','am'],'is'),
 ('We ___ coffee every morning.',['drinks','drink','drinking'],'drink'),
 ('___ you work here?',['Do','Does','Are'],'Do'),
 ('There are two ___ on the desk.',['book','books','booking'],'books'),
 ('I get up ___ seven.',['in','on','at'],'at'),
 ],
 'A2':[
 ('Yesterday I ___ to the station.',['go','went','have go'],'went'),
 ('This bag is ___ than mine.',['heavy','heavier','heaviest'],'heavier'),
 ('We ___ visit her tomorrow.',['are going to','did','was'],'are going to'),
 ('I have ___ money, so I can buy lunch.',['a little','a few','many'],'a little'),
 ('You ___ park here. It is forbidden.',['must not','do not have to','should'],'must not'),
 ],
 'B1':[
 ('I ___ here since 2022.',['have lived','live','am living'],'have lived'),
 ('If it rains, we ___ at home.',['will stay','would stayed','stayed'],'will stay'),
 ('The bridge ___ in 1990.',['was built','has building','built'],'was built'),
 ('She asked me where I ___.',['lived','do live','am live'],'lived'),
 ('I enjoy ___ new places.',['visiting','to visiting','visit'],'visiting'),
 ],
 'B2':[
 ('If I had known, I ___ you.',['would have called','would call yesterday','had call'],'would have called'),
 ('By next June, she ___ the course.',['will have finished','will finishing','has finish'],'will have finished'),
 ('He denied ___ the document.',['having seen','to have seen','see'],'having seen'),
 ('The report, ___ was published yesterday, contains new evidence.',['which','what','who'],'which'),
 ('You ___ told me earlier; now it is too late.',['should have','must to','would to'],'should have'),
 ]}
READING=[
 {'level':'A2','passage':'Maya works in a shop from Monday to Friday. On Saturday she visits her sister. This week her sister is away, so Maya plans to stay at home and read.',
  'prompt':'What is different this Saturday?','options':['Maya will stay home.','Maya will work in the shop.','Her sister will visit her.'],'answer':'Maya will stay home.'},
 {'level':'B1','passage':'A gym offered cheaper morning classes. Attendance increased, but evening classes remained popular with people who worked early. The gym decided to keep both schedules rather than replace the evening sessions.',
  'prompt':'Why keep both schedules?','options':['Different times suit different people.','Morning classes failed completely.','All evening classes were empty.'],'answer':'Different times suit different people.'},
 {'level':'B2','passage':'People who volunteered for a study reported better sleep after reducing screen use. However, they also changed their exercise routines. Without a comparison group, the researchers could not determine which change caused the improvement.',
  'prompt':'Which conclusion is justified?','options':['The cause of improvement remains uncertain.','Screen use was proved to be the only cause.','Exercise had no effect.'],'answer':'The cause of improvement remains uncertain.'},
]


def questions(keys=False):
    result=[]
    for band,items in SPECS.items():
        for i,(prompt,options,answer) in enumerate(items):
            result.append({'id':f'{band}-{i}','band':band,'skill':'grammar','prompt':prompt,'options':options,**({'answer':answer} if keys else {})})
    for i,q in enumerate(READING):
        result.append({'id':f'read-{i}','band':q['level'],'skill':'reading','passage':q['passage'],'prompt':q['prompt'],'options':q['options'],**({'answer':q['answer']} if keys else {})})
    return deepcopy(result)


def assess(answers):
    scores={b:0 for b in SPECS};reading={'correct':0,'total':3}
    for q in questions(True):
        if answers.get(q['id']) not in q['options']:raise ValueError('diagnostic_incomplete')
        if answers[q['id']]==q['answer']:
            if q['skill']=='grammar':scores[q['band']]+=1
            else:reading['correct']+=1
    band='A1'
    for current in ('A1','A2','B1','B2'):
        if scores[current]<4:break
        band={'A1':'A2','A2':'B1','B1':'B2','B2':'B2'}[current]
    return {'working_band':band,'grammar':scores,'reading':reading,
            'note':'Предварительная точка старта по грамматике и короткому чтению. Это не подтверждённый CEFR: аудирование, речь и письмо ещё не проверены.',
            'speaking_tasks':['Расскажи о себе за 30–60 секунд с опорами: I live… / I work or study… / I like…','Расскажи о вчерашнем дне и планах. Если можешь — сравни два способа учить язык и объясни свой выбор.']}
