const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>Number(n||0).toLocaleString('ru-RU')+' ₽';
const titles={home:'Главная',schedule:'Занятия',homework:'Домашка',payments:'Оплата',messages:'Сообщения',profile:'Профиль',studentLogin:'Вход'};
let auth=null;
let current='home';

async function api(path,opt={}){
  const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});
  const j=await r.json().catch(()=>({}));
  if(!r.ok){const e=new Error(j.error||'Ошибка');e.status=r.status;throw e}
  return j;
}
function fmtDate(v){if(!v)return '—';const d=new Date(v);return new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short'}).format(d)}
function fmtTime(v){if(!v)return '—';const d=new Date(v);return new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit'}).format(d)}
function subjectName(v){return ({PHYSICS:'Физика',CHEMISTRY:'Химия'})[String(v||'').toUpperCase()]||v||'Занятие'}
function goalName(v){return ({EGE:'ЕГЭ',OGE:'ОГЭ',SCHOOL:'Школьный курс',OLYMPIAD:'Олимпиадная подготовка'})[String(v||'').toUpperCase()]||v||''}
function payStatus(v){return ({PAID:'Оплачено',AWAITING_PAYMENT:'Ожидает оплаты',WAITING:'Ожидает оплаты',PENDING:'На проверке',CONFIRMED:'Подтверждено',CANCELLED:'Отменено'})[String(v||'').toUpperCase()]||v||'—'}
function lessonStatus(v){return ({CONFIRMED:'Подтверждено',PENDING:'Ожидает подтверждения',IN_PROGRESS:'Идёт занятие',COMPLETED:'Завершено',CANCELLED:'Отменено',REJECTED:'Отклонено'})[String(v||'').toUpperCase()]||v||'—'}
function loading(){return '<div class="skeleton-stack"><div class="skeleton hero-skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>'}
function authCard(){return `<section class="form-card auth-card"><span class="status">Аделия 💜</span><h2>Вход в личный кабинет</h2><p>Получите одноразовый код в TutorBot и введите его здесь. Код действует 10 минут.</p><label>Код из бота</label><input class="code-input" id="loginCode" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000"><button class="form-primary" id="studentLoginButton">Войти</button><div id="loginResult"></div></section>`}

async function ensureAuth(){
  try{const d=await api('/auth/me');auth=d.session||null}catch{auth=null}
  if(auth?.role==='teacher'){location.href='/teacher/';return false}
  return !!(auth&&auth.role==='student');
}

async function home(){
  const d=await api('/student/dashboard');
  const s=d.student||{};const l=d.next_lesson;
  const next=l?`${subjectName(l.subject)} · ${fmtDate(l.start_time)} в ${fmtTime(l.start_time)} · ${l.duration_minutes||60} мин`:'Ближайших занятий пока нет';
  const cta=l?`<button class="primary-btn" data-lesson="${l.id}">${l.started_at?'Вернуться к занятию':'Открыть занятие'}</button>`:`<button class="primary-btn" data-go="schedule">Расписание</button>`;
  const recent=d.recent_result?`<section class="section"><h3>Последний результат</h3><article class="task-card done"><span class="status">Проверено</span><h3>${esc(d.recent_result.title||'Домашняя работа')}</h3><p>${d.recent_result.accuracy_percent!=null?`Результат: <b>${esc(d.recent_result.accuracy_percent)}%</b>`:esc(d.recent_result.result||'Проверено')}</p></article></section>`:'';
  return `<section class="welcome"><p>${esc(s.name||'Ученик')}, добро пожаловать 💜</p><h2>${l?'Следующее занятие':'Всё под контролем'}</h2><span>${esc(next)}</span>${cta}</section><section class="quick-actions"><button class="action-card" data-go="schedule"><span>📅</span><b>Расписание</b><small>${l?fmtDate(l.start_time)+' · '+fmtTime(l.start_time):'Нет ближайших занятий'}</small></button><button class="action-card" data-go="homework"><span>📚</span><b>Домашка</b><small>${d.active_homework} активных заданий</small></button><button class="action-card" data-go="payments"><span>💳</span><b>Оплата</b><small>${d.payments_waiting?`${money(d.payments_waiting_amount)} ожидает`:`Баланс ${s.extra_minutes_balance||0} мин`}</small></button><button class="action-card" data-go="messages"><span>💬</span><b>Сообщения</b><small>${d.unread_messages?`${d.unread_messages} новых`:'Связь с преподавателем'}</small></button></section>${recent}`;
}

async function schedule(){
  const d=await api('/student/schedule?limit=60');
  const items=d.items||[];const now=Date.now();
  const upcoming=items.filter(x=>new Date(x.start_time).getTime()>=now&&!['cancelled','completed'].includes(x.ui_state)).sort((a,b)=>new Date(a.start_time)-new Date(b.start_time));
  const past=items.filter(x=>!upcoming.includes(x)).slice(0,20);
  const card=x=>`<article class="list-card lesson-card state-${esc(x.ui_state)}" data-lesson="${x.id}"><div class="date-badge"><b>${new Date(x.start_time).getDate()}</b><span>${new Intl.DateTimeFormat('ru-RU',{month:'short'}).format(new Date(x.start_time))}</span></div><div class="list-copy"><b>${esc(subjectName(x.subject))}${x.study_goal?' · '+esc(goalName(x.study_goal)):''}</b><span>${fmtTime(x.start_time)}–${fmtTime(x.end_time)} · ${x.duration_minutes||60} мин</span><small>${esc(lessonStatus(x.lesson_status))} · ${esc(payStatus(x.payment_status))}</small></div><button class="mini-btn">Открыть</button></article>`;
  return `<div class="segmented"><button class="active" data-schedule-tab="future">Предстоящие</button><button data-schedule-tab="past">Прошедшие</button></div><section class="section schedule-pane" id="futurePane"><h3>Ближайшие занятия</h3>${upcoming.map(card).join('')||'<div class="empty">Предстоящих занятий пока нет.</div>'}</section><section class="section schedule-pane hidden" id="pastPane"><h3>История</h3>${past.map(card).join('')||'<div class="empty">История занятий пока пуста.</div>'}</section>`;
}

async function payments(){
  const d=await api('/student/payments');const b=d.balance||{};const items=d.items||[];const receipts=d.receipts||[];
  return `<section class="balance"><small>Баланс занятий</small><b>${b.extra_minutes||0} минут</b><span>${b.bonus_lessons?`Бонусных занятий: ${b.bonus_lessons}`:'Минуты доступны для следующих занятий'}</span></section><section class="section"><h3>Платежи</h3>${items.map(x=>`<article class="payment"><div><b>${x.payment_type==='PACKAGE'?'Абонемент':'Оплата занятия'}</b><span>${fmtDate(x.created_at)} · ${esc(payStatus(x.status))}${x.minutes_total?` · ${x.minutes_total} мин`:''}</span></div><strong>${money(x.total_amount)}</strong></article>`).join('')||'<div class="empty">Платежей пока нет.</div>'}</section><section class="section"><h3>Чеки</h3>${receipts.map(x=>`<article class="payment"><div><b>Чек #${x.id}</b><span>${fmtDate(x.created_at)} · ${esc(payStatus(x.status))}</span></div><strong>${esc(x.source_platform||'')}</strong></article>`).join('')||'<div class="empty">Чеков пока нет.</div>'}</section>`;
}

async function messages(){
  const d=await api('/student/messages?limit=100');const items=d.items||[];
  return `<section class="chat-shell"><div class="chat-list">${items.map(x=>`<div class="chat-msg ${x.direction==='IN'?'mine':'theirs'}"><small>${x.direction==='IN'?'Вы':'Преподаватель'} · ${fmtTime(x.created_at)}</small><div>${esc(x.text||'')}</div></div>`).join('')||'<div class="empty">Здесь появится переписка с преподавателем.</div>'}</div><div class="chat-compose"><textarea id="messageText" maxlength="4000" placeholder="Написать сообщение…"></textarea><button id="sendMessage">Отправить</button></div><div id="messageResult"></div></section>`;
}

async function profile(){
  const p=await api('/student/profile');const initial=(p.name||'У')[0].toUpperCase();
  const rates=[['Школьная физика',p.school_physics_rate],['ЕГЭ физика',p.ege_physics_rate],['ОГЭ физика',p.oge_physics_rate],['Олимпиадная физика',p.olympiad_physics_rate],['Школьная химия',p.school_chemistry_rate],['ОГЭ химия',p.oge_chemistry_rate]].filter(x=>x[1]);
  return `<section class="profile-card"><div class="big-avatar">${esc(initial)}</div><h2>${esc(p.name||'Ученик')}</h2><p>${p.grade?`${esc(p.grade)} класс · `:''}${esc(subjectName(p.main_subject))}${p.study_goal?' · '+esc(goalName(p.study_goal)):''}</p></section><section class="menu-list"><button data-go="payments">💳 <span>Оплата и чеки</span>›</button><button data-go="messages">💬 <span>Сообщения</span>›</button>${p.board_url?`<button data-external="${esc(p.board_url)}">🖥 <span>Моя Доска</span>↗</button>`:''}</section>${rates.length?`<section class="section"><h3>Мои тарифы</h3>${rates.map(([n,v])=>`<article class="payment"><div><b>${esc(n)}</b><span>Индивидуальная цена</span></div><strong>${money(v)}/ч</strong></article>`).join('')}</section>`:''}`;
}

async function homework(){
  try{const d=await api('/student/homework');return `<section class="stat-row"><div><b>${d.items.filter(x=>!['CHECKED','COMPLETED'].includes(x.status)).length}</b><span>активных</span></div><div><b>${d.items.filter(x=>['CHECKED','COMPLETED'].includes(x.status)).length}</b><span>выполнено</span></div></section><section class="section"><h3>Мои задания</h3>${d.items.map(x=>`<article class="task-card ${['CHECKED','COMPLETED'].includes(x.status)?'done':''}"><span class="status">${x.external?(x.external.provider==='RESHU_EGE'?'Решу ЕГЭ':x.external.provider==='RESHU_OGE'?'Решу ОГЭ':'Внешний вариант'):x.interactive_task_count?'Интерактивное ДЗ':esc(x.status||'ДЗ')}</span><h3>${esc(x.title||'Домашнее задание')}</h3><p>${esc(x.description||'')}${x.interactive_task_count?` · ${x.interactive_task_count} заданий`:''}</p><button class="form-primary" data-hw="${x.id}">Открыть</button></article>`).join('')||'<div class="empty">Новых заданий нет ✨</div>'}</section>`}catch(e){return '<div class="form-error">Не удалось загрузить домашние задания.</div>'}
}

async function homeworkDetail(id){
  try{const d=await api('/student/homework/detail?id='+id),h=d.homework;if(d.external)return `<button class="back" data-go="homework">← К заданиям</button><article class="task-card"><span class="status">${d.external.provider==='RESHU_EGE'?'Решу ЕГЭ':d.external.provider==='RESHU_OGE'?'Решу ОГЭ':'Внешний вариант'}</span><h2>${esc(h.title)}</h2><p>${esc(h.description||'')}</p><button class="form-primary" id="openExternal">Открыть вариант ↗</button><div class="completion-box"><b>Когда закончишь</b><p>Отметь статус — преподаватель сразу увидит его вместе со ссылкой на вариант.</p><div class="status-actions"><button data-ext-status="DONE">✓ Сделал</button><button data-ext-status="WORKING">Ещё решаю</button><button data-ext-status="NEED_MORE_TIME">Нужно время</button></div></div><div id="hwResult"></div></article>`;return `<button class="back" data-go="homework">← К заданиям</button><section class="section"><h2>${esc(h.title)}</h2><p>${esc(h.description||'')}</p>${(d.tasks||[]).map((t,i)=>`<article class="task-card"><span class="status">Задание ${i+1}${t.task_number?' · №'+esc(t.task_number):''}</span><h3>${esc(t.title||t.topic||'Задача')}</h3><p>${esc(t.statement)}</p><label>Ответ</label><input class="answer-input" data-answer="${t.id}" placeholder="Введи ответ"></article>`).join('')}<button class="form-primary" id="submitInteractive">Проверить ответы</button><div id="hwResult"></div></section>`}catch(e){return '<div class="form-error">Не удалось открыть задание.</div>'}
}

function loginView(){return authCard()}

async function render(tab='home'){
  current=tab;$('#content').innerHTML=loading();$('#pageTitle').textContent=titles[tab]||tab;
  const ok=await ensureAuth();
  if(!ok){$('#content').innerHTML=loginView();bind();return}
  const views={home,schedule,homework,payments,messages,profile};
  const view=views[tab]||home;
  try{$('#content').innerHTML=await view()}catch(e){if(e.status===401){auth=null;$('#content').innerHTML=loginView()}else $('#content').innerHTML='<div class="form-error">Не удалось загрузить данные. Попробуйте ещё раз.</div>'}
  document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.tab===tab));bind();
}

async function openHomework(id){$('#content').innerHTML=loading();$('#content').innerHTML=await homeworkDetail(id);bind();const ext=$('#openExternal');if(ext)ext.onclick=async()=>{try{const r=await api('/student/homework/external/open',{method:'POST',body:JSON.stringify({homework_id:+id})});window.open(r.url,'_blank','noopener')}catch{$('#hwResult').innerHTML='<p class="form-error">Не удалось открыть вариант.</p>'}};document.querySelectorAll('[data-ext-status]').forEach(x=>x.onclick=async()=>{try{await api('/student/homework/external/status',{method:'POST',body:JSON.stringify({homework_id:+id,status:x.dataset.extStatus})});$('#hwResult').innerHTML='<div class="form-success">✓ Статус отправлен преподавателю</div>'}catch{$('#hwResult').innerHTML='<p class="form-error">Не удалось отправить статус.</p>'}});const submit=$('#submitInteractive');if(submit)submit.onclick=async()=>{const responses={};document.querySelectorAll('[data-answer]').forEach(x=>responses[x.dataset.answer]=x.value);try{const r=await api('/student/homework/submit',{method:'POST',body:JSON.stringify({homework_id:+id,responses})});$('#hwResult').innerHTML=`<div class="form-success"><b>${r.score_percent}%</b><br>${r.correct_tasks} из ${r.total_tasks} автоматически проверяемых заданий · ${r.earned_points} / ${r.total_points} баллов</div>`}catch{$('#hwResult').innerHTML='<p class="form-error">Не удалось проверить ответы.</p>'}}}

async function doLogin(){const input=$('#loginCode'),out=$('#loginResult');const code=(input?.value||'').replace(/\D/g,'');if(code.length!==6){out.innerHTML='<p class="form-error">Введите 6 цифр.</p>';return}try{const r=await api('/auth/student/code',{method:'POST',body:JSON.stringify({code})});auth={role:'student',id:r.student?.id};out.innerHTML='<div class="form-success">✓ Вход выполнен</div>';setTimeout(()=>render('home'),250)}catch(e){out.innerHTML=`<p class="form-error">${e.message==='expired'?'Код истёк. Получите новый в боте.':'Код неверный или уже использован.'}</p>`}}

function bind(){
  document.querySelectorAll('[data-go]').forEach(x=>x.onclick=()=>render(x.dataset.go));
  document.querySelectorAll('[data-hw]').forEach(x=>x.onclick=()=>openHomework(x.dataset.hw));
  document.querySelectorAll('[data-external]').forEach(x=>x.onclick=()=>window.open(x.dataset.external,'_blank','noopener'));
  document.querySelectorAll('[data-lesson]').forEach(x=>x.onclick=()=>location.href='/app/lesson/?id='+encodeURIComponent(x.dataset.lesson));
  document.querySelectorAll('[data-schedule-tab]').forEach(x=>x.onclick=()=>{document.querySelectorAll('[data-schedule-tab]').forEach(b=>b.classList.toggle('active',b===x));$('#futurePane').classList.toggle('hidden',x.dataset.scheduleTab!=='future');$('#pastPane').classList.toggle('hidden',x.dataset.scheduleTab!=='past')});
  const l=$('#studentLoginButton');if(l)l.onclick=doLogin;
  const send=$('#sendMessage');if(send)send.onclick=async()=>{const t=$('#messageText'),out=$('#messageResult'),text=(t.value||'').trim();if(!text)return;send.disabled=true;try{await api('/student/message',{method:'POST',body:JSON.stringify({text})});t.value='';out.innerHTML='<div class="form-success">✓ Сообщение отправлено</div>';setTimeout(()=>render('messages'),250)}catch{out.innerHTML='<p class="form-error">Не удалось отправить сообщение.</p>'}finally{send.disabled=false}};
}

document.querySelectorAll('.nav-item').forEach(x=>x.onclick=()=>render(x.dataset.tab));
$('#roleButton').onclick=()=>render('profile');
const params=new URLSearchParams(location.search);render(params.get('tab')||'home');
