// Daily adjusted OHLC only. Never mix live raw contract prices into these distances.
const finite=x=>typeof x==='number'&&Number.isFinite(x);
export function buildPullbackLists(data={}){
 const result={long:[],short:[],excluded:0};
 for(const row of data.decisions||data.records||[]){
  const code=row.ts_code||row.code,bars=data.candles?.[code]||[];
  if(bars.length<65||bars.some(b=>!b.slice(1,5).every(finite)||b[2]<b[3]||b[4]<=0)){result.excluded++;continue;}
  let e20=bars[0][4],e60=e20,atr=bars[0][2]-bars[0][3];const history=[];
  bars.forEach((b,i)=>{
   if(i){e20+=(b[4]-e20)*2/21;e60+=(b[4]-e60)*2/61;
    const tr=Math.max(b[2]-b[3],Math.abs(b[2]-bars[i-1][4]),Math.abs(b[3]-bars[i-1][4]));atr+=(tr-atr)/14;}
   history.push(e20);
  });
  const slope=e20-history.at(-6),side=e20>e60&&slope>0?'long':e20<e60&&slope<0?'short':null;
  if(!side||!finite(atr)||atr<=0){result.excluded++;continue;}
  const b=bars.at(-1),distanceAtr=(b[4]-e20)/atr,sign=side==='long'?1:-1,touched=b[3]<=e20&&b[2]>=e20;
  const status=sign*distanceAtr<0?'穿线待观察':touched?'触线后收回':Math.abs(distanceAtr)<=.5?'接近均线':'远离均线';
  result[side].push({...row,code,close:b[4],ema20:e20,ema60:e60,atr14:atr,distanceAtr,distancePct:(b[4]/e20-1)*100,status,date:b[0],slope});
 }
 for(const side of ['long','short'])result[side].sort((a,b)=>Math.abs(a.distanceAtr)-Math.abs(b.distanceAtr)||a.code.localeCompare(b.code));
 return result;
}
