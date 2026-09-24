'use strict';
const fs=require('fs'),path=require('path');
const {PNG}=require('pngjs');
const png2icons=require('png2icons');
const brand=path.join(__dirname,'..','brand','adelia_icon'),build=path.join(__dirname,'build');
const source=path.join(brand,'adelia-icon-512.png');
const PNG_SIG=Buffer.from([137,80,78,71,13,10,26,10]);

function validPng(b,w,h){return b.length>64&&b.subarray(0,8).equals(PNG_SIG)&&b.readUInt32BE(16)===w&&b.readUInt32BE(20)===h}
function writeAtomic(name,data){const dst=path.join(build,name),tmp=dst+'.tmp';fs.writeFileSync(tmp,data);fs.renameSync(tmp,dst)}
function roundedAlphaIcon(input){
  const src=PNG.sync.read(input);
  const size=1024,pad=72,radius=205;
  const out=new PNG({width:size,height:size});
  for(let y=0;y<size;y++)for(let x=0;x<size;x++){
    const sx=Math.min(src.width-1,Math.max(0,Math.floor((x-pad)*src.width/(size-pad*2))));
    const sy=Math.min(src.height-1,Math.max(0,Math.floor((y-pad)*src.height/(size-pad*2))));
    const di=(y*size+x)*4,si=(sy*src.width+sx)*4;
    out.data[di]=src.data[si];out.data[di+1]=src.data[si+1];out.data[di+2]=src.data[si+2];
    let inside=x>=pad&&x<size-pad&&y>=pad&&y<size-pad;
    if(inside){
      const lx=x-pad,ly=y-pad,w=size-pad*2,h=w;
      const cx=lx<radius?radius:(lx>w-radius?w-radius:lx);
      const cy=ly<radius?radius:(ly>h-radius?h-radius:ly);
      inside=(lx-cx)*(lx-cx)+(ly-cy)*(ly-cy)<=radius*radius;
    }
    out.data[di+3]=inside?255:0;
  }
  return PNG.sync.write(out);
}
try{
  fs.mkdirSync(build,{recursive:true});
  const canonical=fs.readFileSync(source);
  if(!validPng(canonical,512,512))throw new Error('Canonical icon must be 512x512 PNG');
  writeAtomic('icon.png',canonical);
  const nativePng=roundedAlphaIcon(canonical);
  writeAtomic('icon-macos.png',nativePng);
  const icns=png2icons.createICNS(nativePng,png2icons.BILINEAR,0);
  const ico=png2icons.createICO(nativePng,png2icons.BILINEAR,0,false);
  if(!icns||icns.toString('ascii',0,4)!=='icns')throw new Error('Could not generate ICNS');
  if(!ico||!(ico[0]===0&&ico[1]===0&&ico[2]===1&&ico[3]===0))throw new Error('Could not generate ICO');
  writeAtomic('icon.icns',icns);writeAtomic('icon.ico',ico);
  console.log('Generated transparent native Adelia icons from canonical PNG');
}catch(error){console.error('Desktop icon generation failed:',error&&error.message||error);process.exit(2)}
