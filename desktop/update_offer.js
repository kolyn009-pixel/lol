'use strict';
// Unsigned Mac builds can announce updates, but Squirrel.Mac cannot install them.
async function offerUpdate({platform,arch,version,dialog,parent,openExternal,downloadUpdate}){
 const manual=platform==='darwin';
 const result=await dialog.showMessageBox(parent,{type:'info',title:'Доступно обновление Аделии',message:`Доступна новая версия ${version}.`,detail:manual?'Скачать новую версию для Mac? Откройте DMG и замените Аделию в «Программах».':'Скачать обновление сейчас? Можно продолжать пользоваться приложением во время загрузки.',buttons:[manual?'Скачать для Mac':'Скачать','Позже'],defaultId:0,cancelId:1,noLink:true});
 if(result.response!==0)return;
 if(manual){if(!['arm64','x64'].includes(arch))throw new Error('Unsupported Mac architecture');await openExternal(`https://adeliatutor.ru/desktop-updates/Adelia-latest-macos-${arch}.dmg`);return;}
 await downloadUpdate();
}
module.exports={offerUpdate};
