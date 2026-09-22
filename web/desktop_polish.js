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
  function addCounters(){
    D.getUxState().then(s=>{
      const unread=Number(s?.dashboard?.unreadMessages||0),homework=Number(s?.dashboard?.activeHomework||0);
      const chat=document.querySelector('.nav-item[data-tab="messages"]'),hw=document.querySelector('.nav-item[data-tab="homework"]');
      const put=(el,n)=>{if(!el)return;let badge=el.querySelector('.desktop-nav-badge');if(!n){badge?.remove();return}if(!badge){badge=document.createElement('i');badge.className='desktop-nav-badge';el.appendChild(badge)}badge.textContent=n>99?'99+':String(n)};
      put(chat,unread);put(hw,homework);
    }).catch(()=>{});
  }
  const observer=new MutationObserver(()=>{polishNavigation();addCounters()});
  observer.observe(document.body,{childList:true,subtree:true});
  polishNavigation();addCounters();setInterval(addCounters,30000);
})();
