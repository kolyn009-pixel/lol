'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {Readable,Transform}=require('node:stream'),{pipeline}=require('node:stream/promises');
const {execFile}=require('node:child_process');
function versionParts(v){const m=String(v).match(/^(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$/);return m?[+m[1],+m[2],+m[3],m[4]===undefined?Infinity:+m[4]]:null;}
function newer(a,b){const x=versionParts(a),y=versionParts(b);if(!x||!y)return false;for(let i=0;i<x.length;i++){if(x[i]!==y[i])return x[i]>y[i];}return false;}
function create({app,dialog,shell,net,getWindow,hasLesson,sendState,baseURL,arch}){
 const root=path.join(app.getPath('downloads'),'AdeliaUpdates'),receiptFile=path.join(app.getPath('userData'),'mac-dmg-update.json');
 const alias='Adelia-latest-macos-'+arch+'.dmg';let busy=false,ready=null;
 const show=options=>dialog.showMessageBox(getWindow()||undefined,{noLink:true,...options});
 const tell=message=>sendState({status:ready?'downloaded':'error',message});
 function save(receipt){const tmp=receiptFile+'.tmp';fs.writeFileSync(tmp,JSON.stringify(receipt),{mode:0o600});fs.renameSync(tmp,receiptFile);}
 function validFile(file){try{return path.dirname(path.resolve(file))===root&&!fs.lstatSync(file).isSymbolicLink()&&fs.realpathSync(file)===file;}catch{return false;}}
 async function json(name){const r=await net.fetch(baseURL+name,{cache:'no-store',signal:AbortSignal.timeout(20000)});if(!r.ok||r.redirected)throw Error('Не удалось получить описание обновления.');return r.json();}
 async function download(version,manifest){
  const item=manifest.files?.find(x=>x.name===alias);if(!item||!Number.isSafeInteger(item.size)||item.size<1000000||!/^[a-f0-9]{128}$/i.test(item.sha512))throw Error('Установщик отсутствует или его контрольная сумма некорректна.');
  fs.mkdirSync(root,{recursive:true});if(fs.lstatSync(root).isSymbolicLink())throw Error('Неподходящая папка загрузки.');
  const file=path.join(root,'Adelia-'+version+'-'+arch+'.dmg'),temp=file+'.partial';
  const r=await net.fetch(baseURL+alias,{cache:'no-store',signal:AbortSignal.timeout(30*60*1000)});if(!r.ok||r.redirected||!r.body)throw Error('Не удалось скачать установщик.');
  let size=0;const hash=crypto.createHash('sha512');const meter=new Transform({transform(chunk,encoding,done){size+=chunk.length;if(size>item.size)return done(Error('Размер установщика не совпадает.'));hash.update(chunk);sendState({status:'downloading',version,percent:Math.round(size/item.size*100)});done(null,chunk);}});
  try{await pipeline(Readable.fromWeb(r.body),meter,fs.createWriteStream(temp,{flags:'wx',mode:0o600}));if(size!==item.size||hash.digest('hex')!==item.sha512.toLowerCase())throw Error('Проверка установщика не прошла.');fs.renameSync(temp,file);}catch(e){fs.rmSync(temp,{force:true});throw e;}
  ready={file,version,sha512:item.sha512.toLowerCase()};save(ready);sendState({status:'downloaded',version,percent:100});
  const choice=await show({type:'info',message:'Обновление загружено',detail:'После урока откройте DMG и запустите Аделию внутри него. Текущая версия закроется; новая предложит заменить приложение в «Программах».',buttons:['Открыть DMG и выйти','Позже'],defaultId:1,cancelId:1});if(choice.response===0)await install();
 }
 async function install(){
  if(!ready||!validFile(ready.file))return false;
  if(await hasLesson()){tell('Завершите занятие перед заменой приложения.');return false;}
  const hash=crypto.createHash('sha512');for await(const chunk of fs.createReadStream(ready.file))hash.update(chunk);if(hash.digest('hex')!==ready.sha512){tell('Установщик изменён. Скачайте его повторно.');return false;}
  const error=await shell.openPath(ready.file);if(error){tell('Не удалось открыть DMG: '+error);return false;}
  app.quit();return true;
 }
 async function check(){
  if(busy)return;busy=true;sendState({status:'checking'});
  try{const manifest=await json('manifest.json');if(manifest.schema!==2||!versionParts(manifest.version)||manifest.channel!==(/-beta\./.test(app.getVersion())?'beta':'stable'))throw Error('Некорректное описание обновления.');
   if(!newer(manifest.version,app.getVersion())){sendState({status:'current'});return;}
   sendState({status:'available',version:manifest.version});if(await hasLesson())return;
   const choice=await show({type:'info',message:'Доступна Аделия '+manifest.version,detail:'Скачать проверенный DMG? Он заменит приложение в «Программах». Вход и настройки хранятся отдельно от приложения.',buttons:['Скачать','Позже'],defaultId:0,cancelId:1});if(choice.response===0)await download(manifest.version,manifest);
  }catch(e){tell(e.message||'Не удалось проверить обновления.');}finally{busy=false;}
 }
 async function startup(){
  let receipt;try{receipt=JSON.parse(fs.readFileSync(receiptFile,'utf8'));if(validFile(receipt.file)&&versionParts(receipt.version))ready=receipt;}catch{}
  if(!app.isInApplicationsFolder()&&app.getAppPath().startsWith('/Volumes/')){
   const choice=await show({type:'question',message:'Установить Аделию в «Программы»?',detail:'Прежняя версия будет заменена. Приложение перезапустится, данные кабинета останутся на месте.',buttons:['Заменить и открыть','Позже'],defaultId:0,cancelId:1});if(choice.response!==0)return false;
   const mount=app.getAppPath().match(/^\/Volumes\/[^/]+/)?.[0];if(ready&&mount)save({...ready,mount});
   try{return app.moveToApplicationsFolder({conflictHandler:type=>type==='exists'});}catch(e){await show({type:'error',message:'Не удалось заменить приложение',detail:'Закройте прежнюю Аделию и повторите установку. '+e.message,buttons:['Понятно']});return false;}
  }
  if(app.isInApplicationsFolder()&&ready&&!newer(ready.version,app.getVersion())){
   const choice=await show({type:'question',message:'Убрать установщик DMG в Корзину?',detail:'Новая версия запущена из «Программ». Будет убран только скачанный установщик Аделии.',buttons:['В Корзину','Оставить'],defaultId:1,cancelId:1});
   if(choice.response===0){try{if(receipt.mount&&/^\/Volumes\/[^/]+$/.test(receipt.mount))await new Promise((resolve,reject)=>execFile('/usr/bin/hdiutil',['detach',receipt.mount],e=>e?reject(e):resolve()));if(validFile(ready.file))await shell.trashItem(ready.file);fs.rmSync(receiptFile,{force:true});ready=null;}catch{await show({type:'info',message:'Установщик пока не удалось убрать',detail:'Извлеките образ Аделии в Finder и переместите DMG в Корзину вручную.',buttons:['Понятно']});}}
   else{fs.rmSync(receiptFile,{force:true});ready=null;}
  }else if(ready)sendState({status:'downloaded',version:ready.version});
  return false;
 }
 return {check,install,startup};
}
module.exports={create,newer,versionParts};
