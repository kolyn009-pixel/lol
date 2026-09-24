'use strict';
const fs=require('fs'),path=require('path');
const brand=path.join(__dirname,'..','brand','adelia_icon'),build=path.join(__dirname,'build');
const files=[
 ['adelia-icon-512.png','icon.png'],
 ['adelia-icon-macos.icns','icon.icns'],
 ['adelia-icon-windows.ico','icon.ico'],
 ['adelia-icon-macos-1024.png','icon-macos.png']
];
const PNG=Buffer.from([137,80,78,71,13,10,26,10]);
function validPng(b,w,h){return b.length>64&&b.subarray(0,8).equals(PNG)&&b.readUInt32BE(16)===w&&b.readUInt32BE(20)===h}
try{
 fs.mkdirSync(build,{recursive:true});
 for(const [srcName,dstName] of files){
   const src=path.join(brand,srcName),dst=path.join(build,dstName),tmp=dst+'.tmp';
   const b=fs.readFileSync(src);
   if(srcName==='adelia-icon-512.png'&&!validPng(b,512,512))throw new Error('Canonical web icon must be 512x512 PNG');
   if(srcName==='adelia-icon-macos-1024.png'&&!validPng(b,1024,1024))throw new Error('macOS preview icon must be 1024x1024 PNG');
   if(srcName.endsWith('.icns')&&b.toString('ascii',0,4)!=='icns')throw new Error('Invalid macOS ICNS');
   if(srcName.endsWith('.ico')&&!(b[0]===0&&b[1]===0&&b[2]===1&&b[3]===0))throw new Error('Invalid Windows ICO');
   fs.writeFileSync(tmp,b);fs.renameSync(tmp,dst);
 }
 console.log('Synced canonical Adelia web/macOS/Windows icon assets');
}catch(error){console.error('Desktop icon sync failed:',error&&error.message||error);process.exit(2)}
