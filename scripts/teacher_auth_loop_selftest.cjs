const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../web/teacher_dashboard_week.js'),'utf8');
const old="if(e.message==='AUTH'){if(typeof window.show==='function')return window.show('dashboard');location.reload();return}";
const fixed="if(e.message==='AUTH'){lastSignature='';if(typeof window.login==='function'){window.login();return}title.textContent='Вход';app.innerHTML='<section class=\"error\"><b>Для продолжения войдите в кабинет преподавателя.</b><p>Форма входа ещё загружается. Обновите страницу.</p></section>';return}";
function fixture(code,status=401,hasLogin=true){
  const state={requests:0,login:0,redirects:0,reloads:0};
  const title={textContent:'Сегодня'},app={innerHTML:'loading',querySelector:()=>null,querySelectorAll:()=>[]};
  const doc={querySelector:s=>s==='#app'?app:s==='#title'?title:{onclick:null},querySelectorAll:()=>[]};
  const win={addEventListener(){},show(){state.redirects++;return win.AdeliaTeacherDashboardV2();}};
  if(hasLogin)win.login=()=>{state.login++;title.textContent='Вход';app.innerHTML='<form>LOGIN</form>';};
  const payload={stats:{},week:{today:'2026-11-11',start:'2026-11-09',timezone:'Europe/Moscow'},today_lessons:[],week_lessons:[],pending_reviews:[],next_lessons:[]};
  const context={window:win,document:doc,MutationObserver:class{observe(){}},AbortController,
    setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,
    location:{reload(){state.reloads++;}},fetch:async()=>{state.requests++;if(status==='network')throw Error('NETWORK_TIMEOUT');return{status,ok:status===200,json:async()=>payload};}};
  vm.runInNewContext(code,context);
  return {state,title,app,render:()=>win.AdeliaTeacherDashboardV2()};
}
module.exports=(async()=>{
  assert(source.includes(fixed));
  const broken=fixture(source.replace(fixed,old));await broken.render();
  assert.equal(broken.state.redirects,1);assert.equal(broken.state.login,0);
  const loggedOut=fixture(source);await loggedOut.render();
  assert.equal(loggedOut.state.login,1);assert.equal(loggedOut.state.redirects,0);assert.equal(loggedOut.state.reloads,0);assert.equal(loggedOut.title.textContent,'Вход');
  const lateLogin=fixture(source,401,false);await lateLogin.render();
  assert.equal(lateLogin.title.textContent,'Вход');assert.equal(lateLogin.state.redirects,0);assert.equal(lateLogin.state.reloads,0);
  const loggedIn=fixture(source,200);await loggedIn.render();
  assert.match(loggedIn.app.innerHTML,/teacher-dashboard-v2/);assert.equal(loggedIn.state.login,0);
  const network=fixture(source,'network');await network.render();
  assert.match(network.app.innerHTML,/Сервер отвечает слишком долго/);assert.equal(network.state.login,0);
  return 'TEACHER_AUTH_LOOP_TESTS_OK: regression reproduced; login, late initialization, authenticated dashboard and network failure checked';
})();
if(require.main===module)module.exports.then(console.log).catch(e=>{console.error(e);process.exitCode=1;});
