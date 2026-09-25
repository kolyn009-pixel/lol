'use strict';
const fs=require('fs'),path=require('path');
const {PNG}=require('pngjs');
const png2icons=require('png2icons');
const root=path.join(__dirname,'..'),brand=path.join(root,'brand','adelia_icon'),build=path.join(__dirname,'build'),webIcons=path.join(root,'web','assets','icons');
const source=path.join(brand,'adelia-icon-512.png');
const PNG_SIG=Buffer.from([137,80,78,71,13,10,26,10]);

function validPng(b,w,h){return b.length>64&&b.subarray(0,8).equals(PNG_SIG)&&b.readUInt32BE(16)===w&&b.readUInt32BE(20)===h}
function writeAtomic(name,data){const dst=path.join(build,name),tmp=dst+'.tmp';fs.writeFileSync(tmp,data);fs.renameSync(tmp,dst)}
function edgeColor(src){
  const pts=[[2,2],[src.width-3,2],[2,src.height-3],[src.width-3,src.height-3],[Math.floor(src.width/2),2],[Math.floor(src.width/2),src.height-3]];
  return pts.reduce((a,[x,y])=>{const i=(y*src.width+x)*4;a[0]+=src.data[i];a[1]+=src.data[i+1];a[2]+=src.data[i+2];return a},[0,0,0]).map(v=>v/pts.length);
}
function removeConnectedOuterBackground(src){
  const bg=edgeColor(src),w=src.width,h=src.height;
  const seen=new Uint8Array(w*h),q=new Int32Array(w*h),out=new PNG({width:w,height:h});
  src.data.copy(out.data);
  let head=0,tail=0;
  const push=(x,y)=>{if(x<0||y<0||x>=w||y>=h)return;const p=y*w+x;if(seen[p])return;seen[p]=1;q[tail++]=p};
  for(let x=0;x<w;x++){push(x,0);push(x,h-1)}for(let y=0;y<h;y++){push(0,y);push(w-1,y)}
  while(head<tail){
    const p=q[head++],x=p%w,y=Math.floor(p/w),i=p*4;
    const r=src.data[i],g=src.data[i+1],b=src.data[i+2];
    const diff=Math.abs(r-bg[0])+Math.abs(g-bg[1])+Math.abs(b-bg[2]);
    const luma=.2126*r+.7152*g+.0722*b;
    if(diff>92&&luma>34)continue;
    out.data[i+3]=0;
    push(x+1,y);push(x-1,y);push(x,y+1);push(x,y-1);
  }
  return out;
}
function resizeSquare(input,size){
  const src=PNG.sync.read(input),out=new PNG({width:size,height:size});
  for(let y=0;y<size;y++)for(let x=0;x<size;x++){
    const sx=Math.min(src.width-1,Math.floor((x+.5)*src.width/size)),sy=Math.min(src.height-1,Math.floor((y+.5)*src.height/size));
    const si=(sy*src.width+sx)*4,di=(y*size+x)*4;for(let c=0;c<4;c++)out.data[di+c]=src.data[si+c];
  }
  return PNG.sync.write(out);
}
function alphaBounds(src){
  let left=src.width,top=src.height,right=-1,bottom=-1;
  for(let y=0;y<src.height;y++)for(let x=0;x<src.width;x++){
    if(src.data[(y*src.width+x)*4+3]<8)continue;
    if(x<left)left=x;if(x>right)right=x;if(y<top)top=y;if(y>bottom)bottom=y;
  }
  if(right<left||bottom<top)throw new Error('Native icon artwork disappeared after background removal');
  return {left,top,right,bottom};
}
function nativeIcon(input){
  const original=PNG.sync.read(input),src=removeConnectedOuterBackground(original),b=alphaBounds(src);
  const cropW=b.right-b.left+1,cropH=b.bottom-b.top+1;
  const size=1024,pad=78,tile=size-pad*2;
  const out=new PNG({width:size,height:size});
  for(let y=pad;y<size-pad;y++)for(let x=pad;x<size-pad;x++){
    const sx=b.left+Math.min(cropW-1,Math.floor((x-pad)*cropW/tile));
    const sy=b.top+Math.min(cropH-1,Math.floor((y-pad)*cropH/tile));
    const di=(y*size+x)*4,si=(sy*src.width+sx)*4;
    out.data[di]=src.data[si];out.data[di+1]=src.data[si+1];out.data[di+2]=src.data[si+2];out.data[di+3]=src.data[si+3];
  }
  return PNG.sync.write(out);
}
try{
  fs.mkdirSync(build,{recursive:true});fs.mkdirSync(webIcons,{recursive:true});
  const canonical=fs.readFileSync(source);
  if(!validPng(canonical,512,512))throw new Error('Canonical icon must be 512x512 PNG');
  writeAtomic('icon.png',canonical);
  for(const size of [32,180,192,256,512]){const data=size===512?canonical:resizeSquare(canonical,size),dst=path.join(webIcons,`adelia-icon-${size}.png`),tmp=dst+'.tmp';fs.writeFileSync(tmp,data);fs.renameSync(tmp,dst)}
  const nativePng=nativeIcon(canonical);
  writeAtomic('icon-macos.png',nativePng);
  const icns=png2icons.createICNS(nativePng,png2icons.BILINEAR,0);
  const ico=png2icons.createICO(nativePng,png2icons.BILINEAR,0,false);
  if(!icns||icns.toString('ascii',0,4)!=='icns')throw new Error('Could not generate ICNS');
  if(!ico||!(ico[0]===0&&ico[1]===0&&ico[2]===1&&ico[3]===0))throw new Error('Could not generate ICO');
  writeAtomic('icon.icns',icns);writeAtomic('icon.ico',ico);
  console.log('Generated Desktop and Web/PWA Adelia icons from one canonical PNG');
}catch(error){console.error('Desktop icon generation failed:',error&&error.message||error);process.exit(2)}
