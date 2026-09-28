'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const pkg=JSON.parse(fs.readFileSync(path.join(root,'desktop/package.json'),'utf8'));
const main=fs.readFileSync(path.join(root,'desktop/main.js'),'utf8');
const about=fs.readFileSync(path.join(root,'desktop/about.js'),'utf8');
if(pkg.build.mac.identity===null){
  assert(main.includes("if (!AUTO_UPDATE_SUPPORTED) { sendUpdateState({status:'manual'"),'unsigned mac updater must be disabled');
  assert(main.includes("if(!AUTO_UPDATE_SUPPORTED)return sendUpdateState({status:'manual'"),'manual check must report the same state');
  assert(about.includes("manual:['Обновление вручную'"),'about page must explain manual updates');
}
console.log('DESKTOP_UPDATE_CAPABILITY=PASS');
