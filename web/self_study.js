/* Private learning workspace. Existing teacher screens remain mounted separately. */
(()=>{'use strict';
if(window.AdeliaSelfStudy)return;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rootId='selfStudyRoot';
const labels={unauthorized:'Войди в кабинет преподавателя, затем открой «Моё обучение».',cross_origin_forbidden:'Не удалось подтвердить запрос. Обнови страницу.',answer_all_questions:'Ответь на все четыре вопроса перед проверкой.',invalid_daily_minutes:'Выбери два или три часа.',invalid_target_date:'Проверь дату цели.',invalid_answers:'Проверь ответы.',request_conflict:'Эта попытка уже сохранена с другими ответами. Открой урок заново.',lesson_not_found:'Этот урок не найден.',server_error:'Сервер не смог сохранить данные. Попробуй ещё раз.'};
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
 box.innerHTML=`<section class="ss-hero"><div><span class="ss-eyebrow">Личная программа · этап 1</span><h2>Понимать. Вспоминать. Применять.</h2><p>Английский для аспирантуры — главный приоритет. Немецкий и фарси получают своё время каждый день.</p></div><div class="ss-budget" aria-label="Время на все языки">${[120,180].map(n=>`<button type="button" data-ss-budget="${n}" aria-pressed="${snapshot.profile.daily_minutes===n}">${n/60} часа</button>`).join('')}</div></section>
 ${languageTabs()}
 <div class="ss-grid"><section class="ss-panel"><span class="ss-eyebrow">${all?'Следующий цикл':'Продолжить обучение'}</span><h3>${esc(next.title)}</h3><div class="ss-meta"><span class="ss-pill">${p.minutes} мин в день</span><span class="ss-muted">${esc(p.start)}</span></div><p class="ss-muted">${all?'Стартовые модули пройдены. Повтори их на новых примерах и используй внешние материалы.':'Материал → четыре задания → разбор ответов → устное применение с опорами.'}</p><div class="ss-actions"><button type="button" class="ss-primary" data-ss-lesson="${next.id}">${next.draft?'Продолжить сохранённое':all?'Вернуться к практике':'Начать занятие'}</button></div><progress max="${p.total}" value="${p.completed}" aria-label="Пройдено стартовых модулей"></progress><p class="ss-muted">${p.completed} из ${p.total} стартовых модулей · последнее выполнение не ниже 75%</p><div class="ss-note">${esc(snapshot.measurement_note)} Стартовые модули не заменяют полный курс до C1.</div></section>
 <section class="ss-panel"><span class="ss-eyebrow">Твой ориентир</span><h3>${esc(p.goal)}</h3><p class="ss-muted">Целевая дата: ${esc(p.target_date)}. Уровень пока указан по самооценке.</p><details><summary>Настроить даты</summary><form data-ss-goals class="ss-goals">${Object.entries(snapshot.profile.languages).map(([code,spec])=>`<label>${esc(spec.name)}<input type="date" name="${code}" value="${esc(spec.target_date)}" min="2026-01-01" max="2036-12-31" required></label>`).join('')}<button class="ss-secondary" type="submit">Сохранить даты</button></form></details><div class="ss-phase"><p><b>Сейчас:</b> программа, задания, черновики и история.</p><p>Далее: повторения и независимые проверки → голос → занятия по сериалам.</p></div><p data-ss-status class="ss-status" role="status"></p></section>
 <section class="ss-panel"><h3>Стартовые модули</h3><div class="ss-course">${course.map(item=>`<button type="button" class="ss-unit" data-ss-lesson="${item.id}" data-passed="${item.passed}"><span class="ss-unit-number">${item.passed?'✓':item.number}</span><span class="ss-unit-body"><strong>${esc(item.title)}</strong><small>${item.draft?'Есть сохранённые ответы · ':''}${item.latest?`Первая ${item.first.correct}/${item.first.total} · последняя ${item.latest.correct}/${item.latest.total} · попыток ${item.attempt_count}`:'Новый материал'}</small></span><span aria-hidden="true">→</span></button>`).join('')}</div></section>
 <section class="ss-panel"><h3>Маршрут подготовки</h3><ol class="ss-roadmap">${snapshot.roadmap[language].map(step=>`<li><small class="ss-eyebrow">${esc(step[0])}</small><strong>${esc(step[1])}</strong><span>${esc(step[2])}</span></li>`).join('')}</ol><p class="ss-muted">Даты маршрута рассчитаны на старт осенью 2026. При изменении дедлайна этапы нужно пересмотреть.</p><details><summary>Видео и сериалы для программы</summary>${snapshot.resources.filter(x=>x.language===language).map(x=>`<article class="ss-reference"><h4>${esc(x.title)}</h4><span class="ss-pill">${esc(x.level)}</span><p>${esc(x.why)}</p><p class="ss-muted">${esc(x.caution)}</p><a href="${esc(safeURL(x.url))}" target="_blank" rel="noopener noreferrer">Открыть официальный источник ↗</a></article>`).join('')}<p class="ss-muted">Разбор сцен и журнал просмотра появятся на этапе 4. Встроенного плеера сейчас нет.</p></details></section>
 <section class="ss-panel ss-full"><h3>История проверок</h3><p class="ss-muted">Первая попытка и повторы видны отдельно в карточках модулей. Здесь — последние сохранённые проверки выбранного языка.</p><div class="ss-history-wrap"><table class="ss-history"><thead><tr><th>Дата</th><th>Модуль</th><th>Результат</th></tr></thead><tbody>${snapshot.history.filter(x=>x.language===language).map(x=>`<tr><td>${esc(new Date(x.created_at).toLocaleString('ru-RU'))}</td><td>${esc(course.find(y=>y.id===x.lesson_id)?.title||x.lesson_id)}</td><td>${x.correct}/${x.total}</td></tr>`).join('')||'<tr><td colspan="3">Пока нет проверок. Начни с первого модуля.</td></tr>'}</tbody></table></div></section></div>`;
 bindHome();
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
 form.onsubmit=e=>{e.preventDefault();submitLesson();};
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
 root().querySelector('[data-ss-home]').onclick=open;root().querySelector('[data-ss-again]').onclick=()=>loadLesson(item.id);
}
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
