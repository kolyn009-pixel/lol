/* Private learning workspace. Existing teacher screens remain mounted separately. */
(()=>{'use strict';
if(window.AdeliaSelfStudy)return;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rootId='selfStudyRoot';
const labels={unauthorized:'Войди в кабинет преподавателя, затем открой «Моё обучение».',cross_origin_forbidden:'Не удалось подтвердить запрос. Обнови страницу.',answer_all_questions:'Ответь на все вопросы перед проверкой.',invalid_daily_minutes:'Выбери два или три часа.',invalid_target_date:'Проверь дату цели.',invalid_answers:'Проверь ответы.',request_conflict:'Эта попытка уже сохранена с другими ответами. Открой урок заново.',lesson_not_found:'Этот урок не найден.',server_error:'Сервер не смог сохранить данные. Попробуй ещё раз.'};
Object.assign(labels,{stale_review:'Карточка уже обновлена на другом устройстве. Вернись к повторению.',card_not_due:'Для этой карточки повторение ещё не наступило.',card_not_found:'Карточка не найдена.',review_not_found:'Результат повторения не найден.',checkpoint_not_due:'Следующая работа с новым текстом пока недоступна.',no_new_checkpoints:'Все три новых варианта выполнены. Можно повторять знакомые.',checkpoint_finished:'Эта работа уже завершена. Вернись к программе.',checkpoint_not_found:'Контрольная работа не найдена.'});
let snapshot=null,language='en',currentLesson=null,generation=0,busy=false,dirty=false,submitId=null,lastPayload=null;
const root=()=>document.getElementById(rootId);
const status=text=>{const el=root()?.querySelector('[data-ss-status]');if(el)el.textContent=text;};
async function api(path='',body){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
 try{
  const response=await fetch('/api/teacher/self-study'+path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:controller.signal});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(labels[data.error]||'Не удалось выполнить действие. Обнови страницу и повтори.');
  return data;
 }catch(error){if(error.name==='AbortError')throw Error('Ответ сервера задержался. Можно повторить: одна попытка сохранится только один раз.');throw error;}
 finally{clearTimeout(timer);}
}
function uuid(){return globalThis.crypto?.randomUUID?.()||'10000000-1000-4000-8000-100000000000'.replace(/[018]/g,c=>(+c^crypto.getRandomValues(new Uint8Array(1))[0]&15>>+c/4).toString(16));}
function safeURL(raw){try{const u=new URL(raw);return u.protocol==='https:'?u.href:'#';}catch{return '#';}}
function canLeave(){return !dirty||confirm('Есть несохранённые ответы. Выйти без сохранения?');}
function mount(){
 let box=root();if(!box){box=document.createElement('section');box.id=rootId;box.className='ss-root';box.setAttribute('aria-label','Моё обучение');document.querySelector('#app')?.after(box);}
 if(!box)return null;
 document.body.classList.add('ss-open');
 document.querySelectorAll('aside nav button').forEach(x=>x.classList.remove('active'));
 document.querySelector('[data-self-study]')?.classList.add('active');
 const title=document.querySelector('#title');if(title)title.textContent='Моё обучение';
 box.hidden=false;return box;
}
function close(){generation++;root()?.remove();document.body.classList.remove('ss-open');document.querySelector('[data-self-study]')?.classList.remove('active');dirty=false;currentLesson=null;const url=new URL(location.href);url.searchParams.delete('study');history.replaceState(null,'',url);}
function errorView(error,retry){const box=root();if(!box)return;box.innerHTML=`<div class="ss-panel"><h2>Моё обучение</h2><p class="ss-error" role="alert">${esc(error.message)}</p><button class="ss-secondary" data-ss-retry>Повторить</button></div>`;box.querySelector('[data-ss-retry]').onclick=retry;}
async function open(){
 if(busy||!canLeave())return;
 dirty=false;currentLesson=null;const box=mount();if(!box)return;const version=++generation;
 box.innerHTML='<p class="ss-loading" role="status">Загружаю программу и результаты…</p>';
 const url=new URL(location.href);url.searchParams.set('study','1');history.replaceState(null,'',url);
 try{const data=await api();if(version!==generation)return;snapshot=data;renderHome();}
 catch(error){if(version===generation)errorView(error,open);}
}
const languageTabs=()=>`<div class="ss-tabs" aria-label="Язык">${Object.entries(snapshot.profile.languages).map(([code,item])=>`<button type="button" class="ss-tab" data-ss-language="${code}" aria-pressed="${language===code}">${esc(item.name)}</button>`).join('')}</div>`;
function renderHome(){
 const box=root();if(!box||!snapshot)return;currentLesson=null;dirty=false;
 const p=snapshot.profile.languages[language],course=snapshot.courses[language],next=course.find(x=>x.id===p.next_lesson),all=p.completed===p.total;
 box.innerHTML=`<section class="ss-hero"><div><span class="ss-eyebrow">Личная программа</span><h2>Понимать. Вспоминать. Применять.</h2><p>Английский для аспирантуры — главный приоритет. Немецкий и фарси получают своё время каждый день.</p></div><div class="ss-budget" aria-label="Время на все языки">${[120,180].map(n=>`<button type="button" data-ss-budget="${n}" aria-pressed="${snapshot.profile.daily_minutes===n}">${n/60} часа</button>`).join('')}</div></section>
 ${languageTabs()}
 ${["en","de"].includes(language)?'<div class="ss-actions" style="margin-bottom:18px"><button class="ss-secondary" data-ss-scenes>Журнал сцен и выражений</button></div>':''}
 <div class="ss-grid"><section class="ss-panel"><span class="ss-eyebrow">${all?'Следующий цикл':'Продолжить обучение'}</span><h3>${esc(next.title)}</h3><div class="ss-meta"><span class="ss-pill">${p.minutes} мин в день</span><span class="ss-muted">${esc(p.start)}</span></div><p class="ss-muted">${all?'Стартовые модули пройдены. Повтори их на новых примерах и используй внешние материалы.':'Материал → четыре задания → разбор ответов → устное применение с опорами.'}</p><div class="ss-actions"><button type="button" class="ss-primary" data-ss-lesson="${next.id}">${next.draft?'Продолжить сохранённое':all?'Вернуться к практике':'Начать занятие'}</button></div><progress max="${p.total}" value="${p.completed}" aria-label="Пройдено стартовых модулей"></progress><p class="ss-muted">${p.completed} из ${p.total} стартовых модулей · последнее выполнение не ниже 75%</p><div class="ss-note">${esc(snapshot.measurement_note)} Стартовые модули не заменяют полный курс до C1.</div></section>
 <section class="ss-panel"><span class="ss-eyebrow">Твой ориентир</span><h3>${esc(p.goal)}</h3><p class="ss-muted">Целевая дата: ${esc(p.target_date)}. Уровень пока указан по самооценке.</p><details><summary>Настроить даты</summary><form data-ss-goals class="ss-goals">${Object.entries(snapshot.profile.languages).map(([code,spec])=>`<label>${esc(spec.name)}<input type="date" name="${code}" value="${esc(spec.target_date)}" min="2026-01-01" max="2036-12-31" required></label>`).join('')}<button class="ss-secondary" type="submit">Сохранить даты</button></form></details><div class="ss-phase"><p><b>Ритм:</b> 5–10 минут повторения → новый материал → применение вслух.</p><p>Раз в четыре недели — короткая работа с новым текстом для сравнения результатов.</p></div><p data-ss-status class="ss-status" role="status"></p></section>
 <section class="ss-panel" data-ss-practice-panel><p role="status">Загружаю повторения…</p></section><section class="ss-panel" data-ss-checkpoint-panel><p role="status">Загружаю контрольные работы…</p></section><section class="ss-panel"><h3>Стартовые модули</h3><div class="ss-course">${course.map(item=>`<button type="button" class="ss-unit" data-ss-lesson="${item.id}" data-passed="${item.passed}"><span class="ss-unit-number">${item.passed?'✓':item.number}</span><span class="ss-unit-body"><strong>${esc(item.title)}</strong><small>${item.draft?'Есть сохранённые ответы · ':''}${item.latest?`Первая ${item.first.correct}/${item.first.total} · последняя ${item.latest.correct}/${item.latest.total} · попыток ${item.attempt_count}`:'Новый материал'}</small></span><span aria-hidden="true">→</span></button>`).join('')}</div></section>
 <section class="ss-panel"><h3>Маршрут подготовки</h3><ol class="ss-roadmap">${snapshot.roadmap[language].map(step=>`<li><small class="ss-eyebrow">${esc(step[0])}</small><strong>${esc(step[1])}</strong><span>${esc(step[2])}</span></li>`).join('')}</ol><p class="ss-muted">Даты маршрута рассчитаны на старт осенью 2026. При изменении дедлайна этапы нужно пересмотреть.</p><details><summary>Видео и сериалы для программы</summary>${snapshot.resources.filter(x=>x.language===language).map(x=>`<article class="ss-reference"><h4>${esc(x.title)}</h4><span class="ss-pill">${esc(x.level)}</span><p>${esc(x.why)}</p><p class="ss-muted">${esc(x.caution)}</p>${x.study_tasks?`<details><summary>Как заниматься по этому сериалу</summary><ol>${x.study_tasks.map(t=>`<li>${esc(t)}</li>`).join('')}</ol><p class="ss-muted">Подготовительный словарь — не цитаты из сериала и не подтверждение наличия слов в конкретной сцене.</p><div class="ss-phrases">${x.starter_terms.map(([a,b])=>`<div class="ss-phrase"><b>${esc(a)}</b><span>${esc(b)}</span></div>`).join('')}</div><button type="button" class="ss-secondary" data-ss-series-speak="${esc(x.id)}">Пересказать сцену голосом</button><p><b>Опоры для ответа:</b></p>${x.speaking_frames.map(t=>`<p>${esc(t)}</p>`).join('')}</details>`:''}<a href="${esc(safeURL(x.url))}" target="_blank" rel="noopener noreferrer">Открыть официальный источник ↗</a></article>`).join('')}<p class="ss-muted">Сцены и выражения сохраняются в журнале. Просмотр — на сервисе правообладателя, встроенного плеера нет.</p></details></section>
 <section class="ss-panel ss-full"><h3>История проверок</h3><p class="ss-muted">Первая попытка и повторы видны отдельно в карточках модулей. Здесь — последние сохранённые проверки выбранного языка.</p><div class="ss-history-wrap"><table class="ss-history"><thead><tr><th>Дата</th><th>Модуль</th><th>Результат</th></tr></thead><tbody>${snapshot.history.filter(x=>x.language===language).map(x=>`<tr><td>${esc(new Date(x.created_at).toLocaleString('ru-RU'))}</td><td>${esc(course.find(y=>y.id===x.lesson_id)?.title||x.lesson_id)}</td><td>${x.correct}/${x.total}</td></tr>`).join('')||'<tr><td colspan="3">Пока нет проверок. Начни с первого модуля.</td></tr>'}</tbody></table></div></section></div>`;
 bindHome();loadPracticePanels();
 box.querySelector('[data-ss-scenes]')?.addEventListener('click',()=>{if(busy||!canLeave())return;dirty=false;generation++;window.AdeliaStudyScenes?.open(root(),{language,resources:snapshot.resources,owner_id:snapshot.owner_id,back:open,dirty:value=>{dirty=value;},busy:value=>{busy=value;}});});
 box.querySelectorAll('[data-ss-series-speak]').forEach(b=>b.onclick=()=>{if(busy||!canLeave())return;const item=snapshot.resources.find(x=>x.id===b.dataset.ssSeriesSpeak);dirty=false;generation++;root().innerHTML='<button class="ss-secondary" data-ss-home>← К программе</button>';root().querySelector('button').onclick=open;mountVoice({id:'series:'+item.id,language:item.language,speaking:item.study_tasks.join(' \n')});});
}
function bindHome(){
 const box=root();box.querySelectorAll('[data-ss-language]').forEach(b=>b.onclick=()=>{if(busy)return;language=b.dataset.ssLanguage;renderHome();});
 box.querySelectorAll('[data-ss-lesson]').forEach(b=>b.onclick=()=>loadLesson(b.dataset.ssLesson));
 box.querySelectorAll('[data-ss-budget]').forEach(b=>b.onclick=()=>saveSettings({daily_minutes:Number(b.dataset.ssBudget)}));
 box.querySelector('[data-ss-goals]').onsubmit=e=>{e.preventDefault();saveSettings({daily_minutes:snapshot.profile.daily_minutes,target_dates:Object.fromEntries(new FormData(e.currentTarget))});};
}
async function saveSettings(body){
 if(busy)return;busy=true;const version=generation;status('Сохраняю…');
 root().querySelectorAll('[data-ss-budget], [data-ss-goals] button').forEach(b=>b.disabled=true);
 try{const p=await api('/profile',body);if(version!==generation)return;snapshot.profile=p;renderHome();status('Настройки сохранены.');}
 catch(error){if(version===generation)status(error.message);}
 finally{busy=false;if(version===generation)root()?.querySelectorAll('[data-ss-budget], [data-ss-goals] button').forEach(b=>b.disabled=false);}
}
async function loadLesson(id){
 if(busy||!canLeave())return;const version=++generation;dirty=false;
 root().innerHTML='<p class="ss-loading" role="status">Загружаю занятие…</p>';
 try{const data=await api('/lesson?id='+encodeURIComponent(id));if(version!==generation)return;currentLesson=data;language=data.language;submitId=uuid();lastPayload=null;renderLesson();}
 catch(error){if(version===generation)errorView(error,()=>loadLesson(id));}
}
function renderLesson(){
 const item=currentLesson,fa=item.language==='fa',box=root();
 box.innerHTML=`<div class="ss-heading"><button type="button" class="ss-secondary" data-ss-back>← К программе</button><span class="ss-muted">${esc(snapshot.profile.languages[item.language].name)} · модуль ${item.number}</span></div>
 <section class="ss-panel"><span class="ss-eyebrow">Сначала с опорой, затем самостоятельно</span><h2>${esc(item.title)}</h2><p class="ss-muted">Прочитай материал. Если слово непонятно, словарь разрешён. Затем закрой материал и попробуй вспомнить выражения.</p><details open data-ss-material><summary>Материал и выражения</summary><div class="ss-reading" lang="${item.language}" dir="${fa?'rtl':'ltr'}">${esc(item.passage)}</div><div class="ss-phrases">${item.phrases.map(x=>`<div class="ss-phrase"><b lang="${item.language}" dir="${fa?'rtl':'auto'}">${esc(x.front)}</b><span>${esc(x.back)}</span></div>`).join('')}</div><p class="ss-muted">${esc(item.source)}</p></details>
 <form data-ss-check><h3>Проверка понимания и памяти</h3><p class="ss-muted">Два вопроса по содержанию и два коротких ответа. Это учебная проверка с возможностью подсмотреть материал, а не независимый экзамен.</p>${item.checks.map((q,i)=>`<fieldset><legend>${i+1}. ${esc(q.prompt)}</legend>${q.kind==='choice'?q.options.map((option,j)=>`<label class="ss-choice"><input type="radio" name="${q.id}" value="${esc(option)}" required ${item.draft[q.id]===option?'checked':''}><span>${esc(option)}</span></label>`).join(''):`<label>Твой короткий ответ<input type="text" name="${q.id}" value="${esc(item.draft[q.id]||'')}" maxlength="1000" autocomplete="off" spellcheck="false" dir="${fa?'rtl':'auto'}" lang="${item.language}" required></label>`}</fieldset>`).join('')}
 <div class="ss-actions"><button type="submit" class="ss-primary">Проверить ответы</button><button type="button" class="ss-secondary" data-ss-save>Сохранить и продолжить позже</button></div><p class="ss-status" data-ss-status role="status">${item.draft_saved_at?'Восстановлены ответы, сохранённые '+esc(new Date(item.draft_saved_at).toLocaleString('ru-RU')):''}</p></form>
 <div class="ss-note"><b>Устное применение:</b> ${esc(item.speaking)}<br>На этом этапе выполни вслух самостоятельно. Автоматическая проверка речи появится позже.</div></section>`;
 box.querySelector('[data-ss-back]').onclick=open;
 const form=box.querySelector('form');
 form.oninput=()=>{dirty=true;if(lastPayload){submitId=uuid();lastPayload=null;}status('Есть несохранённые изменения.');};
 box.querySelector('[data-ss-save]').onclick=saveDraft;
 form.onsubmit=e=>{e.preventDefault();submitLesson();};mountVoice(item);
}
function collect(){return Object.fromEntries(new FormData(root().querySelector('[data-ss-check]')));}
function formBusy(value){root()?.querySelectorAll('form input,form button,[data-ss-back]').forEach(x=>x.disabled=value);}
async function saveDraft(){
 if(busy)return;busy=true;const version=generation,body={lesson_id:currentLesson.id,answers:collect()};formBusy(true);status('Сохраняю ответы…');
 try{await api('/draft',body);if(version!==generation)return;dirty=false;status('Ответы сохранены на сервере. Можно вернуться позже с любого устройства.');}
 catch(error){if(version===generation)status(error.message);}
 finally{busy=false;if(version===generation)formBusy(false);}
}
async function submitLesson(){
 if(busy)return;
 const body={lesson_id:currentLesson.id,answers:collect(),request_id:submitId};lastPayload=body;
 busy=true;const version=generation;formBusy(true);status('Проверяю и сохраняю…');
 try{const result=await api('/submit',body);if(version!==generation)return;dirty=false;renderResult(result);}
 catch(error){if(version===generation)status(error.message);}
 finally{busy=false;if(version===generation)formBusy(false);}
}
function renderResult(result){
 const item=currentLesson;root().innerHTML=`<section class="ss-panel"><span class="ss-eyebrow">Результат сохранён</span><h2>${esc(item.title)}</h2><div class="ss-result">${result.correct}<span class="ss-muted"> / ${result.total}</span></div><p>${result.passed?'Можно двигаться дальше. Попробуй применить выражения в своей ситуации.':'Вернись к объяснениям ниже и попробуй ещё раз после перерыва.'}</p><p class="ss-muted">${esc(result.note)} · попытка ${result.attempt_number}. Результат относится только к этим заданиям.</p>${result.results.map(x=>`<article class="ss-feedback" data-correct="${x.correct}"><b>${x.correct?'✓ Верно':'Нужно повторить'} · ${esc(x.prompt)}</b><p>Твой ответ: <bdi>${esc(x.submitted)}</bdi></p>${!x.correct?`<p>Ожидаемый ответ: <bdi>${esc(x.expected)}</bdi></p>`:''}<p>${esc(x.explanation)}</p></article>`).join('')}<div class="ss-note"><b>Теперь вслух:</b> ${esc(item.speaking)}</div><div class="ss-actions"><button type="button" class="ss-primary" data-ss-home>К программе</button><button type="button" class="ss-secondary" data-ss-again>Повторить модуль</button></div></section>`;
 root().querySelector('[data-ss-home]').onclick=open;root().querySelector('[data-ss-again]').onclick=()=>loadLesson(item.id);mountVoice(item);
}
const errorStates={OPEN:'Повторить',PRACTICING:'Закрепляется',RESOLVED:'Закреплено в разные дни'};
const when=value=>value?new Date(value).toLocaleString('ru-RU'):'';
async function loadPracticePanels(){
 const code=language,panel=root()?.querySelector('[data-ss-practice-panel]'),checks=root()?.querySelector('[data-ss-checkpoint-panel]');
 if(!panel||!checks)return;
 await Promise.allSettled([
  (async()=>{try{
   const data=await api('/practice?language='+code);if(!panel.isConnected||language!==code)return;
   panel.innerHTML=`<span class="ss-eyebrow">Повторение по памяти</span><h3>${data.due?`${data.due} карточек на сегодня`:'На сегодня всё повторено'}</h3><p class="ss-muted">${data.total?`Всего выражений и заданий: ${data.total}.`:'После первого выполненного модуля здесь появятся выражения.'} ${esc(data.note)}</p>${data.due?'<button type="button" class="ss-primary" data-ss-review>Начать повторение</button>':data.next_due_at?`<p class="ss-muted">Следующее повторение: ${esc(when(data.next_due_at))}</p>`:''}<details><summary>Журнал ошибок · ${data.errors.filter(x=>x.status!=='RESOLVED').length} в работе</summary>${data.errors.map(x=>`<article class="ss-reference"><b>${esc(x.topic)}</b><p>${esc(errorStates[x.status])} · ошибок в уроке: ${x.wrong_count}</p><button type="button" class="ss-secondary" data-ss-fix="${esc(x.lesson_id)}">Вернуться к модулю</button></article>`).join('')||'<p class="ss-muted">Ошибок в выполненных заданиях пока нет.</p>'}</details>`;
   panel.querySelector('[data-ss-review]')?.addEventListener('click',loadPractice);
   panel.querySelectorAll('[data-ss-fix]').forEach(b=>b.onclick=()=>loadLesson(b.dataset.ssFix));
  }catch(error){if(panel.isConnected){panel.innerHTML=`<h3>Повторение</h3><p class="ss-error" role="alert">${esc(error.message)}</p><button class="ss-secondary" data-ss-panel-retry>Повторить загрузку</button>`;panel.querySelector('button').onclick=loadPracticePanels;}}})(),
  (async()=>{try{
   const data=await api('/checkpoint/status?language='+code);if(!checks.isConnected||language!==code)return;
   const firsts=data.results.filter(x=>x.fresh),latest=firsts.at(-1);
   const focus=latest?(latest.skills.recall.correct<latest.skills.comprehension.correct?'В следующей неделе удели больше времени воспроизведению выражений.':'Чередуй чтение новых материалов и пересказ без подсказок.'):'Первая работа даст исходную точку для будущих сравнений.';
   checks.innerHTML=`<span class="ss-eyebrow">Проверка раз в четыре недели</span><h3>Новый текст — знакомые навыки</h3><p class="ss-muted">${esc(data.note)}</p><div class="ss-actions">${data.active_id||data.new_available?`<button type="button" class="ss-primary" data-ss-checkpoint>${data.active_id?'Продолжить контрольную':'Начать контрольную'}</button>`:data.next_new_at?`<p class="ss-muted">Следующий новый вариант: ${esc(when(data.next_new_at))}</p>`:'<p class="ss-muted">Все новые варианты стартового набора выполнены.</p>'}</div>${data.results.length?`<div class="ss-history-wrap"><table class="ss-history"><thead><tr><th>Работа</th><th>Чтение</th><th>Воспроизведение</th></tr></thead><tbody>${data.results.map(x=>`<tr><td>${esc(x.form_id)} · ${x.fresh?'новый текст':'повтор'}<br><small>${esc(when(x.completed_at))}</small></td><td>${x.skills.comprehension.correct}/${x.skills.comprehension.total}</td><td>${x.skills.recall.correct}/${x.skills.recall.total}</td></tr>`).join('')}</tbody></table></div>`:''}<p class="ss-muted">${esc(focus)} Повторы знакомых вариантов не включай в сравнение первых работ.</p>${data.practice_forms.length?`<details><summary>Потренироваться на знакомом варианте</summary><div class="ss-actions">${data.practice_forms.map(id=>`<button type="button" class="ss-secondary" data-ss-checkpoint-practice="${esc(id)}">${esc(id)} · повтор</button>`).join('')}</div></details>`:''}`;
   checks.querySelector('[data-ss-checkpoint]')?.addEventListener('click',()=>loadCheckpoint());
   checks.querySelectorAll('[data-ss-checkpoint-practice]').forEach(b=>b.onclick=()=>loadCheckpoint(b.dataset.ssCheckpointPractice));
  }catch(error){if(checks.isConnected){checks.innerHTML=`<h3>Контрольная работа</h3><p class="ss-error" role="alert">${esc(error.message)}</p><button class="ss-secondary">Повторить загрузку</button>`;checks.querySelector('button').onclick=loadPracticePanels;}}})()
 ]);
}
async function loadPractice(){
 if(busy||!canLeave())return;dirty=false;currentLesson=null;const version=++generation;
 root().innerHTML='<p class="ss-loading" role="status">Собираю повторения…</p>';
 try{const data=await api('/practice?language='+language);if(version===generation)renderReview(data);}
 catch(error){if(version===generation)errorView(error,loadPractice);}
}
function renderReview(data){
 const card=data.items[0],box=root();
 if(!card){box.innerHTML=`<section class="ss-panel"><span class="ss-eyebrow">Повторение</span><h2>На сейчас всё готово</h2><p class="ss-muted">${data.next_due_at?`Следующая карточка: ${esc(when(data.next_due_at))}`:'Пройди новый модуль, чтобы добавить выражения.'}</p><button class="ss-primary" data-ss-home>К программе</button></section>`;box.querySelector('button').onclick=open;return;}
 let requestId=uuid();
 box.innerHTML=`<div class="ss-heading"><button class="ss-secondary" type="button" data-ss-back>← К программе</button><span class="ss-muted">Сейчас к повторению: ${data.due}</span></div><section class="ss-panel"><span class="ss-eyebrow">${card.source==='error'?'Работа над ошибкой':'Вспомни выражение'}</span><h2>${esc(card.prompt)}</h2><p class="ss-muted">${card.options.length?'Выбери ответ. Здесь проверяется узнавание смысла.':'Воспроизведи короткое выражение на изучаемом языке без словаря и подсказки.'}</p><form data-ss-card-form>${card.options.length?card.options.map(option=>`<label class="ss-choice"><input type="radio" name="answer" value="${esc(option)}" required><span>${esc(option)}</span></label>`).join(''):`<label>Твой ответ<input type="text" name="answer" maxlength="1000" lang="${language}" dir="${language==='fa'?'rtl':'auto'}" autocomplete="off" required></label>`}<div class="ss-actions"><button class="ss-primary" type="submit">Проверить выражение</button></div></form><div data-ss-reveal></div><p data-ss-status class="ss-status" role="status"></p></section>`;
 box.querySelector('[data-ss-back]').onclick=open;
 const form=box.querySelector('form');form.oninput=()=>{dirty=true;requestId=uuid();};
 form.onsubmit=async event=>{
  event.preventDefault();if(busy)return;
  const answer=new FormData(form).get('answer'),version=generation;busy=true;formBusy(true);status('Проверяю…');
  try{const result=await api('/review/answer',{card_id:card.id,version:card.version,answer,request_id:requestId});if(version!==generation)return;dirty=false;showReveal(result);}
  catch(error){if(version===generation)status(error.message);}
  finally{busy=false;if(version===generation)formBusy(false);}
 };
 function showReveal(result){
  form.hidden=true;status('');const reveal=box.querySelector('[data-ss-reveal]');
  reveal.innerHTML=`<article class="ss-feedback" data-correct="${result.correct}"><b>${result.correct?'Вспомнил верно':'Вернись к выражению'}</b><p>Твой ответ: <bdi>${esc(result.submitted)}</bdi></p><p>Выражение: <bdi lang="${language}" dir="${language==='fa'?'rtl':'auto'}">${esc(result.expected)}</bdi></p><p>${esc(result.explanation)}</p></article><p class="ss-muted">${esc(result.note)}</p><div class="ss-actions"><button class="ss-secondary" data-ss-rating="again">Повторить через 10 минут</button><button class="ss-secondary" data-ss-rating="hard" ${result.correct?'':'disabled'}>Верно, но трудно · завтра</button><button class="ss-primary" data-ss-rating="good" ${result.correct?'':'disabled'}>Вспомнил уверенно</button></div>`;
  reveal.querySelectorAll('[data-ss-rating]').forEach(b=>b.onclick=async()=>{
   if(busy)return;busy=true;const version=generation;reveal.querySelectorAll('button').forEach(x=>x.disabled=true);status('Сохраняю следующее повторение…');
   try{await api('/review/rate',{review_id:result.review_id,rating:b.dataset.ssRating});const next=await api('/practice?language='+language);if(version===generation)renderReview(next);}
   catch(error){if(version===generation)status(error.message);}
   finally{busy=false;if(reveal.isConnected)reveal.querySelectorAll('[data-ss-rating]').forEach(x=>x.disabled=!result.correct&&x.dataset.ssRating!=='again');}
  });
 }
 if(card.pending)showReveal(card.pending);
}
let activeCheckpoint=null;
async function loadCheckpoint(practiceForm){
 if(busy||!canLeave())return;dirty=false;currentLesson=null;const version=++generation;
 root().innerHTML='<p class="ss-loading" role="status">Открываю контрольную…</p>';
 try{const data=await api('/checkpoint/start',{language,...(practiceForm?{practice_form:practiceForm}:{})});if(version!==generation)return;activeCheckpoint=data;renderCheckpoint();}
 catch(error){if(version===generation)errorView(error,()=>loadCheckpoint(practiceForm));}
}
function renderCheckpoint(){
 const item=activeCheckpoint,fa=item.language==='fa';
 root().innerHTML=`<div class="ss-heading"><button class="ss-secondary" data-ss-back>← К программе</button><span class="ss-pill">${esc(item.id)} · ${item.fresh?'первая работа с текстом':'знакомый вариант'}</span></div><section class="ss-panel"><h2>Короткая контрольная</h2><p class="ss-muted">Прочитай новый текст и ответь на шесть вопросов. Для сопоставимости выполняй без словаря. Подсказки и правильные ответы появятся после отправки. Это проверка чтения и коротких выражений, не экзамен на уровень.</p><div class="ss-reading" lang="${item.language}" dir="${fa?'rtl':'ltr'}">${esc(item.passage)}</div><form data-ss-checkpoint-form>${item.checks.map((q,index)=>`<fieldset><legend>${index+1}. ${esc(q.prompt)}</legend>${q.kind==='choice'?q.options.map(option=>`<label class="ss-choice"><input type="radio" name="${q.id}" value="${esc(option)}" required ${item.answers[q.id]===option?'checked':''}><span>${esc(option)}</span></label>`).join(''):`<label>Короткий ответ<input type="text" name="${q.id}" maxlength="1000" value="${esc(item.answers[q.id]||'')}" lang="${item.language}" dir="${fa?'rtl':'auto'}" autocomplete="off" required></label>`}</fieldset>`).join('')}<div class="ss-actions"><button type="submit" class="ss-primary">Завершить контрольную</button><button type="button" class="ss-secondary" data-ss-checkpoint-save>Сохранить ответы</button></div><p data-ss-status class="ss-status" role="status"></p></form></section>`;
 root().querySelector('[data-ss-back]').onclick=open;
 const form=root().querySelector('form');form.oninput=()=>{dirty=true;};
 root().querySelector('[data-ss-checkpoint-save]').onclick=()=>persistCheckpoint(false);
 form.onsubmit=event=>{event.preventDefault();persistCheckpoint(true);};
}
async function persistCheckpoint(complete){
 if(busy)return;const form=root().querySelector('[data-ss-checkpoint-form]');
 const body={attempt_id:activeCheckpoint.attempt_id,answers:Object.fromEntries(new FormData(form))};
 busy=true;const version=generation;formBusy(true);status('Сохраняю…');
 try{const result=await api('/checkpoint/'+(complete?'submit':'draft'),body);if(version!==generation)return;dirty=false;if(complete)renderCheckpointResult(result);else status('Ответы сохранены. Можно продолжить позже.');}
 catch(error){if(version===generation)status(error.message);}
 finally{busy=false;if(version===generation)formBusy(false);}
}
function renderCheckpointResult(result){
 root().innerHTML=`<section class="ss-panel"><span class="ss-eyebrow">Контрольная сохранена · ${result.fresh?'первая работа с текстом':'повтор знакомого варианта'}</span><h2>${esc(result.form_id)}</h2><div class="ss-result">${result.correct} / ${result.total}</div><div class="ss-meta"><span class="ss-pill">Чтение ${result.skills.comprehension.correct}/3</span><span class="ss-pill">Воспроизведение ${result.skills.recall.correct}/3</span></div><p class="ss-muted">Сравнивай первые работы на разных текстах отдельно от повторов. На три вопроса по навыку влияет случайность; этот результат не определяет CEFR.</p>${result.results.map(x=>`<article class="ss-feedback" data-correct="${x.correct}"><b>${x.correct?'✓ Верно':'Повторить'} · ${esc(x.prompt)}</b><p>Твой ответ: <bdi>${esc(x.submitted)}</bdi></p>${x.correct?'':`<p>Ожидаемый ответ: <bdi>${esc(x.expected)}</bdi></p>`}<p>${esc(x.explanation)}</p></article>`).join('')}<button class="ss-primary" data-ss-home>К программе</button></section>`;
 root().querySelector('[data-ss-home]').onclick=open;
}
function mountVoice(item){const box=document.createElement('div');box.style.marginTop='18px';root().appendChild(box);window.AdeliaStudyVoice?.mount(box,{owner_id:snapshot.owner_id,lesson_id:item.id,language:item.language,prompt:item.speaking});}
function installButton(){
 const nav=document.querySelector('.teacher-shell aside nav');if(!nav||nav.querySelector('[data-self-study]'))return;
 const button=document.createElement('button');button.type='button';button.dataset.selfStudy='';button.innerHTML='<span class="ico">◈</span><span>Моё обучение</span>';
 const more=nav.querySelector('.teacher-more');if(more)more.before(button);else nav.appendChild(button);
}
document.addEventListener('click',event=>{
 const button=event.target.closest?.('[data-self-study]');if(button){event.preventDefault();event.stopImmediatePropagation();open();return;}
 const other=event.target.closest?.('aside nav [data-view], aside nav [data-learning-open], header [data-view]');
 if(other&&root()){if(busy||!canLeave()){event.preventDefault();event.stopImmediatePropagation();return;}close();}
},true);
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
window.addEventListener('adelia:teacher-login',installButton);
window.addEventListener('adelia:desktop-ui-ready',installButton);
function init(){installButton();if(new URL(location.href).searchParams.get('study')==='1')open();}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
window.AdeliaSelfStudy={open,close};
})();
