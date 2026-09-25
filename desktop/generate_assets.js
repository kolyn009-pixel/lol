'use strict';
const fs=require('fs'),path=require('path');
const {PNG}=require('pngjs');
const png2icons=require('png2icons');
const root=path.join(__dirname,'..'),brand=path.join(root,'brand','adelia_icon'),build=path.join(__dirname,'build'),webIcons=path.join(root,'web','assets','icons');
const source=path.join(brand,'adelia-icon-512.png');
const PNG_SIG=Buffer.from([137,80,78,71,13,10,26,10]);

function validPng(b,w,h){return b.length>64&&b.subarray(0,8).equals(PNG_SIG)&&b.readUInt32BE(16)===w&&b.readUInt32BE(20)===h}
function writeAtomic(name,data){const dst=path.join(build,name),tmp=dst+'.tmp';fs.writeFileSync(tmp,data);fs.renameSync(tmp,dst)}
function resizeSquare(input,size){
  const src=PNG.sync.read(input),out=new PNG({width:size,height:size});
  for(let y=0;y<size;y++)for(let x=0;x<size;x++){
    const sx=Math.min(src.width-1,Math.floor((x+.5)*src.width/size)),sy=Math.min(src.height-1,Math.floor((y+.5)*src.height/size));
    const si=(sy*src.width+sx)*4,di=(y*size+x)*4;for(let c=0;c<4;c++)out.data[di+c]=src.data[si+c];
  }
  return PNG.sync.write(out);
}
try{
  fs.mkdirSync(build,{recursive:true});fs.mkdirSync(webIcons,{recursive:true});
  const canonical=fs.readFileSync(source);
  if(!validPng(canonical,512,512))throw new Error('Canonical icon must be 512x512 PNG');
  writeAtomic('icon.png',canonical);
  for(const size of [32,180,192,256,512]){const data=size===512?canonical:resizeSquare(canonical,size),dst=path.join(webIcons,`adelia-icon-${size}.png`),tmp=dst+'.tmp';fs.writeFileSync(tmp,data);fs.renameSync(tmp,dst)}
  const nativePng=resizeSquare(canonical,1024);
  writeAtomic('icon-macos.png',nativePng);
  const icns=png2icons.createICNS(nativePng,png2icons.BILINEAR,0);
  const ico=png2icons.createICO(nativePng,png2icons.BILINEAR,0,false);
  if(!icns||icns.toString('ascii',0,4)!=='icns')throw new Error('Could not generate ICNS');
  if(!ico||!(ico[0]===0&&ico[1]===0&&ico[2]===1&&ico[3]===0))throw new Error('Could not generate ICO');
  writeAtomic('icon.icns',icns);writeAtomic('icon.ico',ico);
  console.log('Generated exact Desktop and Web/PWA Adelia artwork from one canonical PNG');
}catch(error){console.error('Desktop icon generation failed:',error&&error.message||error);process.exit(2)}
