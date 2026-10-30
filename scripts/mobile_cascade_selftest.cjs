// Cascade regression against the actual studio4 desktop selectors served on 2026-10-30.
// This checks stylesheet precedence; it is not a browser layout or iPhone screenshot test.
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const css=require('../qa-deps/node_modules/css-tree'),{parseHTML}=require('../qa-deps/node_modules/linkedom');
const root=path.join(__dirname,'..');
const fixture=fs.readFileSync(path.join(__dirname,'fixtures/mobile_desktop_conflict.css'),'utf8');
const current=fs.readFileSync(path.join(root,'web/release_ui.css'),'utf8');
const legacy=`@media(max-width:900px){
 body.adelia-release-ui .teacher-shell{display:block!important}
 body.adelia-release-ui .teacher-shell>aside{position:fixed!important;height:100dvh!important;max-height:100dvh!important;transform:translateX(-105%)!important;visibility:hidden!important}
 body.adelia-release-ui .clean-menu-toggle{display:inline-grid!important}
}`;
const cmp=(a,b)=>{for(let i=0;i<a.length;i++)if(a[i]!==b[i])return a[i]-b[i];return 0};
function specificity(n){
 if(n.type==='IdSelector')return [1,0,0];
 if(['ClassSelector','AttributeSelector'].includes(n.type))return [0,1,0];
 if(n.type==='TypeSelector')return [0,0,n.name==='*'?0:1];
 if(n.type==='PseudoElementSelector')return [0,0,1];
 if(n.type==='PseudoClassSelector'){
  if(n.name==='where')return [0,0,0];
  if(['is','not','has'].includes(n.name))return specificity(n.children[0]);
  return [0,1,0];
 }
 const children=(n.children||[]).map(specificity);
 if(n.type==='SelectorList')return children.sort(cmp).at(-1)||[0,0,0];
 return children.reduce((a,b)=>a.map((v,i)=>v+b[i]),[0,0,0]);
}
function mediaMatches(raw,width){
 if(/prefers-reduced-motion/.test(raw))return false;
 return raw.split(',').some(group=>{
  let matches=true;for(const m of group.matchAll(/\((min|max)-width:\s*([\d.]+)px\)/g))matches=matches&&(m[1]==='min'?width>=+m[2]:width<=+m[2]);return matches;
 });
}
function cascade(document,width,text){
 const ast=css.toPlainObject(css.parse(text));const rules=[];let order=0;
 function visit(nodes){for(const n of nodes||[]){
  if(n.type==='Atrule'){
   if(n.name==='media'&&!mediaMatches(css.generate(n.prelude),width))continue;
   if(n.name==='keyframes')continue;
   if(n.block)visit(n.block.children);
  }else if(n.type==='Rule'&&n.prelude?.type==='SelectorList'){
   for(const selector of n.prelude.children){
    const sel=css.generate(selector),spec=specificity(selector);
    for(const d of n.block.children)if(d.type==='Declaration')rules.push({sel,spec,property:d.property,value:css.generate(d.value),important:!!d.important,order:order++});
   }
  }
 }}visit(ast.children);
 return (selector,property)=>{
  const element=document.querySelector(selector);let winner=null;
  for(const r of rules){if(r.property!==property)continue;let matches=false;try{matches=element.matches(r.sel)}catch{}if(!matches)continue;
   const rank=[+r.important,...r.spec,r.order];if(!winner||cmp(rank,winner.rank)>0)winner={...r,rank};
  }return winner;
 };
}
let cases=0;
for(const mode of ['studio','desktop'])for(const width of [375,390,430,768,900,901,1440]){
 const {document}=parseHTML(`<html ${mode==='studio'?'data-adelia-design="studio4"':'class="adelia-desktop-teacher"'}><body class="adelia-release-ui"><div class="teacher-shell"><aside></aside><main><header><button class="clean-menu-toggle"></button><div><h1>Сегодня</h1></div><div class="header-actions"></div></header><div id="app"></div></main></div></body></html>`);
 const get=cascade(document,width,fixture+'\n'+current);
 const expected=(selector,property,value)=>assert.equal(get(selector,property)?.value,value,`${mode}/${width}: ${selector} ${property}; winner ${JSON.stringify(get(selector,property))}`);
 if(width<=900){
  expected('.teacher-shell','display','block');expected('.teacher-shell>aside','position','fixed');
  expected('.teacher-shell>aside','height','100dvh');expected('.teacher-shell>aside','max-height','100dvh');
  expected('.teacher-shell>aside','visibility','hidden');expected('.teacher-shell>aside','transform','translateX(-105%)');
  expected('.clean-menu-toggle','display','inline-grid');expected('main>header','display','grid');expected('main>header','min-height','0');
  expected('#app','margin','0');document.body.classList.add('menu-open');
  expected('.teacher-shell>aside','transform','translateX(0)');expected('.teacher-shell>aside','visibility','visible');
 }else{expected('.teacher-shell','display','grid');expected('.clean-menu-toggle','display','none')}
 cases++;
}
// Guard the reason for this test: old mobile selectors lost to the actual desktop theme.
const {document}=parseHTML('<html data-adelia-design="studio4"><body class="adelia-release-ui"><div class="teacher-shell"><aside></aside></div><button class="clean-menu-toggle"></button></body></html>');
const old=getOld();function getOld(){return cascade(document,390,fixture+'\n'+legacy)}
assert.equal(old('.teacher-shell>aside','position').value,'static');assert.equal(old('.teacher-shell>aside','max-height').value,'220px');assert.equal(old('.teacher-shell>aside','visibility').value,'hidden');assert.equal(old('.clean-menu-toggle','display').value,'none');
console.log(`Mobile CSS cascade: ${cases} widths/theme cases passed; production conflict reproduced.`);
