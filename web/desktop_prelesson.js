(()=>{'use strict';
if(!window.adeliaDesktop?.desktop||window.__adeliaPrelessonUi)return;
window.__adeliaPrelessonUi=true;
const D=window.adeliaDesktop;
let root=null,timer=null,lastId=null,snoozeUntil=0;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function fmtTime(v,timezone){
 const zone=timezone?.zone||window.StudentTime?.preference?.zone;
 if(!zone)return '—';
 try{return new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',timeZone:zone}).format(new Date(v))}catch(_){return'—'}
}
function diffMin(v){return (new Date(v).getTime()-Date.now())/60000}
function countdown(v){const ms=new Date(v).getTime()-Date.now();if(ms<=0)return'Занятие начинается';const m=Math.max(0,Math.ceil(ms/60000));if(m<60)return m===1?'Через минуту':'Через '+m+' мин';const h=Math.floor(m/60),r=m%60;return r?'Через '+h+' ч '+r+' мин':'Через '+h+' ч'}
function shell(){if(root&&document.contains(root))return root;root=document.createElement('section');root.id='adeliaDesktopPrelesson';root.className='adelia-prelesson';root.setAttribute('aria-live','polite');document.body.append(root);return root}
function hide(){if(root)root.hidden=true}
function render(lesson){
 if(!lesson?.id||!lesson.start_time){hide();lastId=null;return}
 const d=diffMin(lesson.start_time);
 if(d>30||d<-Math.max(10,Number(lesson.duration_minutes||60))){hide();return}
 if(Date.now()<snoozeUntil&&d>5){hide();return}
 const urgent=d<=5; const el=shell(); el.hidden=false; el.classList.toggle('urgent',urgent);
 const same=String(lastId)===String(lesson.id); lastId=lesson.id;
 el.innerHTML='<div class="apl-accent"></div><div class="apl-copy"><span class="apl-kicker">'+(urgent?'Скоро начинаем':'Ближайшее занятие')+'</span><b>'+esc(lesson.subject||'Занятие')+' · '+esc(fmtTime(lesson.start_time,lesson.timezone))+'</b><small>'+esc(countdown(lesson.start_time))+(lesson.timezone?.label?' · '+esc(lesson.timezone.label):'')+(lesson.started?' · уже началось':'')+'</small></div><div class="apl-actions"><button type="button" class="apl-later" data-later>Позже</button><button type="button" class="apl-check" data-check>Камера и звук</button><button type="button" class="apl-open" data-open>Открыть занятие</button></div>';
 el.querySelector('[data-open]').onclick=async()=>{try{await D.openRoute('lesson',lesson.id)}catch(_){}};
 el.querySelector('[data-check]').onclick=async()=>{try{await D.openDeviceCheck(lesson.id)}catch(_){}};
 el.querySelector('[data-later]').onclick=()=>{snoozeUntil=Date.now()+5*60000;hide()};
 if(!same&&urgent&&el.animate)el.animate([{transform:'translateY(10px)',opacity:.2},{transform:'translateY(0)',opacity:1}],{duration:260,easing:'cubic-bezier(.2,.8,.2,1)'});
}
async function refresh(){try{const s=await D.getUxState();render(s?.dashboard?.nextLesson||null)}catch(_){hide()}}
function start(){refresh();timer=setInterval(()=>{if(!document.hidden)refresh()},15000)}
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
window.addEventListener('beforeunload',()=>{if(timer)clearInterval(timer)});
start();
})();
