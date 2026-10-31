(()=>{'use strict';if(!document.querySelector('.teacher-shell'))return;
 function shortcuts(){
  if(!document.querySelector('nav [data-view=messages]'))return;
  // Live widgets also use div/span wrappers rather than buttons.
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  const labels=[];let text;
  while((text=walker.nextNode()))if(text.textContent.trim()==='Сообщения')labels.push(text.parentElement);
  labels.forEach(el=>{
   if(!el||el.closest('.teacher-shell>aside,#learningHubOverlay,.teacher-message-shortcut'))return;
   for(let node=el;node&&node!==document.body;node=node.parentElement){
    if(getComputedStyle(node).position!=='fixed')continue;
    // Hide only a standalone shortcut, never a chat panel containing a composer.
    const label=node.textContent.replace(/\s+/g,' ').trim();
    if(!node.querySelector('textarea,input:not([type=button]),[role=dialog]')&&
       /^[^\p{L}]*Сообщения[^\p{L}]*$/u.test(label)){node.classList.add('teacher-message-shortcut');node.hidden=true;node.style.setProperty('display','none','important');}
    break;
   }
  });
 }
let pending=false;function update(){if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;shortcuts();});}new MutationObserver(update).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class','style']});update();})();
