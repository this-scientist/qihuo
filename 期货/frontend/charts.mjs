const NS='http://www.w3.org/2000/svg';
const palette=['#2764cf','#c17f2c','#248870','#8a64b0','#d35e63','#4c8da8','#a37d61','#819533','#ab609c','#5972a6','#ba9253','#479382'];
const observers=new WeakMap();
const element=(tag,attrs={},text)=>{const node=document.createElementNS(NS,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);if(text!==undefined)node.textContent=text;return node};
const dateTime=date=>Date.UTC(+date.slice(0,4),+date.slice(4,6)-1,+date.slice(6,8));
const shortDate=time=>new Date(time).toISOString().slice(5,10);
const number=(value,price)=>price?value.toFixed(1):`${value>=0?'+':''}${value.toFixed(2)}%`;

export function zoomRange({start,count,total},anchorIndex,factor,{minimum=12}={}){
 const nextCount=Math.max(Math.min(minimum,total),Math.min(total,Math.round(count*factor)));
 const ratio=count>1?Math.max(0,Math.min(1,anchorIndex/(count-1))):1;
 const anchor=start+Math.max(0,Math.min(count-1,anchorIndex));
 const nextStart=Math.max(0,Math.min(total-nextCount,Math.round(anchor-ratio*(nextCount-1))));
 return {start:nextStart,count:nextCount};
}

export function normalizePriceLevels(levels=[]){
 return levels.filter(level=>level?.value!==null&&level?.value!==''&&Number.isFinite(Number(level.value))&&['support','resistance'].includes(level.kind)).map((level,index)=>({
  id:level.id||`${level.kind}-${index}`,
  kind:level.kind,
  label:level.label||(level.kind==='support'?'支撑':'压力'),
  value:Number(level.value),
  systemValue:Number.isFinite(Number(level.systemValue))?Number(level.systemValue):Number(level.value),
 }));
}

export function priceFromPointer(pointerY,{top,height,low,high}){
 const ratio=Math.max(0,Math.min(1,(pointerY-top)/height));
 return high-ratio*(high-low);
}

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

export function renderCandlestickChart(container,{candles=[],moving={},signals=[],levels=[]},{window=80,title='K线图',interactive=false,activity=true,onLevelChange}={}){
 observers.get(container)?.disconnect();container.replaceChildren();
 const allRows=candles.filter(row=>row.length>=5&&row.slice(1,5).every(Number.isFinite));
 if(allRows.length<2){const empty=document.createElement('div');empty.className='empty';empty.textContent='暂无可展示的K线';container.appendChild(empty);return null}
 const initialCount=Math.min(allRows.length,Math.max(12,window));
 let range={start:allRows.length-initialCount,count:initialCount},priceLevels=normalizePriceLevels(levels),pan=null;
 const surface=document.createElement('div'),svg=element('svg',{'class':'chart-svg kline-svg',role:'img','aria-label':title}),legend=document.createElement('div'),tip=document.createElement('div');
 surface.className='chart-surface kline-chart-surface';legend.className='chart-legend kline-legend';tip.className='chart-tooltip';tip.hidden=true;tip.setAttribute('role','tooltip');surface.append(svg,tip);container.append(surface,legend);
 const maDefinitions=Object.entries(moving).filter(([,values])=>Array.isArray(values)).map(([key,values],index)=>({id:key,label:key.toUpperCase(),color:palette[(index+1)%palette.length],values}));
 maDefinitions.forEach(item=>{const button=document.createElement('button');button.type='button';button.setAttribute('aria-pressed','true');const swatch=document.createElement('span');swatch.className='swatch';swatch.style.borderColor=item.color;button.append(swatch,document.createTextNode(item.label));legend.appendChild(button)});
 for(const item of [{label:'成交量',color:'#9aa8ba',kind:'volume'},{label:'持仓量',color:'#a06b2c',kind:'oi'}]){
  const key=document.createElement('span');key.className='chart-key';key.dataset.kind=item.kind;const swatch=document.createElement('i');swatch.style.borderColor=item.color;key.append(swatch,document.createTextNode(item.label));legend.appendChild(key);
 }
 for(const level of priceLevels){
  const key=document.createElement('span');key.className=`chart-key level-${level.kind}`;key.dataset.levelLegend=level.id;const swatch=document.createElement('i');key.append(swatch,document.createTextNode(`${level.label} ${level.value.toFixed(2)}`));legend.appendChild(key);
 }
 let lastLayout=null;
 if(interactive){
  surface.addEventListener('pointermove',event=>{
   if(!pan||!lastLayout)return;
   const bounds=svg.getBoundingClientRect(),px=(event.clientX-bounds.left)*lastLayout.width/bounds.width,shift=Math.round((pan.x-px)/lastLayout.plotW*range.count),next=Math.max(0,Math.min(allRows.length-range.count,pan.start+shift));
   if(next!==range.start){range.start=next;draw()}
  });
  const endPan=event=>{if(!pan)return;pan=null;if(surface.hasPointerCapture?.(event.pointerId))surface.releasePointerCapture(event.pointerId)};
  surface.addEventListener('pointerup',endPan);surface.addEventListener('pointercancel',endPan);
 }
 const notifyLevels=()=>onLevelChange?.(priceLevels.map(level=>({...level})));
 const resetView=()=>{range={start:allRows.length-initialCount,count:initialCount};draw()};
 const applyZoom=(factor,anchor=.5)=>{const anchorIndex=(range.count-1)*anchor;range=zoomRange({...range,total:allRows.length},anchorIndex,factor);draw()};
 const resetLevels=()=>{priceLevels=priceLevels.map(level=>({...level,value:level.systemValue}));notifyLevels();draw()};
 function draw(){
  svg.replaceChildren();tip.hidden=true;
  const rows=allRows.slice(range.start,range.start+range.count),width=Math.max(300,surface.getBoundingClientRect().width),height=interactive?590:430;
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('height',height);svg.dataset.visibleStart=rows[0][0];svg.dataset.visibleEnd=rows.at(-1)[0];svg.append(element('title',{},title));
  const left=68,right=72,top=24,bottom=40,gap=28,activityH=activity?105:0,plotH=height-top-bottom-activityH-(activity?gap:0),activityTop=top+plotH+gap,plotW=width-left-right;
  lastLayout={width,plotW,left};
  for(const level of priceLevels){const item=legend.querySelector(`[data-level-legend="${level.id}"]`);if(item)item.lastChild.textContent=`${level.label} ${level.value.toFixed(2)}`}
  const visibleDates=new Set(rows.map(row=>row[0])),visibleSignals=signals.filter(signal=>visibleDates.has(signal.trade_date));
  const maSeries=maDefinitions.map(item=>({...item,values:item.values.slice(range.start,range.start+range.count)}));
  const basePrices=rows.flatMap(row=>[row[2],row[3]]).concat(maSeries.flatMap(item=>item.values.filter(Number.isFinite))).concat(visibleSignals.map(s=>s.close).filter(Number.isFinite));
  const rawLow=Math.min(...basePrices),rawHigh=Math.max(...basePrices),rawSpan=Math.max(rawHigh-rawLow,1);
  const nearbyLevels=priceLevels.map(level=>level.value).filter(value=>value>=rawLow-rawSpan*.2&&value<=rawHigh+rawSpan*.2);
  const minY=Math.min(...basePrices,...nearbyLevels),maxY=Math.max(...basePrices,...nearbyLevels),pad=Math.max((maxY-minY)*.08,1),lo=minY-pad,hi=maxY+pad;
  const x=index=>left+plotW*(index+.5)/rows.length,y=value=>top+3+(hi-value)/(hi-lo)*(plotH-6),bodyW=Math.max(2,Math.min(13,plotW/rows.length*.58));
  svg.append(element('rect',{'data-chart-frame':'price',x:left,y:top,width:plotW,height:plotH,fill:'none',stroke:'#e2e7ee'}));
  for(let i=0;i<5;i++){const value=lo+(hi-lo)*i/4,py=y(value);svg.append(element('line',{x1:left,y1:py,x2:width-right,y2:py,stroke:'#edf0f5'}));svg.append(element('text',{x:left-8,y:py+4,'text-anchor':'end'},value.toFixed(0)))}
  svg.append(element('text',{x:left,y:13,'class':'axis-title'},'复权K线 / 均线'));
  rows.forEach((row,index)=>{
   const [,open,high,low,close]=row,px=x(index),up=close>=open,color=up?'#cb524a':'#24846b';
   svg.append(element('line',{'data-candle-wick':'',x1:px,y1:y(high),x2:px,y2:y(low),stroke:color,'stroke-width':1.2}));
   svg.append(element('rect',{'data-candle':'',x:px-bodyW/2,y:Math.min(y(open),y(close)),width:bodyW,height:Math.max(1,Math.abs(y(open)-y(close))),fill:up?'#fff1ef':'#e8f6f1',stroke:color,'stroke-width':1.2}));
  });
  maSeries.forEach(item=>{
   const points=item.values.map((value,index)=>Number.isFinite(value)?[index,value]:null).filter(Boolean);
   if(points.length>1)svg.append(element('path',{'data-series':item.id,d:points.map(([index,value],i)=>`${i?'L':'M'}${x(index).toFixed(2)},${y(value).toFixed(2)}`).join(' '),fill:'none',stroke:item.color,'stroke-width':1.7}));
  });
  visibleSignals.forEach(signal=>{
   const index=rows.findIndex(row=>row[0]===signal.trade_date);if(index<0)return;
   const isLong=signal.side==='long',px=x(index),py=y(signal.close)+(isLong?16:-12),label=element('text',{x:px,y:py,'text-anchor':'middle','class':`kline-signal ${isLong?'long':'short'}`},signal.label);
   svg.append(element('circle',{cx:px,cy:y(signal.close),r:4,fill:isLong?'#cb524a':'#24846b'}));svg.append(label);
  });
  const levelHandles=[];
  for(const level of priceLevels){
   if(level.value<lo||level.value>hi)continue;
   const color=level.kind==='resistance'?'#c43f3f':'#21835d',py=y(level.value);
   const line=element('line',{x1:left,x2:width-right,y1:py,y2:py,stroke:color,'stroke-width':1.5,'stroke-dasharray':'7 5','data-level-line':level.id});
   const label=element('text',{x:width-right+5,y:py+4,fill:color,'data-level-label':level.kind,'data-level-id':level.id},level.value.toFixed(2));
   svg.append(line,label);
   if(interactive){
    const handle=element('line',{x1:left,x2:width-right,y1:py,y2:py,stroke:'transparent','stroke-width':14,'data-price-level':level.kind,'data-level-id':level.id,tabindex:0,role:'slider','aria-label':`拖动${level.label}`});
    handle.style.cursor='ns-resize';
    handle.addEventListener('pointerdown',event=>{event.preventDefault();event.stopPropagation();handle.setPointerCapture(event.pointerId);handle.dataset.dragging='true'});
    handle.addEventListener('pointermove',event=>{
     if(handle.dataset.dragging!=='true')return;
     const bounds=svg.getBoundingClientRect(),pointerY=(event.clientY-bounds.top)*height/bounds.height,next=priceFromPointer(pointerY,{top,height:plotH,low:lo,high:hi});
     level.value=Number(next.toFixed(Math.abs(next)>=100?2:4));const nextY=y(level.value);
     for(const node of [line,handle]){node.setAttribute('y1',nextY);node.setAttribute('y2',nextY)}label.setAttribute('y',nextY+4);label.textContent=level.value.toFixed(2);
     const legendItem=legend.querySelector(`[data-level-legend="${level.id}"]`);if(legendItem)legendItem.lastChild.textContent=`${level.label} ${level.value.toFixed(2)}`;
    });
    const finish=()=>{if(handle.dataset.dragging==='true'){delete handle.dataset.dragging;notifyLevels()}};
    handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',finish);levelHandles.push(handle);
   }
  }
  if(activity){
   const volumes=rows.map(row=>Number.isFinite(row[5])?row[5]:null),openInterest=rows.map(row=>Number.isFinite(row[6])?row[6]:null),maxVol=Math.max(...volumes.filter(Number.isFinite),1),oiValues=openInterest.filter(Number.isFinite),oiLow=oiValues.length?Math.min(...oiValues):0,oiHigh=oiValues.length?Math.max(...oiValues):1,oiSpan=Math.max(oiHigh-oiLow,1);
   const volY=value=>activityTop+activityH-(value/maxVol)*(activityH-8),oiY=value=>activityTop+4+(oiHigh-value)/oiSpan*(activityH-8);
   svg.append(element('rect',{'data-chart-frame':'activity',x:left,y:activityTop,width:plotW,height:activityH,fill:'none',stroke:'#e2e7ee'}));
   svg.append(element('text',{x:left,y:activityTop-8,'class':'axis-title'},'成交量 / 持仓量'));
   rows.forEach((row,index)=>{if(!Number.isFinite(row[5]))return;const px=x(index),up=row[4]>=row[1];svg.append(element('rect',{'data-volume-bar':'',x:px-bodyW/2,y:volY(row[5]),width:bodyW,height:Math.max(1,activityTop+activityH-volY(row[5])),fill:up?'#e8b2ad':'#9dd0bf',opacity:.75}))});
   const oiPoints=openInterest.map((value,index)=>Number.isFinite(value)?[index,value]:null).filter(Boolean);
   if(oiPoints.length>1)svg.append(element('path',{'data-open-interest':'',d:oiPoints.map(([index,value],i)=>`${i?'L':'M'}${x(index).toFixed(2)},${oiY(value).toFixed(2)}`).join(' '),fill:'none',stroke:'#a06b2c','stroke-width':1.8}));
   svg.append(element('text',{x:width-right+5,y:activityTop+10,fill:'#a06b2c'},oiValues.length?Math.round(oiHigh).toLocaleString('zh-CN'):'—'));
   svg.append(element('text',{x:left-8,y:activityTop+10,'text-anchor':'end'},Math.round(maxVol).toLocaleString('zh-CN')));
  }
  const ticks=width<420?3:width<620?4:6;
  for(let i=0;i<ticks;i++){const index=Math.round((rows.length-1)*i/(ticks-1)),px=x(index);svg.append(element('text',{x:px,y:height-15,'text-anchor':i===0?'start':i===ticks-1?'end':'middle'},shortDate(dateTime(rows[index][0]))))}
  const guide=element('line',{x1:0,x2:0,y1:top,y2:activity?activityTop+activityH:top+plotH,stroke:'#8390a3',visibility:'hidden','stroke-dasharray':'3 3'});svg.append(guide);
  const overlay=element('rect',{x:left,y:top,width:plotW,height:(activity?activityTop+activityH:top+plotH)-top,fill:'transparent','data-kline-overlay':''});
  const pointerIndex=event=>{const bounds=svg.getBoundingClientRect(),px=(event.clientX-bounds.left)*width/bounds.width;return Math.max(0,Math.min(rows.length-1,Math.round((px-left)/plotW*rows.length-.5)))};
  const showTip=event=>{
   const index=pointerIndex(event),row=rows[index],gx=x(index);guide.setAttribute('x1',gx);guide.setAttribute('x2',gx);guide.setAttribute('visibility','visible');tip.replaceChildren();
   const date=document.createElement('strong');date.textContent=`${row[0].slice(0,4)}-${row[0].slice(4,6)}-${row[0].slice(6)}`;tip.appendChild(date);
   [['开',row[1]],['高',row[2]],['低',row[3]],['收',row[4]],['成交量',row[5]],['持仓量',row[6]]].forEach(([label,value])=>{const item=document.createElement('div'),l=document.createElement('span'),v=document.createElement('span');l.textContent=label;v.textContent=Number.isFinite(value)?(label.length>1?Math.round(value).toLocaleString('zh-CN'):value.toFixed(2)):'—';item.append(l,v);tip.appendChild(item)});
   tip.hidden=false;tip.style.left=`${Math.max(0,Math.min(width-tip.offsetWidth,gx+12))}px`;tip.style.top='32px';
  };
  overlay.addEventListener('pointermove',event=>{if(!pan)showTip(event)});
  overlay.addEventListener('pointerleave',()=>{if(!pan){tip.hidden=true;guide.setAttribute('visibility','hidden')}});
  if(interactive){
   overlay.style.cursor='grab';
   overlay.addEventListener('wheel',event=>{event.preventDefault();const index=pointerIndex(event),factor=event.deltaY<0?.75:1.34;range=zoomRange({...range,total:allRows.length},index,factor);draw()},{passive:false});
   overlay.addEventListener('pointerdown',event=>{surface.setPointerCapture(event.pointerId);pan={x:(event.clientX-svg.getBoundingClientRect().left)*width/svg.getBoundingClientRect().width,start:range.start};overlay.style.cursor='grabbing'});
   overlay.addEventListener('dblclick',resetView);
  }
  svg.append(overlay,...levelHandles);
 }
 draw();const observer=new ResizeObserver(draw);observer.observe(surface);observers.set(container,observer);
 return {zoomIn:()=>applyZoom(.75),zoomOut:()=>applyZoom(1.34),resetView,resetLevels,getLevels:()=>priceLevels.map(level=>({...level}))};
}
