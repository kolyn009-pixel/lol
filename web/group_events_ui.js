(()=>{
  const $=s=>document.querySelector(s);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money=n=>Number(n||0).toLocaleString('ru-RU')+' ₽';
  const fmtDate=v=>v?new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short'}).format(new Date(v)):'—';
  const fmtTime=v=>v?new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit'}).format(new Date(v)):'—';
  let groups=[];
  let mounted=false;

  async function api(path,opt={}){
    const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});
    const j=await r.json().catch(()=>({}));
    if(!r.ok){const e=new Error(j.error||'Ошибка');e.status=r.status;throw e}
    return j;
  }
  function content(){return $('#content')}
  function title(v){const x=$('#pageTitle');if(x)x.textContent=v}
  function active(tab){document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.tab===tab))}
  function loading(){content().innerHTML='<div class="skeleton-stack"><div class="skeleton hero-skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>'}
  function error(msg='Не удалось загрузить данные.'){content().innerHTML=`<div class="form-error">${esc(msg)}</div>`}

  function eventType(v){return ({MOCK_EXAM:'Пробник',SEMINAR:'Семинар',INTENSIVE:'Интенсив',WORKSHOP:'Разбор'})[String(v||'').toUpperCase()]||'Событие'}
  function eventStatus(item){
    const reg=item.registration||null,inv=item.invite||null;
    if(reg?.status==='REGISTERED')return reg.payment_status==='UNPAID'?'Вы записаны · ожидает оплаты':'Вы записаны';
    if(inv?.status==='HELD')return 'Персональное приглашение';
    return 'Запись открыта';
  }
  function eventCard(item){
    const cap=item.capacity||{};
    const reg=item.registration||null,inv=item.invite||null;
    const places=cap.remaining==null?'места не ограничены':`${cap.remaining} мест осталось`;
    const canRegister=!reg&&!(inv&&inv.status==='ACCEPTED');
    const inviteActions=inv?.status==='HELD'?`<div class="event-actions"><button class="event-primary" data-invite-accept="${item.id}">Принять приглашение</button><button class="event-secondary" data-invite-decline="${item.id}">Отказаться</button></div>`:'';
    const register=canRegister&&!inviteActions?`<button class="event-primary" data-event-register="${item.id}">Записаться</button>`:'';
    const enter=reg?.status==='REGISTERED'?`<button class="event-secondary" data-event-enter="${item.id}">Открыть событие</button>`:'';
    return `<article class="event-card"><div class="event-date"><b>${fmtDate(item.starts_at)}</b><span>${fmtTime(item.starts_at)}</span></div><div class="event-main"><div class="event-kicker">${esc(eventType(item.event_type))} · ${esc(item.subject||'Обучение')}</div><h3>${esc(item.title)}</h3><p>${esc(eventStatus(item))} · ${esc(places)}</p><div class="event-meta"><span>⏱ ${fmtTime(item.starts_at)}–${fmtTime(item.ends_at)}</span><span>💳 ${Number(item.price_per_student||0)?money(item.price_per_student):'Бесплатно'}</span></div>${inviteActions||`<div class="event-actions">${register}${enter}</div>`}</div></article>`;
  }

  async function eventsView(){
    loading();title('Группы и события');active('events');
    try{
      const d=await api('/student/events');const items=d.items||[];
      const registered=items.filter(x=>x.registration?.status==='REGISTERED');
      const open=items.filter(x=>!x.registration||x.registration.status!=='REGISTERED');
      content().innerHTML=`<section class="events-hero"><div><span>✨ Новые возможности</span><h2>Группы и события</h2><p>Пробники, семинары, интенсивы и открытые занятия — записывайся прямо в Аделии.</p></div><div class="events-hero-icon">🎓</div></section>${registered.length?`<section class="section"><div class="section-head"><h3>Мои записи</h3><span class="group-count">${registered.length}</span></div><div class="event-grid">${registered.map(eventCard).join('')}</div></section>`:''}<section class="section"><h3>Доступно сейчас</h3><div class="event-grid">${open.map(eventCard).join('')||'<div class="empty">Сейчас открытых событий нет. Аделия покажет их здесь, как только появится запись.</div>'}</div></section><div id="eventResult"></div>`;
      bindEvents();
    }catch(e){error(e.message)}
  }

  function groupCard(g){
    return `<button class="group-card" data-group-open="${g.id}"><div class="group-avatar">👥</div><div><b>${esc(g.name||'Учебная группа')}</b><span>${esc(g.subject||'')} ${g.membership_status==='PAUSED'?'· пауза':'· участник'}</span></div><span class="group-arrow">→</span></button>`;
  }
  async function groupsView(){
    loading();title(groups.length>1?'Мои группы':'Моя группа');active('groups');
    try{
      const d=await api('/student/groups');groups=d.items||[];
      if(!groups.length){content().innerHTML='<div class="empty">Ты пока не состоишь в учебной группе.</div>';return}
      if(groups.length===1)return groupDetail(groups[0].id);
      content().innerHTML=`<section class="groups-hero"><span>👥 Учимся вместе</span><h2>Мои группы</h2><p>Расписание, групповой чат, домашние задания и занятия — в одном месте.</p></section><div class="group-list">${groups.map(groupCard).join('')}</div>`;
      document.querySelectorAll('[data-group-open]').forEach(x=>x.onclick=()=>groupDetail(x.dataset.groupOpen));
    }catch(e){error(e.message)}
  }
  async function groupDetail(id){
    loading();active('groups');
    try{
      const d=await api('/student/group/summary?group_id='+encodeURIComponent(id));
      const g=d.group||{};title(g.name||'Моя группа');
      const lessons=d.upcoming_lessons||[];
      content().innerHTML=`<button class="back group-back" id="groupsBack">← ${groups.length>1?'К группам':'Назад'}</button><section class="group-detail-hero"><div class="group-avatar big">👥</div><div><span>Моя группа</span><h2>${esc(g.name||'Учебная группа')}</h2><p>${esc(g.subject||'')} ${g.study_goal?'· '+esc(g.study_goal):''}</p></div></section><section class="group-tabs"><button class="active" data-group-tab="lessons">Занятия</button><button data-group-tab="chat">Чат группы</button></section><div id="groupPane"><section class="section"><h3>Ближайшие занятия</h3>${lessons.map(l=>`<article class="group-lesson"><div class="date-badge"><b>${new Date(l.start_time).getDate()}</b><span>${new Intl.DateTimeFormat('ru-RU',{month:'short'}).format(new Date(l.start_time))}</span></div><div><b>${fmtTime(l.start_time)}–${fmtTime(l.end_time)}</b><span>${esc(l.payment_status||'')} · ${esc(l.attendance_status||'')}</span></div><button class="mini-btn" data-group-enter="${l.id}">Открыть</button></article>`).join('')||'<div class="empty">Ближайших групповых занятий пока нет.</div>'}</section></div>`;
      $('#groupsBack').onclick=()=>groups.length>1?groupsView():eventsView();
      document.querySelectorAll('[data-group-tab]').forEach(x=>x.onclick=()=>{document.querySelectorAll('[data-group-tab]').forEach(b=>b.classList.toggle('active',b===x));x.dataset.groupTab==='chat'?groupChat(id):groupDetail(id)});
      document.querySelectorAll('[data-group-enter]').forEach(x=>x.onclick=()=>enterGroupLesson(x.dataset.groupEnter));
    }catch(e){error(e.message)}
  }
  async function groupChat(id){
    const pane=$('#groupPane');if(!pane)return;pane.innerHTML='<div class="skeleton"></div>';
    try{
      const d=await api('/student/group/chat?group_id='+encodeURIComponent(id)+'&limit=100');const items=d.items||[];
      pane.innerHTML=`<section class="group-chat"><div class="group-chat-list">${items.map(m=>`<div class="group-msg ${m.mine?'mine':''}"><small>${esc(m.sender_name||m.sender_role||'Участник')} · ${fmtTime(m.created_at)}</small><div>${esc(m.body)}</div></div>`).join('')||'<div class="empty">В группе пока нет сообщений.</div>'}</div><div class="group-compose"><textarea id="groupMessage" maxlength="4000" placeholder="Сообщение группе…"></textarea><button id="groupSend">Отправить</button></div><div id="groupResult"></div></section>`;
      $('#groupSend').onclick=async()=>{const text=($('#groupMessage').value||'').trim();if(!text)return;try{await api('/student/group/chat',{method:'POST',body:JSON.stringify({group_id:+id,body:text})});await groupChat(id)}catch(e){$('#groupResult').innerHTML=`<div class="form-error">${esc(e.message)}</div>`}};
    }catch(e){pane.innerHTML=`<div class="form-error">${esc(e.message)}</div>`}
  }
  async function enterGroupLesson(id){
    try{const r=await api('/student/group-lesson/enter',{method:'POST',body:JSON.stringify({lesson_id:+id})});if(window.adeliaDesktop?.desktop){if(r.meeting_url)await window.adeliaDesktop.openLessonTool('meeting',r.meeting_url);if(r.board_url)await window.adeliaDesktop.openLessonTool('board',r.board_url)}else{if(r.meeting_url)window.open(r.meeting_url,'_blank','noopener');if(r.board_url)window.open(r.board_url,'_blank','noopener')}}catch(e){alert(e.message==='group_lesson_not_open'?'Вход в занятие пока закрыт.':e.message)}
  }
  async function enterEvent(id){
    try{const r=await api('/student/event/enter',{method:'POST',body:JSON.stringify({event_id:+id})});if(window.adeliaDesktop?.desktop){if(r.meeting_url)await window.adeliaDesktop.openLessonTool('meeting',r.meeting_url);if(r.board_url)await window.adeliaDesktop.openLessonTool('board',r.board_url)}else{if(r.meeting_url)window.open(r.meeting_url,'_blank','noopener');if(r.board_url)window.open(r.board_url,'_blank','noopener')}}catch(e){const out=$('#eventResult');if(out)out.innerHTML=`<div class="form-error">${e.message==='event_not_open'?'Событие ещё не началось или вход пока закрыт.':esc(e.message)}</div>`}
  }
  function bindEvents(){
    document.querySelectorAll('[data-event-register]').forEach(x=>x.onclick=async()=>{x.disabled=true;try{await api('/student/event/register',{method:'POST',body:JSON.stringify({event_id:+x.dataset.eventRegister})});await eventsView()}catch(e){x.disabled=false;$('#eventResult').innerHTML=`<div class="form-error">${esc(e.message)}</div>`}});
    document.querySelectorAll('[data-invite-accept]').forEach(x=>x.onclick=async()=>{try{await api('/student/event/invite/respond',{method:'POST',body:JSON.stringify({event_id:+x.dataset.inviteAccept,accepted:true})});await eventsView()}catch(e){$('#eventResult').innerHTML=`<div class="form-error">${esc(e.message)}</div>`}});
    document.querySelectorAll('[data-invite-decline]').forEach(x=>x.onclick=async()=>{try{await api('/student/event/invite/respond',{method:'POST',body:JSON.stringify({event_id:+x.dataset.inviteDecline,accepted:false})});await eventsView()}catch(e){$('#eventResult').innerHTML=`<div class="form-error">${esc(e.message)}</div>`}});
    document.querySelectorAll('[data-event-enter]').forEach(x=>x.onclick=()=>enterEvent(x.dataset.eventEnter));
  }

  function navButton(tab,icon,label){const b=document.createElement('button');b.className='nav-item';b.dataset.tab=tab;b.innerHTML=`<span>${icon}</span><small>${label}</small>`;return b}
  async function mount(){
    if(mounted)return;mounted=true;
    const nav=document.querySelector('.bottom-nav');if(!nav)return;
    const events=navButton('events','✨','Группы и события');events.onclick=eventsView;nav.insertBefore(events,nav.querySelector('[data-tab="profile"]'));
    try{const d=await api('/student/groups');groups=d.items||[]}catch{groups=[]}
    if(groups.length){const label=groups.length>1?'Мои группы':'Моя группа';const gb=navButton('groups','👥',label);gb.onclick=groupsView;nav.insertBefore(gb,events)}
    const observer=new MutationObserver(()=>{
      const quick=document.querySelector('.quick-actions');
      if(quick&&!quick.querySelector('[data-go-events]')){const b=document.createElement('button');b.className='action-card';b.dataset.goEvents='1';b.innerHTML='<span>✨</span><b>Группы и события</b><small>Пробники, семинары и группы</small>';b.onclick=eventsView;quick.appendChild(b)}
    });
    observer.observe(content(),{childList:true,subtree:true});
  }
  setTimeout(mount,250);
})();
