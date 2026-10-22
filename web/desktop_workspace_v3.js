(()=>{'use strict';
if(!window.adeliaDesktop?.desktop||location.pathname.startsWith('/app/parent')||window.__adeliaWorkspaceV3)return;
window.__adeliaWorkspaceV3=true;
const D=window.adeliaDesktop;
let panel=null,frame=null,lastFocus=null,ready=false,open=false,timeout=null;
const launch=document.createElement('button');launch.type='button';launch.className='v3-chat-launcher';launch.textContent='Сообщения';launch.setAttribute('aria-expanded','false');launch.setAttribute('aria-controls','v3ChatPanel');document.body.append(launch);
function signal(){if(frame?.contentWindow&&ready)frame.contentWindow.postMessage({type:'adelia:chat-visibility',visible:open},location.origin)}
function close(){if(!panel)return;open=false;signal();panel.hidden=true;launch.setAttribute('aria-expanded','false');lastFocus?.focus()}
function show(){lastFocus=document.activeElement;
 if(!panel){panel=document.createElement('section');panel.id='v3ChatPanel';panel.className='v3-chat-panel';panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Сообщения');panel.innerHTML='<header><b>Сообщения</b><div><button type="button" data-chat-retry hidden>Повторить</button> <button type="button" data-chat-close aria-label="Закрыть сообщения">✕</button></div></header><div class="v3-chat-feedback" role="status">Загружаю переписку…</div>';frame=document.createElement('iframe');frame.title='Переписка в Аделии';frame.src='/app/quick_chat.html?v=20261022-workspace3';panel.append(frame);document.body.append(panel);panel.querySelector('[data-chat-close]').onclick=close;panel.querySelector('[data-chat-retry]').onclick=()=>{ready=false;feedback('Загружаю переписку…');frame.src='/app/quick_chat.html?v=20261022-workspace3&retry='+Date.now();watch()};watch()}
 panel.hidden=false;open=true;launch.setAttribute('aria-expanded','true');signal();panel.querySelector('[data-chat-close]').focus()
}
function feedback(text){if(!panel)return;panel.querySelector('.v3-chat-feedback').textContent=text;panel.querySelector('[data-chat-retry]').hidden=!text||text==='Загружаю переписку…'}
function watch(){clearTimeout(timeout);timeout=setTimeout(()=>{if(!ready)feedback('Переписка не загрузилась. Проверьте соединение и нажмите «Повторить».')},15000)}
window.addEventListener('message',e=>{if(e.origin!==location.origin||e.source!==frame?.contentWindow)return;if(e.data?.type==='adelia:chat-ready'){ready=true;clearTimeout(timeout);feedback('');signal()}else if(e.data?.type==='adelia:chat-error'){clearTimeout(timeout);feedback('Не удалось открыть переписку. Попробуйте ещё раз.')}});
launch.onclick=()=>open?close():show();
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&open){e.preventDefault();close()}});
const tools=document.createElement('div');tools.className='v3-tools';tools.innerHTML='<button type="button" data-yandex-login>Яндекс Телемост</button><span class="v3-account-status" role="status"></span>';
const host=document.querySelector('.header-actions')||document.querySelector('.desktop-top-actions')||document.querySelector('.topbar');if(host)host.append(tools);
tools.querySelector('button').onclick=async e=>{const b=e.currentTarget;b.disabled=true;const status=tools.querySelector('[role="status"]');status.textContent='Открываю Яндекс…';try{const ok=await D.openLessonTool('meeting','https://telemost.yandex.ru/');status.textContent=ok?'Войдите в Яндекс в окне Телемоста.':'Не удалось открыть Телемост.'}catch{status.textContent='Не удалось открыть Телемост. Повторите попытку.'}finally{b.disabled=false}};
window.AdeliaQuickChat={open:show,close};
})();
