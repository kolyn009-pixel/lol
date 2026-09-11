(()=>{
  const body=document.body;
  const content=document.getElementById('content');
  if(!body||!content)return;

  function isAuth(){
    const text=(content.textContent||'').toLowerCase();
    return !!content.querySelector('.auth-card,input[type="password"]') &&
      (text.includes('вход в личный кабинет')||text.includes('первый вход')||text.includes('войти'));
  }

  function sync(){
    body.classList.toggle('adelia-auth-screen',isAuth());
  }

  function iosInstallSheet(){
    document.querySelector('.adelia-install-backdrop')?.remove();
    const wrap=document.createElement('div');
    wrap.className='adelia-install-backdrop';
    wrap.innerHTML=`<section class="adelia-install-sheet" role="dialog" aria-modal="true" aria-label="Установить Аделию"><h3>Установить Аделию</h3><p>На iPhone приложение добавляется через меню браузера.</p><div class="adelia-install-steps"><div class="adelia-install-step"><b>1</b><span>Нажмите <strong>Поделиться</strong> в меню браузера</span></div><div class="adelia-install-step"><b>2</b><span>Выберите <strong>На экран «Домой»</strong></span></div><div class="adelia-install-step"><b>3</b><span>Нажмите <strong>Добавить</strong></span></div></div><button class="adelia-install-close" type="button">Понятно</button></section>`;
    const close=()=>wrap.remove();
    wrap.querySelector('.adelia-install-close').onclick=close;
    wrap.addEventListener('click',e=>{if(e.target===wrap)close()});
    document.body.append(wrap);
  }

  function patchInstall(){
    const b=document.getElementById('installAdelia');
    if(!b||b.dataset.mobilePatched)return;
    b.dataset.mobilePatched='1';
    if(window.AdeliaPWA?.isIOS?.()&&!window.AdeliaPWA?.isStandalone?.()){
      b.textContent='Установить';
      b.hidden=false;
      b.onclick=e=>{e.preventDefault();iosInstallSheet()};
    }
  }

  sync();patchInstall();
  new MutationObserver(()=>{sync();patchInstall()}).observe(document.body,{childList:true,subtree:true});
  window.addEventListener('adelia:pwa-state',patchInstall);
})();
