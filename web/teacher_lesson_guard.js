(()=>{
  const busy=new Set();
  function lock(btn,label){if(!btn||busy.has(btn))return false;busy.add(btn);btn.disabled=true;btn.dataset.oldText=btn.textContent;btn.textContent=label||'Подождите…';return true}
  function unlock(btn){if(!btn)return;busy.delete(btn);btn.disabled=false;if(btn.dataset.oldText){btn.textContent=btn.dataset.oldText;delete btn.dataset.oldText}}
  document.addEventListener('click',e=>{
    const btn=e.target.closest('#startLesson,#finishNow,#finishPlan,#openLessonEntry,#finishPostFlow,#completePostReview,#postSkipHw');
    if(!btn)return;
    if(busy.has(btn)){e.preventDefault();e.stopImmediatePropagation();return}
    const label=btn.id==='startLesson'?'Запускаю…':btn.id==='openLessonEntry'?'Открываю вход…':btn.id==='finishPostFlow'?'Закрываю…':'Сохраняю…';
    lock(btn,label);
    setTimeout(()=>{if(document.body.contains(btn))unlock(btn)},12000);
  },true);
  window.AdeliaLessonGuard={lock,unlock};
})();
