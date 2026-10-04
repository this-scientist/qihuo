const STRATEGIES=[
 {id:'breakout',label:'突破'},
 {id:'fake_breakout',label:'假突破'},
 {id:'ema20_pullback',label:'EMA20回踩'},
 {id:'bar_shape',label:'K线形态'},
];

const isFiniteNumber=value=>Number.isFinite(Number(value));
const high=row=>Number(row?.[2]);
const low=row=>Number(row?.[3]);
const close=row=>Number(row?.[4]);

export function registeredStrategies(){
 return STRATEGIES.map(item=>({...item}));
}

export function ema20(candles=[]){
 const alpha=2/21;let previous=null;
 return candles.map(row=>{
  const value=close(row);
  if(!Number.isFinite(value))return null;
  previous=previous===null?value:alpha*value+(1-alpha)*previous;
  return previous;
 });
}

const signal=(row,{id,label,side,detail})=>({
 strategy:id,
 label,
 side,
 trade_date:row[0],
 close:close(row),
 detail,
});

export function evaluatePriceAction({candles=[],moving={}}={}){
 const rows=candles.filter(row=>row.length>=5&&row.slice(1,5).every(isFiniteNumber));
 const emaValues=Array.isArray(moving.ema20)?moving.ema20:ema20(rows);
 const signals=[];
 for(let i=1;i<rows.length;i++){
  const row=rows[i],prior=rows[i-1],lookback=rows.slice(Math.max(0,i-20),i);
  const priorHigh=Math.max(...lookback.map(high).filter(Number.isFinite));
  const priorLow=Math.min(...lookback.map(low).filter(Number.isFinite));
  if(Number.isFinite(priorHigh)&&high(row)>priorHigh&&close(row)>priorHigh){
   signals.push(signal(row,{id:'breakout',label:'突破',side:'long',detail:`收盘突破近${lookback.length}根高点`}));
  }
  if(Number.isFinite(priorLow)&&low(row)<priorLow&&close(row)<priorLow){
   signals.push(signal(row,{id:'breakout',label:'突破',side:'short',detail:`收盘跌破近${lookback.length}根低点`}));
  }
  if(Number.isFinite(priorHigh)&&high(row)>priorHigh&&close(row)<priorHigh){
   signals.push(signal(row,{id:'fake_breakout',label:'假突破',side:'short',detail:'上破前高后收回区间内'}));
  }
  if(Number.isFinite(priorLow)&&low(row)<priorLow&&close(row)>priorLow){
   signals.push(signal(row,{id:'fake_breakout',label:'假突破',side:'long',detail:'下破前低后收回区间内'}));
  }
  const ema=emaValues[i],prevClose=close(prior);
  if(Number.isFinite(ema)&&low(row)<=ema&&close(row)>ema&&prevClose>ema){
   signals.push(signal(row,{id:'ema20_pullback',label:'回踩',side:'long',detail:'顺势回踩EMA20后收在均线上方'}));
  }
  if(Number.isFinite(ema)&&high(row)>=ema&&close(row)<ema&&prevClose<ema){
   signals.push(signal(row,{id:'ema20_pullback',label:'回踩',side:'short',detail:'反弹测试EMA20后收在均线下方'}));
  }
  if(high(row)>high(prior)&&low(row)<low(prior)){
   signals.push(signal(row,{id:'bar_shape',label:'外包',side:close(row)>=row[1]?'long':'short',detail:'外包K线，波动扩张'}));
  }else if(high(row)<high(prior)&&low(row)>low(prior)){
   signals.push(signal(row,{id:'bar_shape',label:'内包',side:'neutral',detail:'内包K线，波动收缩'}));
  }
 }
 const summary=STRATEGIES.map(item=>({id:item.id,label:item.label,count:signals.filter(signal=>signal.strategy===item.id).length}));
 return {signals,summary};
}
