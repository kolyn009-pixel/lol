/* Device-local recordings. No audio is uploaded by this component. */
(()=>{'use strict';
if(window.AdeliaStudyVoice)return;
let dispose=null,hasUnsaved=()=>false;const pendingWrites=new Set();
const locales={en:'en-GB',de:'de-DE',fa:'fa-IR',es:'es-ES'};
function database(){return new Promise((resolve,reject)=>{
 const request=indexedDB.open('adelia-personal-voice',1);
 request.onupgradeneeded=()=>request.result.createObjectStore('answers');
 request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
});}
async function storage(key,value,write=false){
 const db=await database();
 try{return await new Promise((resolve,reject)=>{
  const tx=db.transaction('answers',write?'readwrite':'readonly'),store=tx.objectStore('answers');
  const req=write?store.put(value,key):store.get(key);let result;
  req.onsuccess=()=>{result=req.result;};
  tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
 });}finally{db.close();}
}
function mount(node,context){
 dispose?.();if(!node)return;
 const key=String(context.owner_id)+':'+context.lesson_id;
 let stream=null,recorder=null,recognizer=null,timer=null,url=null,pending=false,closed=false;
 let noteDirty=false,recordingDirty=false;
 hasUnsaved=()=>!closed&&(noteDirty||recordingDirty||pending||Boolean(recognizer)||Boolean(recorder));
 let saved={blob:null,transcript:'',updated_at:null};
 node.innerHTML='<section class="ss-panel"><h3>Скажи вслух</h3><p class="ss-muted" data-voice-prompt></p><p class="ss-muted">Запиши ответ на 30–90 секунд. Прослушай: ответил ли на вопрос, связал ли мысли и где пришлось искать слова? Максимум записи — 3 минуты.</p><div class="ss-actions"><button type="button" class="ss-primary" data-voice-record>Записать ответ</button><button type="button" class="ss-secondary" data-voice-stop disabled>Остановить</button></div><div data-voice-playback></div><p class="ss-status" data-voice-status role="status"></p><details><summary>Расшифровка и заметка</summary><p class="ss-muted">Можно продиктовать короткий ответ или оставить несколько слов о трудности. Проверь распознанный текст. Браузерное распознавание может отправлять звук своему сервису и не всегда доступно.</p><div class="ss-actions"><button type="button" class="ss-secondary" data-voice-dictate>Продиктовать текст</button><button type="button" class="ss-secondary" data-voice-dictate-stop disabled>Остановить диктовку</button></div><label>Расшифровка или заметка<textarea data-voice-text rows="4" maxlength="3000" style="width:100%;padding:12px;border:1px solid #d8d1e6;border-radius:10px;margin-top:8px"></textarea></label><button type="button" class="ss-secondary" data-voice-save>Сохранить заметку</button><p class="ss-muted">По кнопке ниже расшифровка отправляется настроенному ИИ для разбора языка. Аудио не отправляется.</p><button type="button" class="ss-primary" data-voice-feedback>Разобрать расшифровку с ИИ</button><div data-voice-feedback-result></div></details><p class="ss-note">Запись и заметка хранятся только в этом браузере под твоим аккаунтом. Между устройствами не синхронизируются; очистка данных браузера удалит их. Скачай важный ответ. Разбор текста не оценивает произношение или уровень CEFR.</p></section>';
 const el=s=>node.querySelector(s),record=el('[data-voice-record]'),stop=el('[data-voice-stop]'),text=el('textarea'),dictate=el('[data-voice-dictate]'),dictateStop=el('[data-voice-dictate-stop]');
 text.oninput=()=>{noteDirty=true;};
 el('[data-voice-prompt]').textContent=context.prompt;text.lang=context.language;text.dir=context.language==='fa'?'rtl':'auto';
 const status=s=>{if(!closed)el('[data-voice-status]').textContent=s;};
 function playback(){
  if(closed)return;const box=el('[data-voice-playback]');box.replaceChildren();
  if(url){URL.revokeObjectURL(url);url=null;}
  if(!saved.blob)return;
  url=URL.createObjectURL(saved.blob);const audio=document.createElement('audio');audio.controls=true;audio.src=url;audio.style.width='100%';audio.style.marginTop='16px';
  const a=document.createElement('a');a.href=url;a.download=context.lesson_id+'-answer.'+(saved.blob.type.includes('mp4')?'m4a':'webm');a.textContent='Скачать запись';a.className='ss-secondary';box.append(audio,a);
 }
 async function save(){saved.updated_at=new Date().toISOString();const p=storage(key,saved,true);pendingWrites.add(p);try{await p;}finally{pendingWrites.delete(p);}}
 function release(){stream?.getTracks().forEach(t=>t.stop());stream=null;clearTimeout(timer);timer=null;}
 function halt(){if(recorder&&recorder.state!=='inactive')recorder.stop();else release();}
 record.onclick=async()=>{
  if(pending||closed)return;pending=true;record.disabled=true;dictate.disabled=true;
  try{
   if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw Error('unsupported');
   if(saved.blob&&!confirm('Заменить предыдущую запись этого урока? Сначала скачай её, если она нужна.'))return;
   status('Ожидаю доступ к микрофону…');stream=await navigator.mediaDevices.getUserMedia({audio:true});
   if(closed){release();return;}
   const chunks=[];recorder=new MediaRecorder(stream);
   recorder.ondataavailable=event=>{if(event.data.size)chunks.push(event.data);};
   recorder.onerror=()=>{status('Не удалось записать звук. Проверь микрофон.');halt();};
   recorder.onstop=async()=>{
    release();if(closed){recorder=null;return;}const blob=new Blob(chunks,{type:recorder.mimeType||'audio/webm'});recorder=null;
    if(!closed){record.disabled=true;dictate.disabled=true;stop.disabled=true;}
    if(!blob.size){if(!closed){record.disabled=false;dictate.disabled=!Recognition;}status('Запись оказалась пустой. Попробуй снова.');return;}
    saved.blob=blob;recordingDirty=true;
    try{await save();recordingDirty=false;status('Запись сохранена на этом устройстве. Прослушай ответ.');}
    catch{status('Не удалось сохранить запись в браузере. Скачай её сейчас.');}
    if(!closed){record.disabled=false;dictate.disabled=!Recognition;}
    playback();
   };
   recorder.start();stop.disabled=false;status('Идёт запись. Можно говорить с подсказками.');timer=setTimeout(halt,180000);
  }catch(error){release();status(error.name==='NotAllowedError'?'Доступ к микрофону запрещён. Разреши его в настройках браузера или выполни задание вслух самостоятельно.':error.message==='unsupported'?'Запись в этом браузере недоступна. Выполни задание вслух самостоятельно.':'Микрофон недоступен. Проверь подключение и повтори.');}
  finally{pending=false;if(!closed&&!recorder){record.disabled=false;dictate.disabled=!Recognition;}}
 };
 stop.onclick=halt;
 const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(!Recognition){dictate.disabled=true;dictate.title='Этот браузер не поддерживает распознавание. Заметку можно ввести вручную.';}
 dictate.onclick=()=>{
  if(recorder||recognizer||closed)return;
  try{
   recognizer=new Recognition();recognizer.lang=locales[context.language];recognizer.continuous=true;recognizer.interimResults=false;
   recognizer.onresult=event=>{if(closed)return;noteDirty=true;for(let i=event.resultIndex;i<event.results.length;i++)if(event.results[i].isFinal)text.value=(text.value+' '+event.results[i][0].transcript).trim().slice(0,3000);};
   recognizer.onerror=()=>status('Распознавание недоступно или не разобрало речь. Проверь язык; можно оставить короткую заметку вручную.');
   recognizer.onend=()=>{recognizer=null;clearTimeout(timer);timer=null;if(!closed){dictate.disabled=false;dictateStop.disabled=true;record.disabled=false;}};
   recognizer.start();dictate.disabled=true;dictateStop.disabled=false;record.disabled=true;status('Диктовка запущена. После остановки проверь и сохрани текст.');timer=setTimeout(()=>recognizer?.stop(),180000);
  }catch{recognizer=null;status('Не удалось запустить диктовку. Попробуй ещё раз или введи заметку.');}
 };
 dictateStop.onclick=()=>recognizer?.stop();
 el('[data-voice-save]').onclick=async()=>{saved.transcript=text.value;try{await save();noteDirty=false;status('Заметка сохранена на этом устройстве.');}catch{status('Не удалось сохранить заметку. Скопируй её перед выходом.');}};
 el('[data-voice-feedback]').onclick=async()=>{
  const button=el('[data-voice-feedback]'),transcript=text.value.trim();
  if(transcript.length<5){status('Сначала продиктуй ответ и проверь расшифровку.');return;}
  button.disabled=true;const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),30000);
  status('Разбираю расшифровку…');
  try{
   const response=await fetch(('/api/'+(['student','parent'].includes(document.body.dataset.studyRole)?document.body.dataset.studyRole:'teacher')+'/self-study')+'/speech/feedback',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({lesson_id:context.lesson_id,transcript,consent:true}),signal:controller.signal});
   const result=await response.json();
   if(!response.ok){const messages={ai_not_configured:'ИИ ещё не настроен на сервере. Запись и самостоятельная практика доступны.',feedback_rate_limited:'Слишком много запросов. Подожди минуту.',ai_invalid_response:'ИИ вернул неполный разбор. Попробуй позже.'};throw Error(messages[result.error]||'ИИ сейчас недоступен. Ответ и запись остаются у тебя.');}
   if(closed)return;
   const box=el('[data-voice-feedback-result]');box.replaceChildren();
   for(const [key,title] of [['strengths','Что получилось'],['corrections','Что поправить'],['next_try','Повторная попытка']]){
    const heading=document.createElement('h4');heading.textContent=title;box.append(heading);
    for(const value of result[key]){const p=document.createElement('p');p.textContent=value;box.append(p);}
   }
   const note=document.createElement('p');note.className='ss-muted';note.textContent=result.note;box.append(note);status('Разбор готов. Попробуй ответить ещё раз своими словами.');
  }catch(error){status(error.name==='AbortError'?'Время ожидания вышло. Можно попробовать позже.':error.message);}
  finally{clearTimeout(deadline);if(!closed)button.disabled=false;}
 };
 record.disabled=true;dictate.disabled=true;text.disabled=true;
 storage(key).then(value=>{if(closed||!value)return;saved=value;text.value=saved.transcript||'';playback();}).catch(()=>status('Хранилище браузера недоступно. Запись можно будет скачать.')).finally(()=>{if(!closed){record.disabled=false;dictate.disabled=!Recognition;text.disabled=false;}});
 const observer=new MutationObserver(()=>{if(!node.isConnected)cleanup();});observer.observe(document.body,{childList:true,subtree:true});
 function cleanup(){if(closed)return;closed=true;observer.disconnect();recognizer?.abort();halt();release();if(url)URL.revokeObjectURL(url);}
 dispose=cleanup;
}
async function clearOwn(owner){
 if(!Number.isSafeInteger(owner))throw Error('invalid_owner');dispose?.();await Promise.allSettled([...pendingWrites]);const db=await database();let count=0;
 try{await new Promise((resolve,reject)=>{const tx=db.transaction('answers','readwrite'),req=tx.objectStore('answers').openCursor();req.onsuccess=()=>{const c=req.result;if(!c)return;if(String(c.key).startsWith(String(owner)+':')){c.delete();count++;}c.continue();};tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});}finally{db.close();}return count;
}
window.AdeliaStudyVoice={mount,clearOwn,hasUnsaved:()=>hasUnsaved(),stop:()=>dispose?.()};
})();
