(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=s=>{if(!s)return '';try{return new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(s))}catch{return s}};
const api=async(path,opt={})=>{const r=await fetch('/api'+path,{credentials:'same-origin',headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'Ошибка');return j};
let poll=null;

function avatar(){return '<div class="student-chat-avatar">A</div>'}
function mediaItems(a){if(!a)return [];if(Array.isArray(a))return a;if(Array.isArray(a.items))return a.items;return [a]}
function mediaHtml(x){return mediaItems(x.attachment).map(a=>{const url=esc(a.url||'');const name=esc(a.name||'Вложение');if(!url)return '';return String(a.kind||'').toLowerCase()==='photo'?'<a class="student-chat-photo" href="'+url+'" target="_blank" rel="noopener"><img src="'+url+'" alt="'+name+'" loading="lazy"></a>':'<a class="student-chat-file" href="'+url+'" target="_blank" rel="noopener">📎 '+name+'</a>'}).join('')}
function bubble(x){const mine=x.direction==='IN';return `<article class="student-chat-bubble ${mine?'mine':'teacher'}"><div class="student-chat-meta"><b>${mine?'Вы':'Преподаватель'}</b><span>${fmt(x.created_at)}</span></div><div class="student-chat-text">${esc(x.text||'')}</div>${mediaHtml(x)}${!mine&&x.read_at?'<small class="student-chat-read">Прочитано</small>':''}</article>`}

async function chatScreen(){
  const d=await api('/student/messages?limit=200');
  const items=d.items||[];
  setTimeout(()=>{const list=document.querySelector('#studentChatHistory');if(list)list.scrollTop=list.scrollHeight},0);
  return `<section class="student-chat-card"><header class="student-chat-head">${avatar()}<div><h2>Чат с преподавателем</h2><p>Основная переписка хранится в Adelia</p></div><span class="student-chat-live">● online</span></header><div class="student-chat-history" id="studentChatHistory">${items.length?items.map(bubble).join(''):'<div class="student-chat-empty"><b>Начните диалог 💜</b><span>Здесь можно задать вопрос по занятию, домашке или расписанию.</span></div>'}</div><form class="student-chat-compose" id="studentChatForm"><label class="student-chat-attach" aria-label="Прикрепить фото или файл">📎<input id="studentChatFile" type="file" accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt" hidden></label><textarea id="studentChatText" maxlength="4000" placeholder="Сообщение преподавателю…" rows="1"></textarea><button type="submit" aria-label="Отправить">➤</button></form><div class="student-chat-file-name" id="studentChatFileName"></div><div class="student-chat-state" id="studentChatState"></div></section>`;
}

async function uploadFile(file){const fd=new FormData();fd.append('file',file);const r=await fetch('/api/student/message-media/upload',{method:'POST',credentials:'same-origin',body:fd});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'Не удалось загрузить файл');return j.attachment}
async function send(ev){
  ev.preventDefault();const text=document.querySelector('#studentChatText')?.value.trim()||'';const file=document.querySelector('#studentChatFile')?.files?.[0];if(!text&&!file)return;
  const btn=ev.currentTarget.querySelector('button');const state=document.querySelector('#studentChatState');if(btn)btn.disabled=true;if(state)state.textContent=file?'Загружаю вложение…':'Отправляю…';
  try{const attachment=file?await uploadFile(file):null;await api('/student/message',{method:'POST',body:JSON.stringify({text,attachment})});if(typeof window.render==='function')await window.render('messages');}
  catch(e){if(state)state.textContent='Не удалось отправить: '+e.message;if(btn)btn.disabled=false}
}

function bind(){const file=document.querySelector('#studentChatFile');if(file&&!file.dataset.bound){file.dataset.bound='1';file.addEventListener('change',()=>{const n=document.querySelector('#studentChatFileName');if(n)n.textContent=file.files?.[0]?.name||''})}const form=document.querySelector('#studentChatForm');if(form&&!form.dataset.bound){form.dataset.bound='1';form.addEventListener('submit',send)}const ta=document.querySelector('#studentChatText');if(ta&&!ta.dataset.grow){ta.dataset.grow='1';ta.addEventListener('input',()=>{ta.style.height='auto';ta.style.height=Math.min(120,ta.scrollHeight)+'px'})}}

async function refreshBadge(){
  try{const d=await api('/student/dashboard');const n=Number(d.unread_messages||0);let nav=document.querySelector('[data-tab="messages"]');if(nav){let badge=nav.querySelector('.chat-nav-badge');if(!badge){badge=document.createElement('i');badge.className='chat-nav-badge';nav.appendChild(badge)}badge.textContent=n>99?'99+':String(n);badge.hidden=!n}}
  catch{}
}

const originalRender=window.render;
window.messages=chatScreen;

if(typeof originalRender==='function'){
  window.render=async function(view,...args){const out=await originalRender.call(this,view,...args);if(view==='messages'){bind();clearInterval(poll);poll=setInterval(async()=>{if(!document.querySelector('#studentChatHistory'))return;try{const before=document.querySelectorAll('.student-chat-bubble').length;const d=await api('/student/messages?limit=200');if((d.items||[]).length!==before)await window.render('messages')}catch{}},8000);await refreshBadge()}else{clearInterval(poll);await refreshBadge()}return out};
}

document.addEventListener('DOMContentLoaded',()=>{refreshBadge();setInterval(refreshBadge,30000)});
document.addEventListener('click',e=>{const b=e.target.closest('[data-tab="messages"],[data-go="messages"]');if(!b)return;setTimeout(bind,0)},true);
})();
