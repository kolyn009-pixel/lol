function ensureBrandAssets(){
 const base='/app/assets/icons/',version='?v=20261022-unified2';
 const png=size=>base+'adelia-mark-'+size+'.png'+version;
 document.querySelectorAll('link[rel~="icon"],link[rel="apple-touch-icon"]').forEach(link=>{
  const rel=(link.getAttribute('rel')||'').toLowerCase();
  if(rel.includes('apple-touch-icon')){link.href=png(180);link.type='image/png';link.sizes='180x180'}
  else if(rel.includes('shortcut')){link.href=base+'adelia-mark.ico'+version;link.type='image/x-icon';link.removeAttribute('sizes')}
  else{const size=link.getAttribute('sizes')==='192x192'?192:32;link.href=png(size);link.type='image/png';link.sizes=size+'x'+size}
 });
 document.querySelectorAll('header .brand img,footer .brand img').forEach(img=>{
  img.src=png(180);img.removeAttribute('srcset');img.removeAttribute('data-src');
  if(img.parentElement?.tagName==='PICTURE')img.parentElement.querySelectorAll('source').forEach(source=>source.remove());
 });
}
