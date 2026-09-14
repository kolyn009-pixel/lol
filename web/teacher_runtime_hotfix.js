(function(){
  'use strict';
  function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text)n.textContent=text;return n}
  function mount(){
    const header=document.querySelector('.teacher-shell>main>header');
    if(!header||header.querySelector('.adelia-runtime-actions'))return;
    const actions=el('div','adelia-runtime-actions');
    const status=el('button','adelia-status-chip');status.type='button';status.innerHTML='<span class="adelia-status-dot"></span><span>Проверка сервера…</span>';
    status.addEventListener('click',()=>{const b=document.querySelector('[data-view="health"]');if(b)b.click()});
    const install=el('button','adelia-install-teacher','Установить приложение');install.type='button';
    install.addEventListener('click',async()=>{
      const api=window.AdeliaPWA;
      if(api&&typeof api.install==='function'){
        const r=await api.install().catch(()=>null);
        if(r&&r.status==='manual')alert(r.message||'Добавьте Аделию на главный экран через меню браузера.');
        else if(r&&r.status==='unavailable')alert('На компьютере откройте Аделию в Chrome или Edge и повторите установку. На Mac в Safari также можно использовать «Файл → Добавить в Dock».');
        return;
      }
      alert('Для установки на компьютер откройте Аделию в Chrome или Edge.');
    });
    actions.append(status,install);header.appendChild(actions);

    fetch('/api/health',{credentials:'same-origin',cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(String(r.status));return r.json()}).then(()=>{
      status.classList.add('ok');status.querySelector('span:last-child').textContent='Сервер работает';
    }).catch(()=>{
      status.classList.add('bad');status.querySelector('span:last-child').textContent='Проблема с сервером';
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})();
