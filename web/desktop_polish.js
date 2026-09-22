(()=>{
  if(!window.adeliaDesktop?.desktop)return;
  const D=window.adeliaDesktop;
  const $=s=>document.querySelector(s);
  const body=document.body;
  let lastLayout='';
  let settingsOpen=false;

  function toast(text,kind='ok'){
    let host=$('#desktopToastHost');
    if(!host){host=document.createElement('div');host.id='desktopToastHost';host.className='desktop-toast-host';body.appendChild(host)}
    const t=document.createElement('div');t.className=`desktop-toast ${kind}`;t.textContent=text;host.appendChild(t);
    requestAnimationFrame(()=>t.classList.add('show'));
    setTimeout(()=>{t.classList.remove('show');setTimeout(()=>t.remove(),220)},2600);
  }

  body.classList.remove('desktop-compact');localStorage.removeItem('adelia_desktop_sidebar');

  const toolbar=document.createElement('section');
  toolbar.className='lesson-toolbar';toolbar.id='lessonToolbar';toolbar.hidden=true;
  toolbar.innerHTML=`<div class="lesson-toolbar-title"><span class="lesson-live-dot"></span><div><b>Режим занятия</b><small id="lessonToolbarState">Окна занятия открыты</small></div></div><div class="lesson-layout-buttons"><button data-layout="together" title="Ctrl+Shift+L">◫ <span>Вместе</span></button><button data-layout="board-focus" title="Ctrl+Shift+B">▣ <span>Фокус на доске</span></button><button data-layout="mini-video">▱ <span>Мини-видео</span></button><button data-layout="hide-video" title="Ctrl+Shift+V">◼ <span>Скрыть Telemost</span></button></div><button class="lesson-toolbar-close" id="lessonToolbarEnd" title="Закрыть окна занятия">×</button>`;
  body.appendChild(toolbar);

  async function setLayout(mode){
    try{const s=await D.setLessonLayout(mode);paintLayout(s);toast(({together:'Обычная раскладка', 'board-focus':'Фокус на доске','mini-video':'Доска + мини-видео','hide-video':'Telemost скрыт'})[mode]||'Раскладка изменена')}catch{toast('Не удалось изменить раскладку','error')}
  }
  function paintLayout(s){
    if(!s)return;lastLayout=s.mode||lastLayout;toolbar.hidden=!s.active;
    toolbar.querySelectorAll('[data-layout]').forEach(b=>b.classList.toggle('active',b.dataset.layout===s.mode));
    const state=$('#lessonToolbarState');if(state)state.textContent=s.meetingVisible?(s.mode==='mini-video'?'Telemost в мини-окне':'Telemost и доска активны'):'Доска на весь экран · Telemost скрыт';
  }
  toolbar.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>setLayout(b.dataset.layout));
  $('#lessonToolbarEnd').onclick=async()=>{try{await D.endLessonWorkspace();toolbar.hidden=true;toast('Окна занятия закрыты')}catch{toast('Не удалось закрыть окна','error')}};
  async function pollLayout(){try{paintLayout(await D.getLessonLayout())}catch{}}
  setInterval(pollLayout,1200);setTimeout(pollLayout,700);

  const settings=document.createElement('div');settings.className='desktop-modal-backdrop';settings.id='desktopSettingsModal';settings.hidden=true;
  settings.innerHTML=`<section class="desktop-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="desktopSettingsTitle"><header><div><span>Приложение Аделия</span><h2 id="desktopSettingsTitle">Настройки Аделии</h2></div><button id="desktopSettingsClose" aria-label="Закрыть">×</button></header><div class="desktop-setting-list"><label><div><b>Уведомления Аделии</b><span>Напоминания о занятиях и важные события</span></div><input type="checkbox" id="settingNotifications"></label><label><div><b>Запуск вместе с системой</b><span>Аделия будет готова ещё до начала занятия</span></div><input type="checkbox" id="settingAutostart"></label><label><div><b>Горячая клавиша</b><span>Ctrl + Shift + A — быстро открыть Аделию</span></div><input type="checkbox" id="settingHotkey"></label><label><div><b>Сворачивать в трей</b><span>Крестик скрывает окно, но оставляет Аделию рядом</span></div><input type="checkbox" id="settingTray"></label></div><div class="desktop-shortcuts"><b>Во время занятия</b><span><kbd>Ctrl Shift B</kbd> Фокус на доске</span><span><kbd>Ctrl Shift V</kbd> Скрыть / вернуть Telemost</span><span><kbd>Ctrl Shift L</kbd> Обычная раскладка</span></div></section>`;
  body.appendChild(settings);

  async function openSettings(){
    try{
      const s=await D.getUxState();const p=s?.preferences||{};
      $('#settingNotifications').checked=p.notificationsEnabled!==false;
      $('#settingAutostart').checked=!!p.autostartEnabled;
      $('#settingHotkey').checked=p.hotkeyEnabled!==false;
      const common=await D.getPreferences();$('#settingTray').checked=common?.closeToTray!==false;
    }catch{}
    settings.hidden=false;settingsOpen=true;setTimeout(()=>$('#desktopSettingsClose')?.focus(),0);
  }
  function closeSettings(){settings.hidden=true;settingsOpen=false}
  $('#desktopSettingsClose').onclick=closeSettings;
  settings.addEventListener('click',e=>{if(e.target===settings)closeSettings()});
  $('#settingNotifications').onchange=async e=>{await D.setNotifications(e.target.checked);toast('Настройка уведомлений сохранена')};
  $('#settingAutostart').onchange=async e=>{await D.setAutostart(e.target.checked);toast(e.target.checked?'Автозапуск включён':'Автозапуск выключен')};
  $('#settingHotkey').onchange=async e=>{const r=await D.setHotkey(e.target.checked);if(e.target.checked&&r?.hotkeyRegistered===false){e.target.checked=false;toast('Эта горячая клавиша занята другой программой','error')}else toast('Настройка горячей клавиши сохранена')};
  $('#settingTray').onchange=async e=>{await D.setCloseToTray(e.target.checked);toast('Поведение кнопки закрытия сохранено')};

  const oldSettings=$('#desktopSettings');if(oldSettings)oldSettings.onclick=openSettings;
  window.addEventListener('keydown',e=>{if(e.key==='Escape'&&settingsOpen)closeSettings()});

  function polishNavigation(){
    document.querySelectorAll('.nav-item').forEach(btn=>{
      if(!btn.hasAttribute('title')){const label=btn.querySelector('small')?.textContent?.trim();if(label)btn.title=label}
      if(!btn.hasAttribute('aria-label')){const label=btn.querySelector('small')?.textContent?.trim();if(label)btn.setAttribute('aria-label',label)}
    });
  }
  async function syncDashboardState(){
    try{
      const [dashRes,msgRes]=await Promise.all([fetch('/api/teacher/dashboard',{credentials:'same-origin',cache:'no-store'}),fetch('/api/teacher/messages?limit=100',{credentials:'same-origin',cache:'no-store'})]);
      if(!dashRes.ok)return;
      const dash=await dashRes.json(),messages=msgRes.ok?await msgRes.json():{items:[]};
      const next=(dash.next_lessons||[])[0]||null;
      const unread=(messages.items||[]).reduce((sum,x)=>sum+Math.max(0,Number(x.unread||0)),0);
      await D.updateDashboardState?.({nextLesson:next,unreadMessages:unread,activeHomework:Number(dash.stats?.submissions||0),unpaidAmount:Number(dash.stats?.unpaid||0)});
    }catch(_){}
  }
  function notificationCenterHtml(s){
    const d=s?.dashboard||{},lesson=d.nextLesson||null,unread=Math.max(0,Number(d.unreadMessages||0)),homework=Math.max(0,Number(d.activeHomework||0)),unpaid=Math.max(0,Number(d.unpaidAmount||0));
    const lessonText=lesson?.start_time?new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit'}).format(new Date(lesson.start_time)):'Нет ближайшего занятия';
    return `<div class="desktop-notification-center"><div class="desktop-notification-head"><div><span>Центр событий</span><h3>Что требует внимания</h3></div><button class="ghost" type="button" data-event-close>×</button></div><button type="button" data-event-route="home"><b>◷ Ближайший урок</b><span>${lesson?String(lesson.name||'Ученик')+' · '+lessonText:'Сегодня всё спокойно'}</span></button><button type="button" data-event-route="chat"><b>✉ Сообщения <i>${unread}</i></b><span>${unread?'Есть непрочитанные сообщения':'Новых сообщений нет'}</span></button><button type="button" data-event-route="homework"><b>✓ ДЗ на проверку <i>${homework}</i></b><span>${homework?'Работы ждут проверки':'Очередь пуста'}</span></button><button type="button" data-event-route="finance"><b>₽ Оплата</b><span>${unpaid?Math.round(unpaid).toLocaleString('ru-RU')+' ₽ ожидает оплаты':'Нет новых проблем с оплатой'}</span></button></div>`;
  }
  async function toggleNotificationCenter(){
    let center=$('#desktopNotificationCenter');
    if(center){center.remove();return}
    try{
      const s=await D.getUxState();center=document.createElement('div');center.id='desktopNotificationCenter';center.innerHTML=notificationCenterHtml(s);body.appendChild(center);
      center.querySelector('[data-event-close]').onclick=()=>center.remove();
      center.querySelectorAll('[data-event-route]').forEach(b=>b.onclick=async()=>{await D.openRoute(b.dataset.eventRoute);center.remove()});
    }catch{toast('Не удалось открыть центр событий','error')}
  }
  function ensureEventButton(){
    const host=document.querySelector('.header-actions');if(!host||host.querySelector('[data-desktop-events]'))return;
    const b=document.createElement('button');b.type='button';b.className='ghost desktop-events-button';b.dataset.desktopEvents='1';b.innerHTML='🔔 <span>События</span>';b.onclick=toggleNotificationCenter;host.prepend(b);
  }
  function addCounters(){
    D.getUxState().then(s=>{
      const unread=Number(s?.dashboard?.unreadMessages||0),homework=Number(s?.dashboard?.activeHomework||0);
      const chat=document.querySelector('.nav-item[data-tab="messages"]'),hw=document.querySelector('.nav-item[data-tab="homework"]');
      const put=(el,n)=>{if(!el)return;let badge=el.querySelector('.desktop-nav-badge');if(!n){badge?.remove();return}if(!badge){badge=document.createElement('i');badge.className='desktop-nav-badge';el.appendChild(badge)}badge.textContent=n>99?'99+':String(n)};
      put(chat,unread);put(hw,homework);
    }).catch(()=>{});
  }
  const observer=new MutationObserver(()=>{polishNavigation();ensureEventButton();addCounters()});
  observer.observe(document.body,{childList:true,subtree:true});
  polishNavigation();ensureEventButton();addCounters();syncDashboardState();setInterval(addCounters,30000);setInterval(syncDashboardState,60000);
})();
