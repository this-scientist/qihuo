const escapeHtml=value=>String(value??'')
 .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
 .replaceAll('"','&quot;').replaceAll("'",'&#39;');

const count=value=>value==null||Number.isNaN(Number(value))?'—':
 Number(value).toLocaleString('zh-CN',{maximumFractionDigits:0});
const signed=value=>value==null||Number.isNaN(Number(value))?'—':
 `${Number(value)>=0?'+':''}${count(value)}`;
const percent=value=>value==null||Number.isNaN(Number(value))?'—':
 `${(Number(value)*100).toFixed(2)}%`;

const scopeNote='<p class="holding-note">席位数据为交易所公开排名的局部口径；全市场多空总量相等；不参与系统评分。</p>';


export function holdingExplanation(value){
 if(!['available','numeric_only'].includes(value?.holding_status))return '';
 const net=Number(value.top20_net);
 if(!Number.isFinite(net))return '前20净仓数据不完整。';
 const side=net>0?'净多':net<0?'净空':'多空持平';
 const change=Number(value.top20_net_change);
 if(value.top20_net_change==null||!Number.isFinite(change))return `前20席位${side}，当日变化数据不完整。`;
 let movement='净仓未变';
 if(net>=0&&change>0)movement='净多增加';
 else if(net>=0&&change<0)movement='净多减少';
 else if(net<0&&change<0)movement='净空增加';
 else if(net<0&&change>0)movement='净空减少';
 return `前20席位${side}，当日${movement}。`;
}


function metric(label,value){
 return `<div><span>${label}</span><strong>${value}</strong></div>`;
}


function brokerList(title,rows){
 const items=(rows||[]).map(row=>`<li><span>${escapeHtml(row.broker)}</span><strong>${count(row.holding)} <small>${signed(row.change)}</small></strong></li>`).join('');
 return `<div><h4>${title}</h4><ol>${items}</ol></div>`;
}


export function renderHoldings(value){
 const status=value?.holding_status||'unavailable';
 if(!['available','numeric_only'].includes(status)){
  const reason=value?.holding_reason||'该主力合约没有可用席位排名';
  return `<section class="holding-panel holding-${status==='invalid'?'invalid':'unavailable'}"><p class="holding-state">${escapeHtml(reason)}</p>${scopeNote}</section>`;
 }
 const metrics=[
  metric('前20多仓',count(value.top20_long)),
  metric('前20空仓',count(value.top20_short)),
  metric('前20净仓',signed(value.top20_net)),
  metric('多仓变化',signed(value.top20_long_change)),
  metric('空仓变化',signed(value.top20_short_change)),
  metric('净仓变化',signed(value.top20_net_change)),
  metric('多仓集中度',percent(value.top20_long_concentration)),
  metric('空仓集中度',percent(value.top20_short_concentration)),
 ].join('');
 const brokers=status==='available'?`<div class="holding-brokers">${brokerList('多头前五',value.top_long_brokers)}${brokerList('空头前五',value.top_short_brokers)}</div>`:'';
 const warning=status==='numeric_only'?`<p class="holding-warning">${escapeHtml(value.holding_reason||'席位名称源数据异常')}</p>`:'';
 return `<section class="holding-panel"><div class="holding-heading"><h3>席位持仓</h3><span>${escapeHtml(value.holding_contract||'—')} · ${escapeHtml(value.holding_trade_date||'—')}</span></div><div class="holding-summary">${metrics}</div><p class="holding-explanation">${escapeHtml(holdingExplanation(value))}</p>${warning}${brokers}${scopeNote}</section>`;
}
