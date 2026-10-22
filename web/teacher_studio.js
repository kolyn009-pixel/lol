(()=>{'use strict';
if(window.__adeliaStudio4||!document.querySelector('.teacher-shell'))return;window.__adeliaStudio4=true;
document.documentElement.dataset.adeliaDesign='studio4';
// Earlier desktop builds injected tiny inline text styles; remove only that presentation layer.
const shrinkTargets='.v4-page-head,.finance-head,.v4-page-head h2,.finance-head h2,.finance-head p,.finance-head small,.finance-head span,.finance-overview-toolbar,.finance-tabs button,.payments-tabs button,.health-card,.tb-card,.tb-card h3,.tb-card p,.tb-form input,.tb-actions button,.msg-shell';
let queued=false;
function clean(){queued=false;document.querySelectorAll(shrinkTargets).forEach(e=>{for(const prop of ['font-size','padding','min-height','height','color','background','border-color','line-height','margin']){if(!e.style.getPropertyValue(prop))continue;e.style.removeProperty(prop)}})}
const observer=new MutationObserver(()=>{if(!queued){queued=true;requestAnimationFrame(clean)}});observer.observe(document.querySelector('#app'),{childList:true,subtree:true,attributes:true,attributeFilter:['style']});clean();
})();
