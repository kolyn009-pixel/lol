(function(){
  const api=async(path,opt={})=>{
    const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});
    const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'Ошибка');return j;
  };
  function addShellActions(){
    const host=document.querySelector('header')||document.querySelector('.topbar');
    if(!host||document.querySelector('#adeliaShellActions'))return;
    const box=document.createElement('div');box.id='adeliaShellActions';box.className='adelia-shell-actions';
    const install=document.createElement('button');install.id='installAdelia';install.type='button';install.className='shell-action';install.textContent='＋ Установить';
    const logout=document.createElement('button');logout.id='logoutAdelia';logout.type='button';logout.className='shell-action';logout.textContent='Выйти';
    box.append(install,logout);host.append(box);
    const refresh=()=>{install.hidden=window.AdeliaPWA?.isStandalone?.()||!window.AdeliaPWA?.canInstall?.()};refresh();
    window.addEventListener('adelia:pwa-state',refresh);
    install.onclick=async()=>{await window.AdeliaPWA?.install?.();refresh()};
    logout.onclick=async()=>{logout.disabled=true;try{await api('/auth/logout',{method:'POST',body:'{}'})}catch{}location.replace('/app/')};
  }
  function deepLink(){
    const q=new URLSearchParams(location.search);
    const homework=q.get('homework');
    const lesson=q.get('lesson');
    const view=q.get('view')||q.get('tab');
    if(homework&&/^\d+$/.test(homework)&&typeof window.openHomework==='function'){window.openHomework(homework);return true}
    if(lesson&&/^\d+$/.test(lesson)){location.replace('/app/lesson/?id='+encodeURIComponent(lesson));return true}
    if(view&&['home','schedule','homework','payments','messages','profile'].includes(view)&&typeof window.render==='function'){window.render(view);return true}
    return false;
  }
  function boot(){addShellActions();setTimeout(deepLink,0)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
