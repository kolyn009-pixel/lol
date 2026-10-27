/* Original task cycle and device-local reflection. No Cambridge exam scores. */
(()=>{'use strict';
if(window.AdeliaStudyIntensive)return;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let cleanup=null;
function mount(root,context){
 cleanup?.();const item=context.lesson;if(!item.cycle)return;
 const key='adelia-intensive:'+context.owner_id+':'+item.id;
 let saved={writing:'',reflection:[]};
 try{saved=JSON.parse(localStorage.getItem(key)||'null')||saved;}catch{}
 const node=document.createElement('section');node.className='ss-panel';node.style.marginTop='18px';root.append(node);
 node.innerHTML=`<span class="ss-eyebrow">Интенсивный блок · ориентир задания ${esc(item.band)}</span><h3>Цель и цикл практики</h3><p>${esc(item.objective)}</p><p class="ss-muted">${esc(item.block_note)}</p><ol>${item.cycle.map(x=>`<li><b>${esc(x.stage)} · ${x.minutes} минут</b><p>${esc(x.task)}</p></li>`).join('')}</ol><div class="ss-actions"><button type="button" class="ss-secondary" data-intensive-listen>Слушать учебную озвучку, скрыв текст</button><button type="button" class="ss-secondary" data-intensive-stop>Остановить озвучку</button></div><p class="ss-muted">Озвучка синтетическая, зависит от голосов устройства. Она не оценивает твой слух или произношение. Дополняй её живой речью из выбранных ресурсов.</p><h4>Короткое письмо с опорой</h4><p>${esc(item.writing)}</p>${(item.writing_frames||[]).map(x=>`<p lang="${item.language}" dir="${item.language==='fa'?'rtl':'ltr'}">${esc(x)}</p>`).join('')}<label>Черновик · можно начать с двух предложений<textarea rows="4" maxlength="1500" data-intensive-writing style="width:100%;padding:12px;border:1px solid #d8d1e6;border-radius:10px"></textarea></label><h4>Перенос на новую ситуацию</h4><p>${esc(item.transfer)}</p><h4>Самопроверка</h4>${item.can_do.map((x,i)=>`<label class="ss-choice"><input type="checkbox" data-intensive-reflection="${i}" ${saved.reflection?.includes(i)?'checked':''}><span>${esc(x)}</span></label>`).join('')}<p class="ss-muted">Это твоя рефлексия, не проверенный балл и не подтверждение уровня. Черновик и отметки сохраняются только в этом браузере, отдельно от проверок урока.</p><p data-intensive-status class="ss-status" role="status"></p>`;
 const writing=node.querySelector('textarea'),status=node.querySelector('[data-intensive-status]');writing.value=saved.writing||'';writing.lang=item.language;writing.dir=item.language==='fa'?'rtl':'auto';
 const persist=()=>{const data={writing:writing.value,reflection:[...node.querySelectorAll('[data-intensive-reflection]:checked')].map(x=>Number(x.dataset.intensiveReflection))};try{localStorage.setItem(key,JSON.stringify(data));status.textContent='Черновик и самопроверка сохранены на этом устройстве.';}catch{status.textContent='Не удалось сохранить в браузере. Скопируй черновик перед выходом.';}};
 writing.oninput=persist;node.querySelectorAll('[data-intensive-reflection]').forEach(x=>x.onchange=persist);
 let utterance=null;
 const stop=()=>{if(utterance){window.speechSynthesis?.cancel();utterance=null;}};
 node.querySelector('[data-intensive-stop]').onclick=stop;
 node.querySelector('[data-intensive-listen]').onclick=()=>{
  if(!window.speechSynthesis||!window.SpeechSynthesisUtterance){status.textContent='Озвучка недоступна. Используй аудио или видео из выбранного ресурса.';return;}
  const voice=speechSynthesis.getVoices().find(v=>v.lang.toLowerCase().split('-')[0]===item.language);
  if(!voice){status.textContent='На устройстве нет готового голоса этого языка. Подключи его в системе или используй озвученный ресурс.';return;}
  stop();const material=root.querySelector('[data-ss-material]');if(material)material.open=false;
  utterance=new SpeechSynthesisUtterance(item.passage);utterance.voice=voice;utterance.lang=voice.lang;utterance.rate=.9;
  utterance.onerror=()=>{status.textContent='Озвучка не завершилась. Можно вернуться к тексту или другому ресурсу.';};
  speechSynthesis.speak(utterance);status.textContent='Слушай основную мысль, затем проверь детали по тексту.';
 };
 const observer=new MutationObserver(()=>{if(!node.isConnected){stop();observer.disconnect();}});observer.observe(document.body,{childList:true,subtree:true});
 cleanup=()=>{stop();observer.disconnect();};
}
window.AdeliaStudyIntensive={mount};
})();
