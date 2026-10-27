(()=>{
  const originalFetch=window.fetch.bind(window);
  const state={lessonId:null,lesson:null,poll:null,timer:null,lastJoin:null,renderToken:0};
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function json(path,opt={}){const r=await originalFetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'Ошибка');return j}
  function deferEnhance(){const token=++state.renderToken;requestAnimationFrame(()=>requestAnimationFrame(()=>{if(token===state.renderToken)enhance()}))}
  function capture(url,response){try{const s=typeof url==='string'?url:url.url||'';const m=s.match(/\/api\/teacher\/lesson\?id=(\d+)/);if(!m)return;const id=+m[1];response.clone().json().then(d=>{if(!d?.lesson)return;state.lessonId=id;state.lesson=d.lesson;deferEnhance()}).catch(()=>{})}catch{}}
  window.fetch=async(...args)=>{const r=await originalFetch(...args);capture(args[0],r);return r};
  function stopPoll(){if(state.poll){clearInterval(state.poll);state.poll=null}}
  function stopTimer(){if(state.timer){clearInterval(state.timer);state.timer=null}}
  function stopLive(){stopPoll();stopTimer()}
  function timerText(v){if(!v)return'00:00:00';const s=Math.max(0,Math.floor((Date.now()-new Date(v).getTime())/1000));return [Math.floor(s/3600),Math.floor(s%3600/60),s%60].map(x=>String(x).padStart(2,'0')).join(':')}
  function startTimer(startedAt){stopTimer();const tick=()=>{const el=document.querySelector('#individualFactTimer');if(el)el.textContent=timerText(startedAt)};tick();if(startedAt)state.timer=setInterval(tick,1000)}
  function suppressLegacyControls(){['startLesson','finishNow','finishPlan'].forEach(id=>{const el=document.getElementById(id);if(el){el.disabled=true;el.hidden=true;el.setAttribute('aria-hidden','true')}})}
  async function reloadLesson(){if(!state.lessonId)return;try{const d=await json('/teacher/lesson?id='+state.lessonId);if(d?.lesson){state.lesson=d.lesson;deferEnhance()}}catch{}}
  async function refreshEvents(){if(!state.lessonId||state.lesson?.started_at||state.lesson?.finished_at){stopPoll();return}try{const d=await json('/teacher/lesson/join-events?id='+state.lessonId),items=d.items||[];const el=document.querySelector('#joinActivity');const joined=items.find(x=>(x.actor_role==='STUDENT'&&x.event_type==='JOIN_CLICKED')||(x.actor_role==='TEACHER'&&x.event_type==='STUDENT_ARRIVED'));if(joined){state.lastJoin=joined.created_at;if(el){el.className='join-activity online';el.innerHTML=`<b>🟢 Ученик пришёл</b><span>${new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(joined.created_at))}</span>`}await reloadLesson();stopPoll()}else if(el){el.className='join-activity';el.innerHTML='<b>Приход ещё не отмечен</b><span>Подключение к Телемосту здесь не отслеживается</span>'}}catch{}}
  function startPoll(){if(state.lesson?.started_at||state.lesson?.finished_at){stopPoll();return}stopPoll();refreshEvents();state.poll=setInterval(refreshEvents,3000)}
  async function openEntry(btn){if(!state.lessonId)return;btn.disabled=true;btn.textContent='Открываю занятие…';const out=document.querySelector('#entryResult');const desktop=!!window.adeliaDesktop?.desktop;const popup=desktop?null:window.open('about:blank','_blank');try{if(popup)popup.opener=null;const r=await json('/teacher/lesson/open-entry',{method:'POST',body:JSON.stringify({lesson_id:state.lessonId})});out.innerHTML='<div class="notice">✓ Вход открыт. Таймер начнётся после прихода ученика.</div>';if(desktop){if(r.meeting_url)await window.adeliaDesktop.openLessonTool('meeting',r.meeting_url);if(r.board_url)await window.adeliaDesktop.openLessonTool('board',r.board_url)}else if(r.meeting_url){if(popup)popup.location.replace(r.meeting_url);else out.innerHTML+=`<div class="error">Браузер заблокировал новое окно. <a href="${esc(r.meeting_url)}" target="_blank" rel="noopener">Открыть Телемост вручную</a>.</div>`}else if(popup)popup.close();state.lesson={...(state.lesson||{}),meeting_link_sent_at:r.opened_at,meeting_url:r.meeting_url,board_url:r.board_url,started_at:r.started_at};enhance()}catch(e){if(popup)popup.close();btn.disabled=false;btn.textContent='▶ Начать занятие';out.innerHTML=`<div class="error">${esc(e.message)}</div>`}}
  async function confirmStudent(btn){btn.disabled=true;btn.textContent='Фиксирую…';const out=document.querySelector('#entryResult');try{const r=await json('/teacher/lesson/mark-arrived',{method:'POST',body:JSON.stringify({lesson_id:state.lessonId})});state.lesson={...(state.lesson||{}),started_at:r.started_at,lesson_status:'IN_PROGRESS'};stopPoll();if(out)out.innerHTML='<div class="notice">✓ Приход ученика зафиксирован. Фактический отсчёт запущен.</div>';enhance()}catch(e){btn.disabled=false;btn.textContent='✓ Отметить присутствие';if(out)out.innerHTML=`<div class="error">${esc(e.message)}</div>`}}
  async function finishLesson(btn){if(!confirm('Завершить занятие? Доступ к Телемосту через Аделию закроется, а окна урока в desktop-приложении будут закрыты.'))return;btn.disabled=true;btn.textContent='Завершаю…';try{await json('/teacher/lesson/finish',{method:'POST',body:JSON.stringify({lesson_id:state.lessonId,attendance_status:'PRESENT',mode:'NOW'})});if(window.adeliaDesktop?.desktop){try{await window.adeliaDesktop.endLessonWorkspace()}catch{}}state.lesson={...(state.lesson||{}),finished_at:new Date().toISOString(),lesson_status:'COMPLETED'};stopLive();enhance()}catch(e){btn.disabled=false;btn.textContent='⏹ Завершить занятие';const out=document.querySelector('#entryResult');if(out)out.innerHTML=`<div class="error">${esc(e.message)}</div>`}}
  function enhance(){
    const actions=document.querySelector('.lesson-actions');
    if(!actions||!state.lessonId)return;
    suppressLegacyControls();
    let block=document.querySelector('#teacherEntryBlock');
    if(!block){
      block=document.createElement('section');
      block.id='teacherEntryBlock';
      block.className='teacher-entry-block lesson-live-workspace';
      actions.parentNode.insertBefore(block,actions.nextSibling);
    }
    const l=state.lesson||{};
    const opened=!!l.meeting_link_sent_at;
    const started=!!l.started_at;
    const finished=!!l.finished_at||String(l.lesson_status||'').toUpperCase()==='COMPLETED';
    const statusText=finished?'Завершено':started?'Идёт сейчас':opened?'Приход ещё не отмечен':'Готово к запуску';
    const statusClass=finished?'done':started?'live':opened?'waiting':'ready';
    const timer=started&&!finished?timerText(l.started_at):finished?'—':'00:00:00';
    let main;
    if(finished)main='<button class="soft opened" disabled>✓ Занятие завершено</button>';
    else if(started)main='<button class="danger lesson-finish-primary" id="finishLiveLesson">⏹ Завершить занятие</button>';
    else if(opened)main='<button class="primary" id="confirmStudentJoin">✓ Отметить присутствие</button>';
    else main='<button class="primary lesson-start-primary" id="openLessonEntry">▶ Начать занятие</button>';

    block.innerHTML=`
      <div class="lesson-live-top">
        <div class="lesson-live-state">
          <span class="lesson-live-dot ${statusClass}"></span>
          <div>
            <small>Статус занятия</small>
            <b>${statusText}</b>
          </div>
        </div>
        <div class="lesson-live-timer">
          <small>Фактическое время</small>
          <b id="individualFactTimer">${timer}</b>
        </div>
        <div class="lesson-live-main">${main}</div>
      </div>

      <div class="lesson-live-tools">
        <button class="lesson-tool-card ${l.meeting_url?'ready':'muted'}" type="button" id="openMeetingTool" data-url="${esc(l.meeting_url||'')}" ${l.meeting_url?'':'disabled'}>
          <span class="lesson-tool-icon">🎥</span>
          <span><b>Телемост</b><small>${l.meeting_url?'Открыть видео':'Подготовится автоматически'}</small></span>
        </button>
        <button class="lesson-tool-card ${l.board_url?'ready':'muted'}" type="button" id="openBoardTool" data-url="${esc(l.board_url||'')}" ${l.board_url?'':'disabled'}>
          <span class="lesson-tool-icon">🖥</span>
          <span><b>МояДоска</b><small>${l.board_url?'Открыть доску':'Доска не настроена'}</small></span>
        </button>
        <div id="joinActivity" class="lesson-live-presence ${started?'online':''}">
          <span class="lesson-tool-icon">${started?'🟢':'◌'}</span>
          <span><b>${started?'Ученик пришёл':'Приход ещё не отмечен'}</b><small>${started?'Фактический отсчёт идёт':'Вход через Аделию учитывается отдельно от звонка'}</small></span>
        </div>
      </div>

      <div class="lesson-live-secondary">
        ${l.user_id?'<button class="soft" type="button" id="lessonStudentCard">Карточка ученика</button>':''}
        ${l.user_id?'<button class="soft" type="button" id="lessonHomework">＋ Задать ДЗ</button>':''}
        <span class="lesson-live-hint">${finished?'Можно перейти к итогам занятия и прогрессу ученика.':started?'Телемост и доска можно переключать из панели приложения.':opened?'Ссылка ученику уже отправлена. Таймер начнётся после прихода.':'Начало занятия отправит ученику доступ к уроку по доступным каналам.'}</span>
      </div>
      <div id="entryResult"></div>`;

    const meetingTool=document.querySelector('#openMeetingTool');
    if(meetingTool&&!meetingTool.disabled)meetingTool.onclick=()=>window.adeliaDesktop?.desktop?window.adeliaDesktop.openLessonTool('meeting',meetingTool.dataset.url):window.open(meetingTool.dataset.url,'_blank','noopener');
    const boardTool=document.querySelector('#openBoardTool');
    if(boardTool&&!boardTool.disabled)boardTool.onclick=()=>window.adeliaDesktop?.desktop?window.adeliaDesktop.openLessonTool('board',boardTool.dataset.url):window.open(boardTool.dataset.url,'_blank','noopener');
    const studentCard=document.querySelector('#lessonStudentCard');
    if(studentCard&&l.user_id)studentCard.onclick=()=>window.teacherStudentOpen?.(l.user_id);
    const homeworkBtn=document.querySelector('#lessonHomework');
    if(homeworkBtn&&l.user_id)homeworkBtn.onclick=()=>window.newHomework?.(l.user_id,state.lessonId);

    const open=document.querySelector('#openLessonEntry');
    if(open)open.onclick=()=>openEntry(open);
    const confirmBtn=document.querySelector('#confirmStudentJoin');
    if(confirmBtn)confirmBtn.onclick=()=>confirmStudent(confirmBtn);
    const finish=document.querySelector('#finishLiveLesson');
    if(finish)finish.onclick=()=>finishLesson(finish);

    if(started&&!finished){stopPoll();startTimer(l.started_at)}
    else{stopTimer();if(opened&&!finished)startPoll();else stopPoll()}

    document.dispatchEvent(new CustomEvent('adelia:lesson-live-rendered',{detail:{lessonId:state.lessonId,lesson:{...l}}}));
  }
  document.addEventListener('click',e=>{if(e.target.closest('[data-view],nav button')&&!e.target.closest('[data-lesson]')){state.renderToken++;stopLive();if(!e.target.closest('[data-lesson]')){state.lessonId=null;state.lesson=null}}},true);
  window.addEventListener('beforeunload',stopLive);
  window.AdeliaLessonLive={refresh:reloadLesson,stop:stopLive};
})();