(()=>{'use strict';
if(window.AdeliaStudyDay)return;
let context=null,session=null,revision=0;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,body){
 const role=['student','parent'].includes(document.body.dataset.studyRole)?document.body.dataset.studyRole:'teacher';
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
 try{const r=await fetch('/api/'+role+'/self-study/day'+path,{credentials:'same-origin',cache:'no-store',signal:controller.signal,...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const d=await r.json();
 if(!r.ok){const messages={practice_result_required:'Сначала выполни задания этого урока и сохрани проверку.',review_result_required:'Повтори хотя бы одну карточку или выбери «Сегодня без повторения».',session_changed:'Занятие изменилось на другом устройстве. Нажми «Обновить занятие».',reflection_required:'Отметь, как получилось применить материал.',family_access_required:'Для языков нужно семейное приглашение.'};throw Error(messages[d.error]||'Не удалось обновить занятие. Попробуй ещё раз.');}return d;
 }catch(e){if(e.name==='AbortError')throw Error('Ответ задержался. Обнови занятие, чтобы проверить сохранённый шаг.');throw e;}finally{clearTimeout(timer);}
}
async function mount(host,options){
 const token=++revision;context=options;session=null;
 host.innerHTML='<p role="status">Подбираю занятие на сегодня…</p>';
 try{const d=await api('?language='+options.language);if(!host.isConnected||token!==revision)return;session=d.session;
 const times=[...new Set([5,10,25,options.minutes])].filter(x=>x<=options.minutes).sort((a,b)=>a-b);
 host.innerHTML=`<span class="ss-eyebrow">Твой следующий шаг</span><h3>${session?'Продолжить с сохранённого места':'Начать сегодня'}</h3><p class="ss-muted">${session?'План сохранён на сервере. Можно продолжить с другого устройства.':'Выбери время на этот язык сейчас. План начнётся с подходящего материала и сохранит остановку.'}</p>${session?'<button class="ss-primary" data-day-resume>Продолжить занятие</button>':`<div class="ss-actions">${times.map(n=>`<button class="${n===options.minutes?'ss-primary':'ss-secondary'}" data-day-start="${n}">${n} минут</button>`).join('')}</div>`}<p class="ss-muted">Пропуск дня ничего не обнуляет. Время — ориентир, можно остановиться раньше.</p><p class="ss-status" data-day-widget-status role="status"></p>`;
 host.querySelector('[data-day-resume]')?.addEventListener('click',resume);
 host.querySelectorAll('[data-day-start]').forEach(b=>b.onclick=async()=>{
  if(!options.canLeave())return;host.querySelectorAll('button').forEach(x=>x.disabled=true);
  try{const result=await api('/start',{language:options.language,minutes:Number(b.dataset.dayStart),timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'Europe/Moscow'});if(token!==revision||!host.isConnected)return;
   if(result.action==='diagnostic'){options.diagnostic();return;}if(['route_check','route_review'].includes(result.action)){options.route();return;}session=result.session;render(result.note);
  }catch(e){if(host.isConnected)host.querySelector('[data-day-widget-status]').textContent=e.message;}
  finally{if(host.isConnected)host.querySelectorAll('button').forEach(x=>x.disabled=false);}
 });
 }catch(e){if(host.isConnected){host.innerHTML='<p class="ss-error" role="alert"></p><button class="ss-secondary">Повторить подбор</button>';host.querySelector('p').textContent=e.message;host.querySelector('button').onclick=()=>mount(host,options);}}
}
async function resume(){
 if(!context||!context.canLeave())return;const options=context,token=++revision;
 try{const d=await api('?language='+options.language);if(token!==revision)return;
  if(!d.session){session=null;options.back();return;}session=d.session;render();
 }catch(e){alert(e.message);}
}
function render(note=''){
 const opts=context,s=session,root=opts.root();if(!root)return;opts.enter();
 const completed=s.status==='FINISHED',stage=s.plan[s.step],item=s.material;
 root.innerHTML=`<div class="ss-heading"><button class="ss-secondary" data-day-home>← К программе</button><span class="ss-pill">${esc(s.language.toUpperCase())} · план ${s.minutes} мин</span></div><section class="ss-panel"><h2>${completed?'Занятие завершено':s.status==='PAUSED'?'Можно продолжить, когда удобно':esc(stage.title)}</h2><p class="ss-muted">${esc(note||s.note)}</p><progress max="${s.plan.length}" value="${s.step}" aria-label="Этапы занятия"></progress><ol>${s.plan.map((p,i)=>`<li>${i<s.step?'✓ ':''}${esc(p.title)} · около ${p.minutes} мин</li>`).join('')}</ol><div data-day-body></div><div class="ss-actions"><button class="ss-secondary" data-day-lite ${completed?'hidden':''}>Сократить оставшееся до 5 минут</button><button class="ss-secondary" data-day-pause ${completed||s.status==='PAUSED'?'hidden':''}>Сохранить паузу</button><button class="ss-secondary" data-day-refresh ${completed?'hidden':''}>Обновить занятие</button></div><p class="ss-status" data-day-status role="status"></p></section>`;
 root.querySelector('[data-day-home]').onclick=opts.back;root.querySelector('[data-day-lite]').onclick=()=>advance('shorten',undefined,5);
 root.querySelector('[data-day-pause]').onclick=()=>advance('pause');root.querySelector('[data-day-refresh]').onclick=resume;
 const body=root.querySelector('[data-day-body]');
 if(completed){const result=s.evidence.find(x=>x.type==='checked_task');body.innerHTML=`<h3>Что получилось</h3><p>${result?`Проверенные задания: ${result.correct}/${result.total}.`:'Здесь нет нового результата проверки.'}</p><p class="ss-muted">Устное применение — самооценка, не подтверждение уровня. ${result&&result.correct/result.total<.75?'В следующий раз начни с объяснений к ошибкам.':'Следующий шаг подберётся по сохранённой программе.'}</p><button class="ss-primary" data-day-done>Готово на сегодня</button>`;body.querySelector('button').onclick=opts.back;return;}
 if(s.status==='PAUSED'){body.innerHTML='<p>Результаты и место остановки сохранены. Долг за пропущенные дни не добавляется.</p><button class="ss-primary">Продолжить</button>';body.querySelector('button').onclick=()=>advance('resume');return;}
 if(stage.kind==='review'){
  body.innerHTML='<p>Повтори несколько выражений из очереди. Все карточки за один раз проходить не обязательно.</p><div class="ss-actions"><button class="ss-primary" data-day-review>Открыть повторение</button><button class="ss-secondary" data-day-next>Повторил — дальше</button><button class="ss-secondary" data-day-skip>Сегодня без повторения</button></div>';
  body.querySelector('[data-day-review]').onclick=opts.review;body.querySelector('[data-day-next]').onclick=()=>advance('advance');body.querySelector('[data-day-skip]').onclick=()=>advance('skip_review');
 }else if(stage.kind==='input'){
  body.innerHTML=`<h3>${esc(item.title)}</h3><p class="ss-muted">Прочитай, выясни основную мысль и выбери два полезных выражения. Для озвучки и полного цикла можно открыть модуль на следующем шаге.</p><div class="ss-reading" lang="${s.language}" dir="${s.language==='fa'?'rtl':'ltr'}">${esc(item.passage)}</div><div class="ss-phrases">${item.phrases.map(x=>`<div class="ss-phrase"><bdi>${esc(x.front)}</bdi><p>${esc(x.back)}</p></div>`).join('')}</div><div class="ss-actions"><button class="ss-primary" data-day-next>Разобрал материал — к практике</button></div>`;
  body.querySelector('button').onclick=()=>advance('advance');
 }else if(stage.kind==='practice'){
  body.innerHTML='<p>Выполни короткие задания. После проверки вернись кнопкой «Продолжить занятие на сегодня».</p><div class="ss-actions"><button class="ss-primary" data-day-lesson>Открыть задания</button><button class="ss-secondary" data-day-next>Проверка сохранена — дальше</button></div>';
  body.querySelector('[data-day-lesson]').onclick=()=>opts.lesson(s.lesson_id);body.querySelector('[data-day-next]').onclick=()=>advance('advance');
 }else{
  body.innerHTML=`<p>${esc(item.transfer||item.speaking)}</p><p class="ss-muted">Попробуй изменить обстоятельства примера. Затем отметь, как получилось; это самооценка.</p><div class="ss-actions"><button class="ss-secondary" data-day-reflection="with_help">Получилось с опорой</button><button class="ss-primary" data-day-reflection="independent">Сказал самостоятельно</button><button class="ss-secondary" data-day-reflection="difficult">Пока трудно</button></div><div data-day-voice></div>`;
  body.querySelectorAll('[data-day-reflection]').forEach(b=>b.onclick=()=>advance('advance',b.dataset.dayReflection));
  window.AdeliaStudyVoice?.mount(body.querySelector('[data-day-voice]'),{owner_id:opts.owner_id,lesson_id:item.id,language:s.language,prompt:item.transfer||item.speaking});
 }
}
async function advance(action,reflection,minutes){
 if(!session||!context.canLeave())return;const root=context.root(),token=revision;
 root.querySelectorAll('button').forEach(x=>x.disabled=true);context.busy(true);
 try{const d=await api('/update',{session_id:session.id,version:session.version,action,reflection,minutes});if(token!==revision)return;session=d.session;render();}
 catch(e){if(root.isConnected)root.querySelector('[data-day-status]').textContent=e.message;}
 finally{context.busy(false);if(root.isConnected)root.querySelectorAll('button').forEach(x=>x.disabled=false);}
}
async function quick(minutes){
 if(!context||!context.canLeave())return;const opts=context,token=++revision;
 try{const d=await api('/start',{language:opts.language,minutes,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'Europe/Moscow'});if(token!==revision)return;
 if(d.action==='diagnostic'){opts.diagnostic();return;}if(['route_check','route_review'].includes(d.action)){opts.route();return;}
 session=d.session;const shortened=await api('/update',{session_id:session.id,version:session.version,action:'shorten',minutes});if(token!==revision)return;session=shortened.session;render();
 }catch(e){alert(e.message);}}
window.AdeliaStudyDay={mount,resume,quick,hasSession:id=>Boolean(session&&(!id||session.lesson_id===id)&&session.status!=='FINISHED')};
})();
