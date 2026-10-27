(()=>{'use strict';
if(window.AdeliaStudyOnboarding)return;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={en:'Английский',de:'Немецкий',es:'Испанский',fa:'Фарси'};
async function api(path,body){const role=['student','parent'].includes(document.body.dataset.studyRole)?document.body.dataset.studyRole:'teacher';const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);try{const r=await fetch('/api/'+role+'/self-study/placement'+path,{credentials:'same-origin',cache:'no-store',signal:controller.signal,...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const d=await r.json();if(!r.ok)throw Error('Не удалось сохранить проверку. Ответы сохранены в этой вкладке; попробуй ещё раз.');return d;}catch(e){if(e.name==='AbortError')throw Error('Ответ задержался. Повтори сохранение.');throw e;}finally{clearTimeout(timer);}}
function home(root,options,data){
 root.innerHTML=`<section class="ss-panel"><span class="ss-eyebrow">Программа под твой старт</span><h2>${data.pending.length?'Сначала выберем точку старта':'Результаты и ближайшие цели'}</h2><p class="ss-muted">Выбери только те языки, которые хочешь изучать сейчас. Затем пройди проверку каждого: она поможет подобрать маршрут. «Не знаю» — нормальный ответ, в том числе для языка с нуля.</p><div class="ss-actions"><button class="ss-secondary" data-onboarding-settings>Выбрать языки, интересы и время</button>${!data.pending.length?'<button class="ss-primary" data-onboarding-done>Перейти к занятиям</button>':''}</div>${data.pending.map(c=>`<article class="ss-reference"><h3>${names[c]}</h3><p>Короткая проверка чтения и грамматики. Без словаря. Можно сделать паузу в этой вкладке.</p><button class="ss-primary" data-placement-required data-placement-start="${c}">Проверить старт · ${names[c]}</button></article>`).join('')}${Object.entries(data.results).map(([c,r])=>`<article class="ss-reference"><h3>${names[c]} · рабочий ориентир ${esc(r.working_band)}</h3><p>${esc(r.note)}</p><p><b>Предлагаем на четыре недели:</b> ${esc(r.recommendation.goal)}.</p><p class="ss-muted">${r.recommendation.review_due?'Пора пересмотреть ближайшую цель. ':''}${r.recommendation.daily_minutes} мин на язык в день · пересмотр ${esc(r.recommendation.review_date)}. ${esc(r.recommendation.note)} ${esc(r.recommendation.course_choice)}</p>${r.recommendation.advanced_check_needed?'<p class="ss-note">Для маршрута C1 нужна дополнительная проверка сложных материалов, речи, аудирования и письма.</p>':''}<div class="ss-actions"><button class="ss-secondary" data-placement-goal="${c}">Подставить предложенную цель в настройки</button><button class="ss-secondary" data-placement-start="${c}">Пройти ещё раз</button></div></article>`).join('')}<p class="ss-note">Прохождение короткого теста не подтверждает весь уровень CEFR. Карточки и повторы знакомых заданий тоже не заменяют независимую проверку.</p></section>`;
 root.querySelector('[data-onboarding-settings]').onclick=()=>options.settings();root.querySelector('[data-onboarding-done]')?.addEventListener('click',options.back);
 root.querySelectorAll('[data-placement-start]').forEach(b=>b.onclick=()=>test(root,options,b.dataset.placementStart));
 root.querySelectorAll('[data-placement-goal]').forEach(b=>b.onclick=()=>{const c=b.dataset.placementGoal;options.settings({[c]:data.results[c].recommendation.goal});});
}
async function test(root,options,language){
 root.innerHTML='<p role="status">Загружаю проверку…</p>';
 try{const d=await api('?language='+language);if(!root.isConnected)return;
 const key='adelia-placement:'+options.owner_id+':'+language;let saved={};try{saved=JSON.parse(sessionStorage.getItem(key)||'{}');}catch(_){}
 const answers={};for(const q of d.questions)if(q.options.concat('unknown').includes(saved[q.id]))answers[q.id]=saved[q.id];
 let index=d.questions.findIndex(q=>!(q.id in answers));if(index<0)index=0;
 function render(){
  const q=d.questions[index];root.innerHTML=`<button class="ss-secondary" data-placement-back>← К выбору языков</button><section class="ss-panel"><span class="ss-eyebrow">${names[language]} · ${index+1} из ${d.questions.length}</span><h2>Стартовая проверка</h2><p class="ss-muted">${esc(d.note)}</p><progress value="${Object.keys(answers).length}" max="${d.questions.length}" aria-label="Отвечено вопросов"></progress>${q.passage?`<p class="ss-reading" lang="${language}" dir="${language==='fa'?'rtl':'ltr'}">${esc(q.passage)}</p>`:''}<form data-placement-form><fieldset><legend lang="${language}" dir="auto">${esc(q.prompt)}</legend>${q.options.concat('unknown').map(v=>`<label class="ss-choice"><input type="radio" name="answer" value="${esc(v)}" ${answers[q.id]===v?'checked':''} required><span dir="auto">${v==='unknown'?'Не знаю':esc(v)}</span></label>`).join('')}</fieldset><div class="ss-actions"><button class="ss-secondary" type="button" data-placement-prev ${index===0?'disabled':''}>Назад</button><button class="ss-primary" type="submit">${index===d.questions.length-1?'Получить маршрут и цели':'Дальше'}</button></div><p data-placement-status role="status"></p></form><p class="ss-muted">Ответы на время теста хранятся в этой вкладке. Можно вернуться позже в ней же. Повторная проверка после разбора показывает тренировку, а не независимый рост.</p></section>`;
  root.querySelector('[data-placement-back]').onclick=options.back;root.querySelector('[data-placement-prev]').onclick=()=>{index--;render();};
  const form=root.querySelector('form');form.onchange=()=>{answers[q.id]=new FormData(form).get('answer');try{sessionStorage.setItem(key,JSON.stringify(answers));}catch(_){} };
  form.onsubmit=async event=>{event.preventDefault();answers[q.id]=new FormData(form).get('answer');if(index<d.questions.length-1){index++;render();return;}
   if(Object.keys(answers).length!==d.questions.length){index=d.questions.findIndex(x=>!(x.id in answers));render();return;}
   options.busy(true);form.querySelectorAll('button,input').forEach(x=>x.disabled=true);
   try{await api('/submit',{language,answers});try{sessionStorage.removeItem(key);}catch(_){}options.busy(false);if(options.completed)await options.completed();else options.back();}
   catch(e){if(form.isConnected)form.querySelector('[data-placement-status]').textContent=e.message;}
   finally{options.busy(false);if(form.isConnected)form.querySelectorAll('button,input').forEach(x=>x.disabled=false);}
  };
 }
 render();
 }catch(e){if(root.isConnected){root.innerHTML='<p class="ss-error" role="alert"></p><button class="ss-secondary">Вернуться</button>';root.querySelector('p').textContent=e.message;root.querySelector('button').onclick=options.back;}}
}
window.AdeliaStudyOnboarding={home,test};
})();
