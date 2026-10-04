const DIRECTION={long:'偏多',short:'偏空',neutral:'中性',LONG:'偏多',SHORT:'偏空',NEUTRAL:'中性'};
const STRUCTURE={SUPPORT:'同向',CONFLICT:'背离',NEUTRAL:'中性',UNKNOWN:'数据不足'};
const OPTION={Call:'做：买认购',Put:'做：买认沽','不做':'不做'};

const dir=value=>DIRECTION[value]||value||'—';
const structure=value=>STRUCTURE[value]||value||'—';
const option=value=>OPTION[value]||value||'—';
const isLong=row=>row?.decision_side==='long'||row?.decision_direction==='LONG';
const isShort=row=>row?.decision_side==='short'||row?.decision_direction==='SHORT';
const cycleLabel=row=>row?.market_cycle_label||row?.trend_state_label||'无阶段';

export const frameLabel=frame=>String(frame)==='daily'?'日线':`${frame}m`;

export function buildSignalMatrix(row,{priceAction={signals:[]},execution=null}={}){
 const side=isLong(row)?'long':isShort(row)?'short':'neutral';
 const unavailable=Boolean(priceAction.unavailable);
 const signals=priceAction.signals||[];
 const longCount=signals.filter(signal=>signal.side==='long').length;
 const shortCount=signals.filter(signal=>signal.side==='short').length;
 const priceStance=unavailable?'missing':longCount===shortCount?'neutral':(side==='long'&&longCount>shortCount)||(side==='short'&&shortCount>longCount)?'support':'conflict';
 return [
  {
   id:'daily_trend',label:'日线趋势',stance:side==='neutral'?'neutral':'support',
   value:`${dir(side)} · ${cycleLabel(row)}`,
   detail:`方向分 ${row?.dir_score==null?'—':Number(row.dir_score).toFixed(0)}`,
  },
  {
   id:'price_action',label:'价格行为',stance:priceStance,
   value:unavailable?'当前周期不可用':longCount||shortCount?`多${longCount} / 空${shortCount}`:'暂无信号',
   detail:unavailable?(priceAction.reason||'分钟 K 线读取失败，未沿用日线信号'):signals.slice(-3).map(signal=>signal.label).join('、')||'当前周期没有价格行为触发',
  },
  {
   id:'structure',label:'商品结构',stance:row?.structure_confirm==='CONFLICT'?'conflict':row?.structure_confirm==='SUPPORT'?'support':'neutral',
   value:`${dir(row?.structure_direction)} · ${structure(row?.structure_confirm)}`,
   detail:'结构只解释顺逆风，不单独下结论',
  },
  {
   id:'execution',label:'盘中位置',stance:execution?execution.exec_score>=70?'support':execution.exec_score>=50?'neutral':'conflict':'missing',
   value:execution?`${execution.exec_score ?? '—'} · ${execution.stance_label||'无状态'}`:'暂无盘中位置',
   detail:execution?'基于实时价相对次日支撑/阻力':'等待盘中报价',
  },
  {
   id:'option',label:'期权动作',stance:['Call','Put'].includes(row?.option_action)?'support':'neutral',
   value:option(row?.option_action),
   detail:'期权模块仍需单张合约量仓与盈亏比过滤',
  },
 ];
}

export function buildEntryHint(row,{frame='daily',priceAction={signals:[]}}={}){
 const label=frameLabel(frame);
 if(String(frame)==='daily')return {stance:'neutral',title:'日线决策',detail:'日线负责方向和收盘决策；切到分钟周期查看盘中入场确认。'};
 if(priceAction.unavailable)return {stance:'missing',title:`${label} 入场确认不可用`,detail:priceAction.reason||'分钟 K 线暂无有效数据。'};
 const side=isLong(row)?'long':isShort(row)?'short':'neutral';
 if(side==='neutral')return {stance:'neutral',title:`${label} 等待方向`,detail:'日线方向仍是中性，分钟线只作观察，不给入场确认。'};
 const signals=priceAction.signals||[];
 const aligned=signals.filter(signal=>signal.side===side);
 const opposite=signals.filter(signal=>signal.side&&signal.side!=='neutral'&&signal.side!==side);
 const pullback=aligned.find(signal=>signal.strategy==='ema20_pullback');
 const breakout=aligned.find(signal=>signal.strategy==='breakout');
 const latest=aligned.at(-1);
 if(pullback)return {stance:'support',title:`${label} 回踩确认`,detail:`日线${dir(side)}，分钟线出现${pullback.label}：${pullback.detail}`};
 if(breakout)return {stance:'support',title:`${label} 突破确认`,detail:`日线${dir(side)}，分钟线出现${breakout.label}：${breakout.detail}`};
 if(latest)return {stance:'support',title:`${label} 顺向信号`,detail:`日线${dir(side)}，分钟线最近顺向信号：${latest.label}`};
 if(opposite.length)return {stance:'conflict',title:`${label} 暂缓入场`,detail:`日线${dir(side)}，但分钟线最近有反向价格行为，等待重新同向。`};
 return {stance:'neutral',title:`${label} 等待确认`,detail:`日线${dir(side)}，当前分钟周期还没有同向入场信号。`};
}
