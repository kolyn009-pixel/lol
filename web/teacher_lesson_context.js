(()=>{
  const baseFetch=window.fetch.bind(window);
  let lessonId=null,loadedFor=null,loading=false,timer=null;
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function api(path,opt={}){const r=await baseFetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...opt});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'Ошибка');return j}
  const previous=window.fetch;
  window.fetch=async(...args)=>{const r=await previous(...args);try{const u=typeof args[0]==='string'?args[0]:args[0].url||'';const m=u.match(/\/api\/teacher\/lesson\?id=(\d+)/);if(m){lessonId=+m[1];loadedFor=null;setTimeout(load,0)}}catch{}return r};
  const when=v=>v?new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit'}).format(new Date(v)):'—';
  const intent=s=>({GOING:'Придёт',MAYBE:'Возможно придёт',NOT_GOING:'Не придёт',UNKNOWN:'Нет ответа'})[String(s||'UNKNOWN').toUpperCase()]||'Нет ответа';
  function timerText(v){if(!v)return '00:00:00';const sec=Math.max(0,Math.floor((Date.now()-new Date(v).getTime())/1000)),h=Math.floor(sec/3600),m=Math.floor(sec%3600/60),s=sec%60;return [h,m,s].map(x=>String(x).padStart(2,'0')).join(':')}
  function runTimer(started){if(timer){clearInterval(timer);timer=null}const tick=()=>{const el=document.querySelector('#lessonActualTimer');if(el)el.textContent=timerText(started)};tick();if(started)timer=setInterval(tick,1000)}
  function msgRow(x){return `<div class="lesson-chat-msg ${x.direction==='OUT'?'mine':'theirs'}"><small>${x.direction==='OUT'?'Вы':'Ученик'}</small><span>${esc(x.text||'')}</span></div>`}
  function stat(value,label){return value===null||value===undefined?``:`<div><b>${esc(value)}</b><span>${label}</span></div>`}
  function studentCard(d){
    const s=d.student||{},st=d.student_stats||{},a=d.attendance_intent||{},j=d.actual_join||{};
    const source=j.source==='TEACHER'?'отмечено преподавателем':j.source==='STUDENT'?'вход через Аделию':j.source==='LEGACY'?'зафиксировано ранее':'';
    return `<article class="lesson-context-card lesson-student-card">
      <header><div><span class="badge">Контекст ученика</span><h3>👤 ${esc(s.full_name||s.name||'Ученик')}</h3></div></header>
      <div class="lesson-student-stats">
        ${stat(st.completed_lessons,'занятий')}
        ${stat(st.homework_done,'ДЗ выполнено')}
        ${stat(st.homework_pending,'ДЗ в работе')}
      </div>
      ${s.study_goal?`<p class="lesson-goal"><span>Цель</span><b>${esc(s.study_goal)}</b></p>`:''}
      <div class="lesson-presence-compact">
        <div><span>Ответ</span><b>${esc(intent(a.status))}</b><small>${a.updated_at?'в '+esc(when(a.updated_at)):'ожидаем'}</small></div>
        <div><span>Вход</span><b>${j.joined?'Подключился':'Не вошёл'}</b><small>${j.joined_at?'в '+esc(when(j.joined_at))+(source?' · '+source:''):'не зафиксирован'}</small></div>
        <div><span>Время</span><b id="lessonActualTimer">${esc(timerText(j.started_at))}</b><small>${j.started_at?'фактическое':'ещё не идёт'}</small></div>
      </div>
      <button class="soft wide" data-student="${esc(d.user_id)}">Открыть карточку ученика</button>
    </article>`
  }
  function notesCard(d){return `<article class="lesson-context-card lesson-notes-card">
    <header><div><span class="badge">Во время занятия</span><h3>📝 Заметки</h3><p>Фиксируйте важное по ходу урока — всё останется в карточке занятия.</p></div></header>
    <div class="lesson-note-list">${(d.notes||[]).slice(-5).map(n=>`<div class="lesson-note">${esc(n.text)}</div>`).join('')||'<span class="muted">Заметок пока нет</span>'}</div>
    <textarea id="lessonNoteText" placeholder="Короткая заметка по занятию…"></textarea>
    <div class="lesson-card-actions"><span id="lessonNoteResult"></span><button class="soft" id="saveLessonNote">Сохранить заметку</button></div>
  </article>`}
  function homeworkCard(d){return `<article class="lesson-context-card lesson-homework-card">
    <header><div><span class="badge">Домашние задания</span><h3>📚 Последние ДЗ</h3></div><button class="soft compact" data-view="newHomework">＋ Задать ДЗ</button></header>
    <div class="lesson-hw-list">${(d.homework||[]).slice(0,5).map(h=>`<div><b>${esc(h.title||'Домашнее задание')}</b><span>${esc(h.status_ui?.label||h.status||'')} ${h.deadline?'· до '+esc(h.deadline):''}</span></div>`).join('')||'<span class="muted">Домашних заданий пока нет</span>'}</div>
  </article>`}
  function materialsCard(d){return `<article class="lesson-context-card lesson-materials-card">
    <header><div><span class="badge">Быстрый доступ</span><h3>📎 Материалы</h3></div></header>
    <div class="lesson-material-list">${(d.materials||[]).slice(0,6).map(m=>{const url=m.external_url||'';return url?`<a href="${esc(url)}" target="_blank" rel="noopener"><b>${esc(m.title)}</b><span>${esc(m.material_type||'Материал')}</span></a>`:`<div><b>${esc(m.title)}</b><span>${esc(m.original_filename||m.material_type||'Материал')}</span></div>`}).join('')||'<span class="muted">Для ученика пока нет выданных материалов</span>'}</div>
    <button class="soft wide" data-view="library">Открыть библиотеку</button>
  </article>`}
  function chatCard(d){return `<article class="lesson-context-card lesson-chat-card">
    <header><div><span class="badge">Единый чат</span><h3>💬 Сообщения</h3></div><button class="soft compact" data-view="messages">Открыть чат</button></header>
    <div class="lesson-chat-list">${(d.messages||[]).slice(-8).map(msgRow).join('')||'<span class="muted">Переписка пока пуста</span>'}</div>
    <div class="lesson-chat-compose"><textarea id="lessonMessageText" maxlength="4000" placeholder="Сообщение ученику…"></textarea><button class="primary" id="sendLessonMessage">Отправить</button></div>
    <div id="lessonMessageResult"></div>
  </article>`}
  async function load(force=false){
    if(!lessonId||loading||(!force&&loadedFor===lessonId&&document.querySelector('.lesson-context-grid')))return;
    const actions=document.querySelector('.lesson-actions');if(!actions)return;
    loading=true;
    try{
      const d=await api('/teacher/lesson/context?id='+lessonId);loadedFor=lessonId;
      let host=document.querySelector('#lessonContextBlock');
      if(!host){host=document.createElement('section');host.id='lessonContextBlock';actions.parentNode.appendChild(host)}
      host.innerHTML=`<div class="lesson-context-grid lesson-context-workspace">
        <div class="lesson-context-main">${notesCard(d)}${homeworkCard(d)}${chatCard(d)}</div>
        <aside class="lesson-context-side">${studentCard(d)}${materialsCard(d)}</aside>
      </div>`;
      runTimer(d.actual_join?.started_at);bind(host)
    }catch(e){console.warn('[lesson-context]',e)}finally{loading=false}
  }
  function bind(host){
    host.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>document.querySelector(`nav [data-view="${b.dataset.view}"]`)?.click());
    host.querySelectorAll('[data-student]').forEach(b=>b.onclick=()=>{const id=b.dataset.student;const nav=document.querySelector('nav [data-view="students"]');if(nav)nav.click();setTimeout(()=>{if(typeof window.openStudent==='function')window.openStudent(id)},0)});
    const save=host.querySelector('#saveLessonNote');
    if(save)save.onclick=async()=>{const t=host.querySelector('#lessonNoteText'),out=host.querySelector('#lessonNoteResult'),text=t.value.trim();if(!text)return;save.disabled=true;try{await api('/teacher/lesson/note',{method:'POST',body:JSON.stringify({lesson_id:lessonId,text})});t.value='';loadedFor=null;await load(true)}catch{out.innerHTML='<div class="error">Не удалось сохранить заметку.</div>'}finally{save.disabled=false}};
    const send=host.querySelector('#sendLessonMessage');
    if(send)send.onclick=async()=>{const t=host.querySelector('#lessonMessageText'),out=host.querySelector('#lessonMessageResult'),text=t.value.trim();if(!text)return;send.disabled=true;try{await api('/teacher/lesson/message',{method:'POST',body:JSON.stringify({lesson_id:lessonId,text})});t.value='';out.innerHTML='<div class="notice">✓ Сообщение сохранено и поставлено в доставку</div>';loadedFor=null;setTimeout(()=>load(true),250)}catch{out.innerHTML='<div class="error">Не удалось отправить сообщение.</div>'}finally{send.disabled=false}}
  }
  document.addEventListener('adelia:lesson-live-rendered',e=>{const id=+e.detail?.lessonId;if(!id)return;lessonId=id;loadedFor=null;load(true)});
  document.addEventListener('click',e=>{if(e.target.closest('[data-view],nav button')&&!e.target.closest('[data-lesson]')){lessonId=null;loadedFor=null;if(timer){clearInterval(timer);timer=null}}},true);
  addEventListener('beforeunload',()=>{if(timer)clearInterval(timer)})
})();