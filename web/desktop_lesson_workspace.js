(()=>{'use strict';
if(!window.adeliaDesktop?.desktop||window.__adeliaLessonWorkspaceUi)return;
window.__adeliaLessonWorkspaceUi=true;
const D=window.adeliaDesktop;
let root=null,timer=null,last='';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={together:'Вместе','board-focus':'Фокус на доске','mini-video':'Мини-видео','hide-video':'Видео скрыто','dual-screen':'2 монитора'};
function button(mode,label,state){const active=state.mode===mode;const disabled=mode==='dual-screen'&&!state.dualScreenAvailable;return '<button type="button" data-layout="'+mode+'" class="'+(active?'active ':'')+(disabled?'disabled':'')+'" '+(disabled?'disabled':'')+'>'+label+'</button>'}
function shell(){if(root&&document.contains(root))return root;root=document.createElement('aside');root.id='adeliaDesktopLessonBar';root.className='adelia-desktop-lessonbar';root.setAttribute('aria-label','Рабочее пространство занятия');document.body.append(root);return root}
function render(state){if(!state?.active){if(root)root.hidden=true;last='';return}const sig=JSON.stringify([state.mode,state.meetingOpen,state.meetingVisible,state.boardOpen,state.boardVisible,state.displayCount]);if(sig===last&&root&&!root.hidden)return;last=sig;const el=shell();el.hidden=false;el.innerHTML='<div class="adl-brand"><span class="adl-dot"></span><div><b>Урок в Аделии</b><small>'+esc(labels[state.mode]||'Рабочее пространство')+'</small></div></div><div class="adl-modes">'+button('together','Вместе',state)+button('board-focus','Доска',state)+button('mini-video','Мини-видео',state)+button('dual-screen','2 монитора',state)+'</div><div class="adl-state"><span class="'+(state.meetingOpen?'on':'')+'">Видео</span><span class="'+(state.boardOpen?'on':'')+'">Доска</span></div><button type="button" class="adl-video" data-video>' +(state.meetingVisible?'Скрыть видео':'Показать видео')+'</button><button type="button" class="adl-close" data-close title="Закрыть окна занятия">×</button>';bind(el)}
function bind(el){el.querySelectorAll('[data-layout]').forEach(b=>b.onclick=async()=>{if(b.disabled)return;b.disabled=true;try{render(await D.setLessonLayout(b.dataset.layout))}catch(_){}finally{b.disabled=false}});el.querySelector('[data-video]')?.addEventListener('click',async()=>{try{render(await D.toggleLessonVideo())}catch(_){}});el.querySelector('[data-close]')?.addEventListener('click',async()=>{if(!confirm('Закрыть окна Телемоста и доски? Само занятие в Аделии не завершится.'))return;try{await D.endLessonWorkspace();setTimeout(refresh,120)}catch(_){}})}
async function refresh(){try{render(await D.getLessonLayout())}catch(_){}}
function start(){refresh();if(timer)clearInterval(timer);timer=setInterval(()=>{if(!document.hidden)refresh()},1600)}
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
window.addEventListener('beforeunload',()=>{if(timer)clearInterval(timer)});
start();
})();