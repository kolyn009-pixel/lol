'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
const start=source.indexOf('const OFFLINE_PATHS='),end=source.indexOf('function fmtDate(',start);
assert(start>=0&&end>start);
const store=new Map();
const sessionStorage={
  getItem:key=>store.get(key)||null,
  setItem:(key,value)=>store.set(key,value),
  removeItem:key=>store.delete(key),
};
let online=true;
const sandbox={
  sessionStorage,AbortController,Date,JSON,Set,String,Object,TypeError,Error,
  setTimeout:()=>1,clearTimeout:()=>{},
  fetch:async()=>{
    if(!online)throw new TypeError('offline');
    return {ok:true,json:async()=>({items:[{id:7,title:'Задачи'}]})};
  },
};
vm.createContext(sandbox);
vm.runInContext('let auth={role:"student",id:5};'+source.slice(start,end)+';globalThis.apiTest=api;globalThis.switchUser=id=>{auth={role:"student",id}}',sandbox);
(async()=>{
  await sandbox.apiTest('/student/homework');
  online=false;
  const cached=await sandbox.apiTest('/student/homework');
  assert.equal(cached.items[0].title,'Задачи');
  assert(cached._offline_at>0);
  sandbox.switchUser(6);
  await assert.rejects(sandbox.apiTest('/student/homework'),/offline/);
  console.log('STUDENT_OFFLINE=PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
