(()=>{
  if(!window.adeliaDesktop?.desktop)return;
  document.body.classList.add('adelia-desktop');
  const topbar=document.querySelector('.topbar');
  const nav=document.querySelector('.bottom-nav');
  const content=document.querySelector('#content');
  if(!topbar||!nav||!content)return;

  const command=document.createElement('label');
  command.className='desktop-command';
  command.innerHTML='<span>⌕</span><input id="desktopSearch" aria-label="Быстрый поиск" placeholder="Поиск по урокам, материалам, сообщениям…"><kbd>Ctrl K</kbd>';
  const actions=document.createElement('div');
  actions.className='desktop-top-actions';
  actions.innerHTML='<button class="desktop-icon-btn" id="desktopBell" aria-label="Уведомления">🔔<i class="desktop-dot" hidden></i></button>';
  topbar.insertBefore(command,document.querySelector('#roleButton'));
  topbar.insertBefore(actions,document.querySelector('#roleButton'));

  const footer=document.createElement('div');
  footer.className='desktop-sidebar-footer';
  footer.innerHTML='<button type="button" id="desktopSettings">⚙ Настройки Windows</button>';
  document.body.appendChild(footer);

  function go(tab){
    const b=document.querySelector(`.nav-item[data-tab="${tab}"]`);
    if(b)b.click();
  }
  function runSearch(value){
    const q=String(value||'').trim().toLowerCase();
    if(!q)return;
    if(/дом|дз|задан/.test(q))return go('homework');
    if(/чат|сообщ/.test(q))return go('messages');
    if(/расп|занят|урок/.test(q))return go('schedule');
    if(/оплат|чек|баланс/.test(q))return go('profile');
    if(/глав/.test(q))return go('home');
  }
  const search=document.querySelector('#desktopSearch');
  search.addEventListener('keydown',e=>{if(e.key==='Enter'){runSearch(search.value);search.blur()}});
  window.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){
      e.preventDefault();search.focus();search.select();
    }
  });
  document.querySelector('#desktopSettings').onclick=()=>go('profile');
  document.querySelector('#desktopBell').onclick=()=>go('messages');

  async function refreshDesktopState(){
    try{
      const s=await window.adeliaDesktop.getUxState?.();
      const unread=Number(s?.dashboard?.unreadMessages||0);
      document.querySelector('#desktopBell .desktop-dot').hidden=!unread;
    }catch{}
  }
  refreshDesktopState();
  setInterval(refreshDesktopState,30000);

  function enhanceHome(){
    if(!document.querySelector('.welcome')||document.querySelector('.desktop-status-strip'))return;
    const strip=document.createElement('section');
    strip.className='desktop-status-strip';
    const cards=[
      ['💜','Аделия рядом','Уведомления и быстрые действия включены'],
      ['⌨','Быстрый поиск','Ctrl + K — перейти к нужному разделу'],
      ['☁','Синхронизация','Данные кабинета обновляются автоматически']
    ];
    strip.innerHTML=cards.map(x=>`<div class="desktop-status-card"><i>${x[0]}</i><div><b>${x[1]}</b><span>${x[2]}</span></div></div>`).join('');
    content.prepend(strip);
  }
  const observer=new MutationObserver(()=>enhanceHome());
  observer.observe(content,{childList:true,subtree:false});
  enhanceHome();
})();
