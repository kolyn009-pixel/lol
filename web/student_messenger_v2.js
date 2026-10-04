/* The student inbox uses the same server conversation as Telegram and VK. */
(()=>{
'use strict';
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time=value=>{if(!value)return '';const d=new Date(value);if(Number.isNaN(d.getTime()))return '';const zone=window.StudentTime?.preference?.zone;if(!zone)return 'время уточняется';try{return new Intl.DateTimeFormat('ru-RU',{timeZone:zone,day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(d)}catch{return 'время недоступно'}};
function receipt(x){
 const read=!!x.read_at,state=read?'read':String(x.status||'SENT').toLowerCase();
 const label=read?'✓✓ Прочитано · '+time(x.read_at)+' · ваше время':state==='delivered'?'✓✓ Доставлено':state==='failed'?'Не отправлено':'✓ Отправлено';
 const hint=read?'Преподаватель открыл диалог в Аделии':state==='delivered'?'Сообщение доставлено в кабинет преподавателя':'Сообщение сохранено на сервере';
 return '<small class="student-chat-read receipt-'+esc(state)+'" title="'+esc(hint)+'">'+esc(label)+'</small>';
}
const api=async(path,options={})=>{const r=await fetch('/api'+path,{credentials:'same-origin',...options,headers:{...(options.body?{'Content-Type':'application/json'}:{})}});const data=await r.json().catch(()=>({}));if(!r.ok)throw new Error(data.error||'Не удалось связаться с сервером');return data};
let timer=null,last='',busy=false,polling=false;
const attachments=a=>!a?[]:Array.isArray(a)?a:Array.isArray(a.items)?a.items:[a];
function media(x){return attachments(x.attachment).map(a=>{const url=esc(a.url||''),name=esc(a.name||'Вложение');if(!url)return'';return String(a.kind||'').toLowerCase()==='photo'?'<a class="student-chat-photo" href="'+url+'" target="_blank" rel="noopener"><img src="'+url+'" alt="'+name+'" loading="lazy"></a>':'<a class="student-chat-file" href="'+url+'" target="_blank" rel="noopener">📎 '+name+'</a>'}).join('')}
function bubble(x){const mine=x.direction==='IN';return '<article class="student-chat-bubble '+(mine?'mine':'teacher')+'"><div class="student-chat-meta"><b>'+(mine?'Вы':'Преподаватель')+'</b><span>'+time(x.created_at)+'</span></div><div class="student-chat-text">'+esc(x.text||'')+'</div>'+media(x)+(mine?receipt(x):'')+'</article>'}
function messages(items){return items.length?items.map(bubble).join(''):'<div class="student-chat-empty"><b>Начните диалог 💜</b><span>Здесь можно спросить о занятии, ДЗ или расписании.</span></div>'}
const signature=items=>JSON.stringify(items.map(x=>[x.id,x.text,x.status,x.read_at,x.attachment]));
const helpTopics={lesson:'Когда следующий урок?',homework:'Где домашнее задание?',payment:'Что с оплатой?',contact:'Как связаться с преподавателем?'};
function helperMarkup(){return '<section class="student-helper" aria-label="Помощник Аделии"><div class="student-helper-title"><b>Помощник Аделии</b><small>Короткие ответы по данным кабинета · не преподаватель</small></div><div class="student-helper-topics">'+Object.entries(helpTopics).map(([key,label])=>'<button type="button" data-help-topic="'+key+'">'+esc(label)+'</button>').join('')+'</div><p id="studentHelperAnswer" role="status" aria-live="polite">Для личного вопроса напишите преподавателю ниже.</p></section>'}
async function help(topic){
  const answer=document.querySelector('#studentHelperAnswer');if(!answer||!Object.hasOwn(helpTopics,topic))return;
  answer.textContent='Проверяю данные Аделии…';
  try{
    let result='';
    if(topic==='lesson'){
      const d=await api('/student/dashboard'),l=d.next_lesson;
      if(!l)result='Следующего занятия пока нет в расписании. Уточните время у преподавателя.';
      else{const zone=d.student?.timezone?.zone||'Europe/Moscow',when=new Intl.DateTimeFormat('ru-RU',{timeZone:zone,day:'numeric',month:'long',hour:'2-digit',minute:'2-digit'}).format(new Date(l.start_at||l.start_time));result='Следующий урок: '+when+' ('+(d.student?.timezone?.label||zone)+'). Точное расписание — в разделе «Занятия».'}
    }else if(topic==='homework'){
      const d=await api('/student/homework'),items=Array.isArray(d.items)?d.items:[],active=items.filter(x=>['ASSIGNED','REVISION','SUBMITTED','UNDER_REVIEW'].includes(String(x.status||'').toUpperCase()));
      result=active.length?'ДЗ и прикреплённые файлы находятся в разделе «ДЗ». Сейчас там '+active.length+' активн. заданий.':'Активных ДЗ сейчас не вижу. Если задание прислали только в чате, уточните у преподавателя.';
    }else if(topic==='payment'){
      const d=await api('/student/payments'),items=Array.isArray(d.items)?d.items:[],current=items[0];
      const names={PAID:'оплата подтверждена',WAITING:'ожидает оплаты',PENDING:'проверяется преподавателем',RECEIPT_SENT:'проверяется преподавателем',REJECTED:'не подтверждена'};
      result=current?'Последний платёж №'+current.id+': '+(names[String(current.status||'').toUpperCase()]||'статус смотрите в разделе «Оплаты»')+'. Детали доступны в разделе «Оплаты».':'Платежей пока нет. Если вы уже перевели деньги, попросите родителя отметить оплату в его кабинете.';
    }else result='Напишите сообщение в поле ниже — его увидит преподаватель. Помощник не отвечает за него и не принимает решений по занятиям или оплате.';
    if(answer.isConnected)answer.textContent=result;
  }catch{if(answer.isConnected)answer.textContent='Не удалось получить свежие данные. Попробуйте ещё раз или напишите преподавателю.'}
}
async function screen(){
  await window.StudentTime?.load().catch(()=>{});
  const data=await api('/student/messages?limit=200');
  const items=data.items||[];last=signature(items);
  return '<section class="student-chat-card"><header class="student-chat-head"><div class="student-chat-avatar">А</div><div><h2>Сообщения</h2><p>Переписка с преподавателем сохраняется в Аделии</p></div></header>'+helperMarkup()+'<div class="student-chat-history" id="studentChatHistory" role="log" aria-label="История сообщений">'+messages(items)+'</div><form class="student-chat-compose" id="studentChatForm"><label class="student-chat-attach" aria-label="Прикрепить фото или файл">📎<input id="studentChatFile" type="file" accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt" hidden></label><textarea id="studentChatText" maxlength="4000" placeholder="Сообщение преподавателю…" rows="1"></textarea><button type="submit" aria-label="Отправить">➤</button></form><div class="student-chat-file-name" id="studentChatFileName"></div><div class="student-chat-state" id="studentChatState" aria-live="polite"></div></section>'
}
async function refresh(force=false){
  const list=document.querySelector('#studentChatHistory');if(!list||polling||document.hidden)return;
  polling=true;
  try{
    const data=await api('/student/messages?limit=200'),items=data.items||[],next=signature(items);
    if(force||next!==last){const stick=list.scrollHeight-list.scrollTop-list.clientHeight<90;list.innerHTML=messages(items);last=next;if(stick||force)list.scrollTop=list.scrollHeight}
    const state=document.querySelector('#studentChatState');if(state&&state.dataset.networkError){state.textContent='';delete state.dataset.networkError}
  }catch{const state=document.querySelector('#studentChatState');if(state&&!busy){state.textContent='Нет соединения. Сообщение можно отправить после восстановления сети.';state.dataset.networkError='1'}}
  finally{polling=false}
}
async function badge(){try{const d=await api('/student/dashboard'),n=Number(d.unread_messages||0),nav=document.querySelector('[data-tab="messages"]');if(!nav)return;let el=nav.querySelector('.chat-nav-badge');if(!el){el=document.createElement('i');el.className='chat-nav-badge';nav.appendChild(el)}el.textContent=n>99?'99+':String(n);el.hidden=!n}catch{}}
async function upload(file){const body=new FormData();body.append('file',file);const r=await fetch('/api/student/message-media/upload',{method:'POST',credentials:'same-origin',body});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'Не удалось загрузить файл');return d.attachment}
async function send(event){
  event.preventDefault();if(busy)return;
  const form=event.currentTarget,input=form.querySelector('#studentChatText'),file=form.querySelector('#studentChatFile')?.files?.[0],text=input.value.trim(),status=document.querySelector('#studentChatState'),button=form.querySelector('button[type="submit"]');
  if(!text&&!file)return;busy=true;button.disabled=true;status.textContent=file?'Загружаю файл…':'Отправляю…';
  try{
    const attachment=file?await upload(file):null;
    await api('/student/message',{method:'POST',body:JSON.stringify({text,attachment})});
    input.value='';input.style.height='';form.querySelector('#studentChatFile').value='';
    document.querySelector('#studentChatFileName').textContent='';status.textContent='Отправлено';
    await refresh(true);await badge();
  }catch(error){status.textContent='Не удалось отправить: '+error.message+' — текст сохранён, попробуйте ещё раз.'}
  finally{busy=false;button.disabled=false}
}
function stop(){if(timer){clearInterval(timer);timer=null}}
function mount(){
  stop();const list=document.querySelector('#studentChatHistory');if(!list)return;
  list.scrollTop=list.scrollHeight;
  document.querySelectorAll('[data-help-topic]').forEach(button=>button.addEventListener('click',()=>help(button.dataset.helpTopic)));
  const form=document.querySelector('#studentChatForm');if(form){form.addEventListener('submit',send);if(window.adeliaDesktop?.desktop){form.addEventListener('dragover',event=>{event.preventDefault();form.classList.add('drag-over')});form.addEventListener('dragleave',()=>form.classList.remove('drag-over'));form.addEventListener('drop',event=>{event.preventDefault();form.classList.remove('drag-over');const dropped=event.dataTransfer?.files?.[0],input=form.querySelector('#studentChatFile');if(!dropped||!input)return;const transfer=new DataTransfer();transfer.items.add(dropped);input.files=transfer.files;input.dispatchEvent(new Event('change'))})}}
  const file=document.querySelector('#studentChatFile');if(file)file.addEventListener('change',()=>{const name=document.querySelector('#studentChatFileName');if(name)name.textContent=file.files?.[0]?.name||''});
  const input=document.querySelector('#studentChatText');if(input)input.addEventListener('input',()=>{input.style.height='auto';input.style.height=Math.min(120,input.scrollHeight)+'px'});
  timer=setInterval(()=>{if(!document.hidden)refresh()},4000);badge();
}
window.AdeliaStudentMessenger={screen,mount,stop,refresh};
window.addEventListener('adelia:student-timezone-changed',()=>refresh(true));
if(document.querySelector('.nav-item.active[data-tab="messages"]'))window.AdeliaStudentRender?.('messages');
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
setInterval(badge,30000);badge();
})();
