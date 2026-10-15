/* Read-only action overview; decisions remain in their canonical screens. */
(()=>{
'use strict';
if(window.__adeliaTeacherAttention)return;window.__adeliaTeacherAttention=true;
const root=()=>document.querySelector('.teacher-dashboard-v2');
let loading=false,last=0;
const api=async path=>{const r=await fetch('/api'+path,{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw new Error('unavailable');return r.json()};
const count=x=>Math.max(0,Number(x)||0);
function card(item,featured=false){return '<button type="button" class="attention-card'+(featured?' featured':'')+'" data-attention="'+item.kind+'"><span>'+item.label+'</span><strong>'+item.value+'</strong><small>'+item.hint+'</small></button>'}
function ensure(){const host=root();if(!host)return null;let section=host.querySelector('#teacherAttention');if(section)return section;section=document.createElement('section');section.id='teacherAttention';section.className='teacher-attention';section.innerHTML='<div class="attention-heading"><div><small>Важное сейчас</small><h2>Требует внимания</h2></div><div><span id="attentionFreshness" role="status">Загружаю…</span><button type="button" data-attention-refresh style="min-height:44px;margin-left:8px">Обновить</button></div></div><div class="attention-grid" id="attentionGrid"></div>';const after=host.querySelector('.today-command');after?.after(section);host.classList.add('has-attention');return section}
async function refresh(force=false){
  const section=ensure();if(!section||loading||!force&&Date.now()-last<30000)return;
  loading=true;
  try{
    const [dash,messages,receipts,requests]=await Promise.allSettled([
      api('/teacher/dashboard'),api('/teacher/messages?limit=200&unread=1'),
      api('/teacher/finance/receipts?status=WAITING&limit=1'),api('/teacher/requests')
    ]);
    if(!section.isConnected)return;
    const value=(r,read)=>r.status==='fulfilled'?count(read(r.value)):null;
    const d=dash.status==='fulfilled'?dash.value:{};
    const items=[
      {kind:'messages',label:'Новые диалоги',value:value(messages,x=>(x.items||[]).length),hint:'Ответить'},
      {kind:'payments',label:'Переводы на проверке',value:value(receipts,x=>x.summary?.waiting),hint:'Сверить в Сбере'},
      {kind:'reviews',label:'Работы на проверке',value:value(dash,()=>d.pending_reviews?.length),hint:'Проверить ДЗ'},
      {kind:'requests',label:'Заявки на занятия',value:value(requests,x=>count(x.counts?.trial)+count(x.counts?.lesson)+count(x.counts?.schedule_groups??x.counts?.schedule)),hint:'Открыть заявки'}
    ];
    const available=items.filter(x=>x.value>0),primary=available[0],grid=section.querySelector('#attentionGrid');
    grid.innerHTML=primary?card(primary,true)+(available.length>1?'<div class="attention-secondary">'+available.slice(1).map(x=>card(x)).join('')+'</div>':'')
      :'<div class="attention-clear"><b>'+([dash,messages,receipts,requests].some(x=>x.status==='rejected')?'Не все данные доступны':'На сегодня всё разобрано')+'</b><p>'+(items.some(x=>x.value===null)?'Обновите страницу, чтобы проверить недоступные очереди.':'Новые задачи появятся здесь, когда потребуется ваше решение.')+'</p></div>';
    section.querySelector('#attentionFreshness').textContent=[dash,messages,receipts,requests].every(x=>x.status==='fulfilled')?'Обновлено сейчас':'Часть данных недоступна';
    last=Date.now();
  }finally{loading=false}
}
function open(kind){
  if(kind==='requests'){document.querySelector('[data-request-center]')?.click();return}
  if(kind==='payments'){
    const promise=window.teacherPayments?.();
    Promise.resolve(promise).then(()=>document.querySelector('[data-pay-tab="receipts"]')?.click()).catch(()=>{});
    return;
  }
  document.querySelector('aside nav [data-view="'+kind+'"]')?.click();
}
document.addEventListener('click',e=>{const b=e.target.closest('#teacherAttention [data-attention]');if(b)open(b.dataset.attention);if(e.target.closest('[data-attention-refresh]'))refresh(true)});
new MutationObserver(()=>{if(root())refresh()}).observe(document.querySelector('#app'),{childList:true});
setInterval(()=>{if(!document.hidden&&root())refresh(true)},45000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh(true)});
setTimeout(()=>refresh(),500);
})();

