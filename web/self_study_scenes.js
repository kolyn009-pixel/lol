(()=>{'use strict';
if(window.AdeliaStudyScenes)return;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tc=s=>`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;
function seconds(s){if(!/^\d{1,4}:[0-5]\d$/.test(s))throw Error('Таймкод укажи как минуты:секунды, например 12:30.');const [m,t]=s.split(':').map(Number);return m*60+t;}
async function api(path,body){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
 try{const r=await fetch('/api/teacher/self-study/scenes'+path,{credentials:'same-origin',cache:'no-store',signal:controller.signal,...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const d=await r.json();if(!r.ok)throw Error(r.status===401?'Войди в кабинет преподавателя.':'Не удалось сохранить или загрузить сцену. Проверь поля и попробуй ещё раз.');return d;}
 catch(e){if(e.name==='AbortError')throw Error('Сервер отвечает долго. Повтори запрос: запись не продублируется.');throw e;}finally{clearTimeout(timer);}
}
async function open(root,options){
 const shows=options.resources.filter(x=>x.language===options.language&&x.study_tasks);
 if(!shows.length)return;
 root.innerHTML=`<div class="ss-heading"><button class="ss-secondary" data-scenes-back>← К программе</button><h2>Журнал сцен</h2></div><section class="ss-panel"><p class="ss-muted">Выбери сцену на 2–5 минут. После просмотра назови конфликт, вспомни до трёх выражений и перескажи своими словами. Поля сюжета и понимания — самоотчёт.</p><form data-scene-form class="ss-goals"><label>Сериал<select name="resource_id">${shows.map(x=>`<option value="${esc(x.id)}">${esc(x.title)}</option>`).join('')}</select></label><div class="ss-phrases"><label>Сезон<input name="season" type="number" min="1" max="999" value="1" required></label><label>Серия<input name="episode" type="number" min="1" max="999" value="1" required></label></div><div class="ss-phrases"><label>Начало · мин:сек<input name="start" type="text" value="0:00" required></label><label>Конец · мин:сек<input name="end" type="text" value="3:00" required></label></div><label>Что понял?<select name="comprehension"><option value="little">Пока мало</option><option value="gist">Основной смысл</option><option value="details">Смысл и детали</option></select></label><label>Кто чего добивается? Короткая заметка, можно по-русски<textarea name="summary" maxlength="1500" rows="3"></textarea></label><p class="ss-muted">Выражения необязательны. Запиши точно по субтитрам; проверь смысл. Завтра они появятся в повторении.</p>${[0,1,2].map(i=>`<div class="ss-phrases"><label>Выражение ${i+1}<input name="expression${i}" type="text" maxlength="200" dir="auto"></label><label>Значение<input name="meaning${i}" type="text" maxlength="200"></label></div>`).join('')}<button type="submit" class="ss-primary">Сохранить сцену</button><p class="ss-status" data-scenes-status role="status"></p></form></section><section class="ss-panel" style="margin-top:18px"><h3>Сохранённые сцены</h3><div data-scenes-list role="status">Загружаю…</div></section><div data-scenes-voice></div>`;
 const form=root.querySelector('form'),out=root.querySelector('[data-scenes-status]'),list=root.querySelector('[data-scenes-list]');
 let requestId=crypto.randomUUID(),saving=false,version=0;
 root.querySelector('[data-scenes-back]').onclick=options.back;
 form.oninput=()=>{requestId=crypto.randomUUID();options.dirty(true);};
 async function refresh(){
  const v=++version;
  try{const d=await api('?language='+options.language);if(!list.isConnected||v!==version)return;
   list.innerHTML=`<p class="ss-muted">${esc(d.note)}</p>`+d.items.map(item=>`<article class="ss-reference"><h4>${esc(shows.find(x=>x.id===item.resource_id)?.title||item.resource_id)} · S${item.season} E${item.episode}</h4><p>${tc(item.start_seconds)}–${tc(item.end_seconds)} · понимание: ${esc({little:'пока мало',gist:'основной смысл',details:'смысл и детали'}[item.comprehension])}</p><p>${esc(item.summary)}</p>${item.phrases.map(p=>`<p><bdi>${esc(p.expression)}</bdi> — ${esc(p.meaning)}</p>`).join('')}<button class="ss-secondary" data-scene-speak="${item.id}">Пересказать эту сцену</button></article>`).join('');
   if(!d.items.length)list.innerHTML+='<p class="ss-muted">Пока нет записей.</p>';
   list.querySelectorAll('[data-scene-speak]').forEach(b=>b.onclick=()=>{const item=d.items.find(x=>x.id===Number(b.dataset.sceneSpeak));window.AdeliaStudyVoice?.mount(root.querySelector('[data-scenes-voice]'),{owner_id:options.owner_id,lesson_id:'scene:'+item.id,language:item.language,prompt:'Перескажи сцену: кто чего хотел, что изменилось и что бы ты уточнил? Твоя заметка: '+item.summary});});
  }catch(e){if(list.isConnected){list.textContent=e.message;const retry=document.createElement('button');retry.className='ss-secondary';retry.textContent='Повторить загрузку';retry.onclick=refresh;list.append(retry);}}
 }
 form.onsubmit=async event=>{
  event.preventDefault();if(saving)return;
  try{
   const values=Object.fromEntries(new FormData(form)),phrases=[];
   for(let i=0;i<3;i++){const expression=values['expression'+i].trim(),meaning=values['meaning'+i].trim();if(expression||meaning){if(!expression||!meaning)throw Error('Для выражения укажи и текст, и значение.');phrases.push({expression,meaning});}}
   const body={resource_id:values.resource_id,season:Number(values.season),episode:Number(values.episode),start_seconds:seconds(values.start),end_seconds:seconds(values.end),summary:values.summary,comprehension:values.comprehension,phrases,request_id:requestId};
   if(body.end_seconds<=body.start_seconds||body.end_seconds-body.start_seconds>900)throw Error('Конец должен быть позже начала. Для разбора выбери не более 15 минут.');
   saving=true;options.busy(true);form.querySelectorAll('input,select,textarea,button').forEach(x=>x.disabled=true);out.textContent='Сохраняю…';
   await api('/save',body);if(!form.isConnected)return;
   options.dirty(false);requestId=crypto.randomUUID();form.reset();out.textContent='Сцена сохранена. Выражения назначены на завтра; самооценка не меняет баллы контрольных.';await refresh();
  }catch(e){if(out.isConnected)out.textContent=e.message;}
  finally{saving=false;options.busy(false);if(form.isConnected)form.querySelectorAll('input,select,textarea,button').forEach(x=>x.disabled=false);}
 };
 await refresh();
}
window.AdeliaStudyScenes={open};
})();
