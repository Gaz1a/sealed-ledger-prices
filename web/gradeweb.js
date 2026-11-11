// In-ledger card grader: same steps as scripts/grader/score.py (card found + flattened with OpenCV, 8 edge/corner crops,
// dinov2-small + PSA-trained head as one ONNX graph, int8). Runs in the browser; nothing is uploaded.
// window.LedgerGrader.grade(files, onStep) -> {photos:[{p8,grade,side,px}|null], p8, grade}
(function(){
 const RES=280, CARD_AR=63/88, MEAN=[0.485,0.456,0.406], STD=[0.229,0.224,0.225];
 let ready=null;
 function loadScript(src){return new Promise((ok,no)=>{const s=document.createElement('script');s.src=src;s.onload=ok;s.onerror=()=>no(new Error('load '+src));document.head.appendChild(s)})}
 async function init(step){
  if(ready)return ready;
  ready=(async()=>{
   step&&step('Loading the grader (first time only, ~35 MB)…');
   if(!window.cv||!window.cv.Mat){await loadScript('grader/opencv.js');
     for(let i=0;i<600&&!(window.cv&&window.cv.Mat);i++)await new Promise(r=>setTimeout(r,50));if(!(window.cv&&window.cv.Mat))throw new Error('opencv did not start')}
   if(!window.ort)await loadScript('grader/ort.wasm.min.js');
   ort.env.wasm.numThreads=1;ort.env.wasm.wasmPaths=new URL('grader/',location.href).href;
   const meta=await (await fetch('grader/parts.json')).json();const bufs=[];
   let C=null;try{C=await caches.open('ledger-grader-'+meta.bytes)}catch(e){}
   for(let i=0;i<meta.parts;i++){const u=new URL('grader/model'+i+'.wasm',location.href).href;let r=null;try{r=C&&await C.match(u)}catch(e){}
    if(!r){r=await fetch(u);if(!r.ok)throw new Error('grader file '+i+' missing');try{C&&await C.put(u,r.clone())}catch(e){}}
    bufs.push(new Uint8Array(await r.arrayBuffer()));step&&step(`Loading the grader… ${i+1}/${meta.parts}`)}
   const all=new Uint8Array(bufs.reduce((a,b)=>a+b.length,0));let o=0;for(const b of bufs){all.set(b,o);o+=b.length}
   return await ort.InferenceSession.create(all,{executionProviders:['wasm']});
  })();
  ready.catch(()=>{ready=null});return ready;
 }
 function quads(img,lo,hi,minFrac){
  const sc=1000/Math.max(img.rows,img.cols),small=new cv.Mat();cv.resize(img,small,new cv.Size(Math.floor(img.cols*sc),Math.floor(img.rows*sc)));
  const g=new cv.Mat();cv.cvtColor(small,g,cv.COLOR_RGBA2GRAY);cv.GaussianBlur(g,g,new cv.Size(5,5),0);
  const area=small.rows*small.cols;let out=null;const k=cv.Mat.ones(3,3,cv.CV_8U);
  for(const [a,b] of [[30,100],[50,150],[10,60],[80,200]]){
   const e=new cv.Mat();cv.Canny(g,e,a,b);cv.dilate(e,e,k);const cs=new cv.MatVector(),h=new cv.Mat();cv.findContours(e,cs,h,cv.RETR_LIST,cv.CHAIN_APPROX_SIMPLE);
   const L=[];for(let i=0;i<cs.size();i++){const c=cs.get(i);L.push([cv.contourArea(c),c])}L.sort((x,y)=>y[0]-x[0]);
   for(const [ar,c] of L.slice(0,12)){if(ar<minFrac*area)break;const p=new cv.Mat();cv.approxPolyDP(c,p,0.02*cv.arcLength(c,true),true);
    if(p.rows===4){const P=[];for(let i=0;i<4;i++)P.push([p.data32S[i*2]/sc,p.data32S[i*2+1]/sc]);
     const s=P.map(q=>q[0]+q[1]),d=P.map(q=>q[1]-q[0]),am=a=>a.indexOf(Math.min(...a)),aM=a=>a.indexOf(Math.max(...a));
     const q=[P[am(s)],P[am(d)],P[aM(s)],P[aM(d)]],n=(u,v)=>Math.hypot(u[0]-v[0],u[1]-v[1]);
     const wq=(n(q[0],q[1])+n(q[3],q[2]))/2,hq=(n(q[0],q[3])+n(q[1],q[2]))/2;
     if(hq>0&&wq/hq>=lo&&wq/hq<=hi)out=[q,hq]}
    p.delete();if(out)break}
   L.forEach(x=>x[1].delete());cs.delete();h.delete();e.delete();if(out)break}
  k.delete();g.delete();small.delete();return out}
 function warpTo(img,q,w,h){const src=cv.matFromArray(4,1,cv.CV_32FC2,q.flat()),dst=cv.matFromArray(4,1,cv.CV_32FC2,[0,0,w-1,0,w-1,h-1,0,h-1]);
  const M=cv.getPerspectiveTransform(src,dst),o=new cv.Mat();cv.warpPerspective(img,o,M,new cv.Size(w,h));src.delete();dst.delete();M.delete();return o}
 function warp(img,q,hq){const hh=Math.floor(Math.min(1400,hq)),ww=Math.floor(hh*CARD_AR);return warpTo(img,q,ww,hh)}
 function findCard(img){let r=quads(img,0.66,0.77,0.10);if(r)return [warp(img,r[0],r[1]),Math.floor(r[1])];
  const s=quads(img,0.53,0.66,0.12);if(!s)return [null,null];const sh=Math.floor(s[1]),sw=Math.floor(s[1]*0.62);
  const slab=warpTo(img,s[0],sw,sh),roi=slab.roi(new cv.Rect(0,Math.floor(0.22*s[1]),sw,sh-Math.floor(0.22*s[1]))).clone();slab.delete();
  r=quads(roi,0.66,0.77,0.30);if(!r){roi.delete();return [null,null]}const c=warp(roi,r[0],r[1]);roi.delete();return [c,Math.floor(r[1])]}
 function side(card){const m=new cv.Mat();cv.resize(card,m,new cv.Size(126,176));const rgb=new cv.Mat();cv.cvtColor(m,rgb,cv.COLOR_RGBA2RGB);const hsv=new cv.Mat();cv.cvtColor(rgb,hsv,cv.COLOR_RGB2HSV);
  const D=hsv.data,W=126,at=(y,x)=>[D[(y*W+x)*3],D[(y*W+x)*3+1]];let blue=0,yl=0,yn=0,rd=0,rn=0;
  for(let y=0;y<176;y++)for(let x=0;x<126;x++){const [H,S]=at(y,x);if(H>=95&&H<=130&&S>60)blue++;
   if(y>=10&&y<52&&x>=15&&x<111){yn++;if(H>=15&&H<=40&&S>90)yl++}if(y>=63&&y<92&&x>=38&&x<88){rn++;if((H<=8||H>=170)&&S>90)rd++}}
  m.delete();rgb.delete();hsv.delete();return blue/(126*176)>0.35&&yl/yn>0.10&&rd/rn>0.03?'back':'front'}
 function crops(card){const hh=card.rows,ww=card.cols,c=Math.floor(0.12*ww),cx=Math.floor((ww-c)/2),cy=Math.floor((hh-c)/2);
  const pts=[[0,0],[ww-c,0],[0,hh-c],[ww-c,hh-c],[cx,0],[cx,hh-c],[0,cy],[ww-c,cy]];const X=new Float32Array(8*3*RES*RES);
  pts.forEach(([x,y],i)=>{const r=card.roi(new cv.Rect(x,y,c,c)),a=new cv.Mat(),b=new cv.Mat();cv.resize(r,a,new cv.Size(320,320),0,0,cv.INTER_CUBIC);cv.resize(a,b,new cv.Size(RES,RES),0,0,cv.INTER_LINEAR);
   const D=b.data,N=RES*RES;for(let p=0;p<N;p++)for(let ch=0;ch<3;ch++)X[i*3*N+ch*N+p]=(D[p*4+ch]/255-MEAN[ch])/STD[ch];r.delete();a.delete();b.delete()});return X}
 async function toMat(file){const bm=await createImageBitmap(file,{imageOrientation:'from-image'});let w=bm.width,h=bm.height;const s=Math.min(1,3000/Math.max(w,h));if(s<1){w=Math.floor(w*s);h=Math.floor(h*s)}
  const cvs=document.createElement('canvas');cvs.width=w;cvs.height=h;cvs.getContext('2d').drawImage(bm,0,0,w,h);bm.close&&bm.close();return cv.imread(cvs)}
 async function scoreMat(sess,img){const [card,px]=findCard(img);if(!card||px<450){card&&card.delete();return null}
  const sd=side(card),X=crops(card);card.delete();
  const out=await sess.run({crops:new ort.Tensor('float32',X,[8,3,RES,RES]),side:new ort.Tensor('int64',BigInt64Array.from([sd==='back'?1n:0n]),[1])});
  return {p8:Math.round(out.p8.data[0]*1000)/1000,grade:Math.round(out.grade.data[0]*10)/10,side:sd,px}}
 async function grade(files,step){const sess=await init(step);const photos=[];let i=0;
  for(const f of files){i++;step&&step(`Grading photo ${i} of ${files.length}…`);await new Promise(r=>setTimeout(r,30));const m=await toMat(f);try{photos.push(await scoreMat(sess,m))}finally{m.delete()}}
  const ok=photos.filter(Boolean);return {photos,p8:ok.length?Math.min(...ok.map(x=>x.p8)):null,grade:ok.length?Math.min(...ok.map(x=>x.grade)):null}}
 window.LedgerGrader={grade,init,_q:async f=>{await init();const m=await toMat(f);const r=[m.rows,m.cols,quads(m,0.66,0.77,0.10)];m.delete();return r},_score:async(arr,sd=1)=>{const s=await init();const o=await s.run({crops:new ort.Tensor('float32',arr,[8,3,RES,RES]),side:new ort.Tensor('int64',BigInt64Array.from([BigInt(sd)]),[1])});return [o.p8.data[0],o.grade.data[0]]}};
})();
