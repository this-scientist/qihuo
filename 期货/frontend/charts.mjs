const NS='http://www.w3.org/2000/svg';
const palette=['#2764cf','#c17f2c','#248870','#8a64b0','#d35e63','#4c8da8','#a37d61','#819533','#ab609c','#5972a6','#ba9253','#479382'];
const observers=new WeakMap();
const element=(tag,attrs={},text)=>{const node=document.createElementNS(NS,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);if(text!==undefined)node.textContent=text;return node};
const dateTime=date=>Date.UTC(+date.slice(0,4),+date.slice(4,6)-1,+date.slice(6,8));
const shortDate=time=>new Date(time).toISOString().slice(5,10);
const number=(value,price)=>price?value.toFixed(1):`${value>=0?'+':''}${value.toFixed(2)}%`;

export function renderChart(container,input,{window=60,price=false,priceLabel='复权价格',title='走势对比'}={}){
 observers.get(container)?.disconnect();container.replaceChildren();
 const series=input.map((item,index)=>{
  const values=item.values.slice(-(window+1));const base=values.find(v=>Number.isFinite(v[1]))?.[1];
  return {...item,color:item.color||palette[index%palette.length],dash:index>=palette.length?'5 3':null,
   points:values.filter(v=>Number.isFinite(v[1])).map(v=>({date:v[0],x:dateTime(v[0]),y:price?v[1]:(v[1]/base-1)*100}))};
 }).filter(item=>item.points.length>1);
 if(!series.length){const empty=document.createElement('div');empty.className='empty';empty.textContent='暂无可对比的品种';container.appendChild(empty);return}
 const hidden=new Set(), surface=document.createElement('div'),svg=element('svg',{'class':'chart-svg',role:'img','aria-label':title}),legend=document.createElement('div'),tip=document.createElement('div');
 surface.className='chart-surface';legend.className='chart-legend';tip.className='chart-tooltip';tip.hidden=true;tip.setAttribute('role','tooltip');surface.append(svg,tip);container.append(surface,legend);
 let pinned=false;
 series.forEach(item=>{
  const button=document.createElement('button');button.type='button';button.setAttribute('aria-pressed','true');button.dataset.series=item.id;
  const swatch=document.createElement('span');swatch.className='swatch';swatch.style.borderColor=item.color;if(item.dash)swatch.style.borderTopStyle='dashed';
  button.append(swatch,document.createTextNode(`${item.label} ${number(item.points.at(-1).y,price)}`));
  button.onclick=()=>{hidden.has(item.id)?hidden.delete(item.id):hidden.add(item.id);button.setAttribute('aria-pressed',String(!hidden.has(item.id)));draw()};legend.appendChild(button);
 });
 function draw(){
  svg.replaceChildren();tip.hidden=true;pinned=false;
  const width=Math.max(280,surface.getBoundingClientRect().width),height=price?285:350;
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('height',height);
  svg.append(element('title',{},title));
  const displayed=series.filter(item=>!hidden.has(item.id));if(!displayed.length)return;
  const points=displayed.flatMap(item=>item.points),xs=points.map(p=>p.x),ys=points.map(p=>p.y);
  const left=price?65:57,right=14,top=22,bottom=47,plotW=width-left-right,plotH=height-top-bottom;
  const xmin=Math.min(...xs),xmax=Math.max(...xs),minY=Math.min(...ys,price?Infinity:0),maxY=Math.max(...ys,price?-Infinity:0),pad=Math.max((maxY-minY)*.08,price?1:.8);
  const lo=minY-pad,hi=maxY+pad,x=t=>left+3+(t-xmin)/(xmax-xmin)*(plotW-6),y=v=>top+3+(hi-v)/(hi-lo)*(plotH-6);
  svg.append(element('rect',{'data-chart-frame':'',x:left,y:top,width:plotW,height:plotH,fill:'none',stroke:'#e2e7ee'}));
  for(let i=0;i<5;i++){
   const value=lo+(hi-lo)*i/4,py=y(value);
   svg.append(element('line',{x1:left,y1:py,x2:width-right,y2:py,stroke:'#edf0f5'}));
   svg.append(element('text',{x:left-8,y:py+4,'text-anchor':'end'},price?value.toFixed(0):`${value.toFixed(0)}%`));
  }
  const ticks=width<380?3:width<550?4:6;
  for(let i=0;i<ticks;i++){
   const t=xmin+(xmax-xmin)*i/(ticks-1),px=x(t);
   svg.append(element('text',{x:px,y:height-27,'text-anchor':i===0?'start':i===ticks-1?'end':'middle'},shortDate(t)));
  }
  svg.append(element('text',{x:left,y:12,'class':'axis-title'},price?priceLabel:'累计涨跌幅（%）'));
  svg.append(element('text',{x:left+plotW/2,y:height-7,'text-anchor':'middle','class':'axis-title'},'日期'));
  if(!price)svg.append(element('line',{x1:left,y1:y(0),x2:width-right,y2:y(0),stroke:'#cbd3df'}));
  displayed.forEach(item=>svg.append(element('path',{d:item.points.map((p,i)=>`${i?'L':'M'}${x(p.x).toFixed(2)},${y(p.y).toFixed(2)}`).join(' '),fill:'none',stroke:item.color,'stroke-width':2,'stroke-dasharray':item.dash||'','data-series':item.id})));
  const guide=element('line',{'data-hover-guide':'',x1:0,x2:0,y1:top,y2:top+plotH,stroke:'#8390a3',visibility:'hidden'});svg.append(guide);
  const markers=displayed.map(item=>{const marker=element('circle',{r:3,fill:item.color,visibility:'hidden','data-hover-marker':item.id});svg.append(marker);return marker});
  function show(event){
   const bounds=svg.getBoundingClientRect(),px=(event.clientX-bounds.left)*width/bounds.width,t=xmin+(px-left-3)/(plotW-6)*(xmax-xmin);
   const anchor=displayed[0].points.reduce((a,b)=>Math.abs(a.x-t)<Math.abs(b.x-t)?a:b);
   const gx=x(anchor.x);guide.setAttribute('x1',gx);guide.setAttribute('x2',gx);guide.setAttribute('visibility','visible');
   tip.replaceChildren();const date=document.createElement('strong');date.textContent=`${anchor.date.slice(0,4)}-${anchor.date.slice(4,6)}-${anchor.date.slice(6)}`;tip.appendChild(date);
   displayed.forEach((item,i)=>{
    const point=item.points.find(p=>p.x===anchor.x);if(!point){markers[i].setAttribute('visibility','hidden');return}
    markers[i].setAttribute('cx',gx);markers[i].setAttribute('cy',y(point.y));markers[i].setAttribute('visibility','visible');
    const row=document.createElement('div'),label=document.createElement('span'),value=document.createElement('span');label.textContent=item.label;value.textContent=number(point.y,price);row.append(label,value);tip.appendChild(row);
   });tip.hidden=false;tip.style.left=`${Math.max(0,Math.min(width-tip.offsetWidth,gx+12))}px`;tip.style.top='32px';
  }
  function hide(){if(pinned)return;tip.hidden=true;guide.setAttribute('visibility','hidden');markers.forEach(m=>m.setAttribute('visibility','hidden'))}
  const overlay=element('rect',{x:left,y:top,width:plotW,height:plotH,fill:'transparent','data-hover-overlay':'cross-series'});
  overlay.addEventListener('pointermove',e=>{if(!pinned)show(e)});overlay.addEventListener('pointerleave',hide);overlay.addEventListener('click',e=>{pinned=!pinned;show(e)});svg.append(overlay);
 }
 draw();const observer=new ResizeObserver(draw);observer.observe(surface);observers.set(container,observer);
}
