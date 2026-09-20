export async function api(path,body){const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Error(result.error||`请求失败 ${response.status}`);return result}
export function asofQuery(){const value=new URLSearchParams(location.search).get('asof');return value?`asof=${encodeURIComponent(value)}`:''}
function compactDate(value){return String(value||'').replaceAll('-','')}
function inputDate(value){return value&&value.length===8?`${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6)}`:''}
export function download(name,text,type='application/json'){const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
export function mountTips(glossary){
 let active=null,pinned=false;
 const bubble=document.createElement('div');bubble.id='tip-bubble';document.body.appendChild(bubble);
 function place(el){
  bubble.classList.add('show');
  const w=bubble.offsetWidth,h=bubble.offsetHeight,vw=window.innerWidth,vh=window.innerHeight;
  const r=el.getBoundingClientRect();let x=r.left+r.width/2-w/2,pad=6;
  x=Math.max(pad,Math.min(x,vw-w-pad));
  let y=r.bottom+6;
  if(y+h>vh-pad)y=Math.max(pad,r.top-h-6);
  bubble.style.left=x+'px';bubble.style.top=y+'px';
 }
 function show(el,pin=false){pinned=pin;if(active===el&&!pin)return;active=el;bubble.textContent=el.dataset.tip||'';place(el)}
 function hide(force=false){if(pinned&&!force)return;pinned=false;active=null;bubble.classList.remove('show')}
 document.addEventListener('pointerover',e=>{const el=e.target.closest?.('.tip');if(el){pinned=false;show(el)}});
 document.addEventListener('pointerout',e=>{if(active&&!pinned&&(!e.relatedTarget||!active.contains(e.relatedTarget)))hide(true)});
 document.addEventListener('click',e=>{const el=e.target.closest?.('.tip');if(el){e.stopPropagation();show(el,true)}else hide(true)});
 document.addEventListener('scroll',()=>{if(active)place(active)},{capture:true});
 window.addEventListener('resize',()=>{if(active)place(active)});
 function tip(key){const text=glossary[key];if(!text)return null;const s=document.createElement('span');s.className='tip';s.textContent='?';s.dataset.tip=text;return s}
 function decorate(root=document){root.querySelectorAll('thead th').forEach(th=>{if(th.querySelector('.tip'))return;const mark=tip(th.textContent.trim());if(mark)th.appendChild(mark)})}
 return {tip,decorate};
}
export async function mountToolbar(){
 const header=document.querySelector('header'),links=document.createElement('div');links.className='page-links';
 for(const [href,label] of [['/','趋势总览'],['/scanner.html','期权扫描'],['/options.html','期权观察'],['/research.html','历史验证']]){const a=document.createElement('a');a.href=href+(location.search||'');a.textContent=label;if(location.pathname===href)a.className='active';links.appendChild(a)}
 header.insertBefore(links,header.lastElementChild);
 const controls=document.createElement('div');controls.className='data-toolbar';
 controls.innerHTML='<label>数据日期 <input id="data-asof" type="date" aria-label="数据日期"></label><button id="update-data">更新行情</button><span id="job-status" role="status"></span>';
 header.after(controls);
 const snapshots=await api('/api/snapshots'),date=controls.querySelector('#data-asof');
 const selected=new URLSearchParams(location.search).get('asof')||snapshots.active;
 date.value=inputDate(selected);
 date.onchange=()=>{const chosen=compactDate(date.value);if(!chosen)return;const url=new URL(location.href);url.searchParams.set('asof',chosen);location.href=url.href};
 const status=controls.querySelector('#job-status');let watching=false;
 async function watch(){
  if(watching)return;watching=true;
  try{let job;do{job=await api('/api/jobs');status.textContent=`${job.status} · ${job.message||'无任务'}`;controls.querySelectorAll('button').forEach(b=>b.disabled=['queued','running'].includes(job.status));if(['queued','running'].includes(job.status))await new Promise(r=>setTimeout(r,1800))}while(['queued','running'].includes(job.status));
   if(['success','partial'].includes(job.status)){const view=document.createElement('button');view.textContent='查看该日期';view.onclick=()=>{const url=new URL(location.href);url.searchParams.set('asof',job.asof);location.href=url.href};status.append(' ',view)}
  }catch(error){status.textContent=error.message}finally{watching=false}
 }
 controls.querySelector('#update-data').onclick=async()=>{try{await api('/api/update',{asof:compactDate(date.value)});watch()}catch(error){status.textContent=error.message}};
 watch();return {watch,status};
}
