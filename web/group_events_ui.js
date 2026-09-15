(()=>{
  const $=s=>document.querySelector(s);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money=n=>Number(n||0).toLocaleString('ru-RU')+' ₽';
  const fmtDate=v=>v?new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short'}).format(new Date(v)):'—';
  const fmtTime=v=>v?new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit'}).format(new Date(v)):'—';
  let groups=[];let mounted=false;
  async function api(path,opt={}){const r=await fetch('/api'+path,{credentials