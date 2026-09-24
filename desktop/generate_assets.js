'use strict';
const fs=require('fs'),path=require('path');
const {PNG}=require('pngjs');
const png2icons=require('png2icons');
const brand=path.join(__dirname,'..','brand','adelia_icon'),build=path.join(__dirname,'build');
const source=path.join(brand,'adelia-icon-512.png');
const PNG_SIG=Buffer.from([137,80,78,71,13,10,26,10]);

function validPng(b,w,h){return b.length>64&&b.subarray(0,8).equals(PNG_SIG)&&b.readUInt32BE(16)===w&&b.readUInt32BE(20)===h}
function writeAtomic(name,data){const dst=path.join(build,name),tmp=dst+'.tmp';fs.writeFileSync(tmp,data);fs.renameSync(tmp,dst)}
function background(src){
  const pts=[[2,2],[src.width-3,2],[2,src.height-3],[src.width-3,src.height-3]];
  return pts.reduce((a,[x,y])=>{const i=(y*src.width+x)*4;a[0]+=src.data[i];a[1]+=src.data[i+1];a[2]+=src.data[i+2];return a},[0,0,0]).map(v=>v/pts.length);
}
function artworkBounds(src){
  const bg=background(src),row=new Uint16Array(src.height),col=new Uint16Array(src.width);
  for(let y=0;y<src.height;y++)for(let x=0;x<src.width;x++){
    const i=(y*src.width+x)*4;
    const d=Math.abs(src.data[i]-bg[0])+Math.abs(src.data[i+1]-bg[1])+Math.abs(src.data[i+2]-bg[2]);
    if(d>58){row[y]++;col[x]++}
  }
  const rowMin=Math.max(8,Math.floor(src.width*.08)),colMin=Math.max(8,Math.floor(src.height*.08));
  let top=0,bottom=src.height-1,left=0,right=src.width-1;
  while(top<bottom&&row[top]<rowMin)top++;while(bottom>top&&row[bottom]<rowMin)bottom--;
  while(left<right&&col[left]<colMin)left++;while(right>left&&col[right]<colMin)right--;
  const w=right-left+1,h=bottom-top+1;
  if(w<src.width*.45||h<src.height*.45)return {left:0,top:0,right:src.width-1,bottom:src.height-1};
  const inset=Math.max(1,Math.round(Math.min(w,h)*.015));
  return {left:left+inset,top:top+inset,right:right-inset,bottom:bottom-inset};
}
function nativeIcon(input){
  const src=PNG.sync.read(input),b=artworkBounds(src);
  const cropW=b.right-b.left+1,cropH=b.bottom-b.top+1;
  const size=1024,pad=72,tile=size-pad*2,radius=205;
  const out=new PNG({width:size,height:size});
  for(let y=pad;y<size-pad;y++)for(let x=pad;x<size-pad;x++){
    const sx=b.left+Math.min(cropW-1,Math.floor((x-pad)*cropW/tile));
    const sy=b.top+Math.min(cropH-1,Math.floor((y-pad)*cropH/tile));
    const di=(y*size+x)*4,si=(sy*src.width+sx)*4;
    const lx=x-pad,ly=y-pad;
    const cx=lx<radius?radius:(lx>tile-radius?tile-radius:lx);
    const cy=ly<radius?radius:(ly>tile-radius?tile-radius:ly);
    if((lx-cx)*(lx-cx)+(ly-cy)*(ly-cy)>radius*radius)continue;
    out.data[di]=src.data[si];out.data[di+1]=src.data[si+1];out.data[di+2]=src.data[si+2];out.data[di+3]=255;
  }
  return PNG.sync.write(out);
}
try{
  fs.mkdirSync(build,{recursive:true});
  const canonical=fs.readFileSync(source);
  if(!validPng(canonical,512,512))throw new Error('Canonical icon must be 512x512 PNG');
  writeAtomic('icon.png',canonical);
  const nativePng=nativeIcon(canonical);
  writeAtomic('icon-macos.png',nativePng);
  const icns=png2icons.createICNS(nativePng,png2icons.BILINEAR,0);
  const ico=png2icons.createICO(nativePng,png2icons.BILINEAR,0,false);
  if(!icns||icns.toString('ascii',0,4)!=='icns')throw new Error('Could not generate ICNS');
  if(!ico||!(ico[0]===0&&ico[1]===0&&ico[2]===1&&ico[3]===0))throw new Error('Could not generate ICO');
  writeAtomic('icon.icns',icns);writeAtomic('icon.ico',ico);
  console.log('Generated cropped transparent native Adelia icons from canonical PNG');
}catch(error){console.error('Desktop icon generation failed:',error&&error.message||error);process.exit(2)}
