(()=>{
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  async function api(path){const r=await fetch('/api'+path,{credentials:'same-origin'});const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'Ошибка');return j}
  async function until(selector,tries=40){for(let i=0;i<tries;i++){const el=document.querySelector(selector);if(el)return el;await wait(50)}return null}
  function topicNames(state){
    if(state?.review_summary?.topics?.length)return state.review_summary.topics.filter(Boolean);
    const draft=state?.draft||{},rows=state?.topics||[];
    return rows.filter(t=>draft[t.id]||draft[String(t.id)]).map(t=>t.topic||t.name||t.title).filter(Boolean);
  }
  async function applyLessonContext(lessonId){
    try{
      const state=await api('/teacher/post-lesson?id='+encodeURIComponent(lessonId));
      const names=topicNames(state);const title=await until('#hmTitle');if(!title)return;
      if(!title.value&&names.length)title.value=names.length===1?`Закрепить: ${names[0]}`:`Закрепление тем занятия`;
      const desc=document.querySelector('#hmDescription');if(desc&&!desc.value&&names.length)desc.value=`Повторить и закрепить: ${names.join(', ')}.`;
      const search=document.querySelector('#hmSearch');if(search&&names.length){search.value=names[0];search.dispatchEvent(new Event('input',{bubbles:true}))}
      const head=document.querySelector('.hw-authoring-head');if(head&&!head.querySelector('.post-lesson-context')){
        const note=document.createElement('div');note.className='post-lesson-context';note.innerHTML=`<b>Связано с завершённым занятием</b><span>${names.length?'Темы: '+names.join(' · '):'Ученик и урок уже выбраны автоматически'}</span>`;head.appendChild(note)
      }
      const student=document.querySelector('#hmStudent');if(student)student.disabled=true;
    }catch(e){console.warn('[adelia] homework lesson context unavailable',e)}
  }
  function wrap(){if(typeof window.newHomework!=='function'||window.newHomework.__adeliaWrapped)return;const original=window.newHomework;const wrapped=async function(selected,lessonId){const result=await original(selected,lessonId);if(lessonId)await applyLessonContext(lessonId);return result};wrapped.__adeliaWrapped=true;window.newHomework=wrapped}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(wrap,0));else setTimeout(wrap,0);
})();
