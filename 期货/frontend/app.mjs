import {renderChart} from './charts.mjs';
import {api,asofQuery,mountToolbar,download} from './common.mjs';
import {enableTableSorting} from './sortable.mjs';

const $=id=>document.getElementById(id);
const app=$('app');
const state={view:'market',selected:null,candidateTab:'START',optionMode:'default',optionChain:null};
let data;

const VIEW_TITLES={
 market:['MARKET RADAR','市场雷达','今天该看什么？'],
 candidates:['CANDIDATES','候选池 / 启动榜','谁正在启动？'],
 detail:['COMMODITY DETAIL','商品详情','为什么做它？'],
 options:['OPTION CHAIN','期权 T 型报价','具体买哪张？'],
 positions:['POSITION MONITOR','持仓监控','买完以后还对不对？'],
 alerts:['STATE ALERTS','预警中心','哪个品种状态刚发生变化？'],
 review:['REVIEW & SETTINGS','复盘 / 系统设置','哪些信号有效？参数是否需要调整？']
};
const STATE_LABELS={START:'启动',PREPARE:'准备观察',TREND:'趋势持有',EXHAUST:'衰竭',WAIT:'等待'};
const DIRECTION_LABELS={LONG:'做多',SHORT:'做空',NEUTRAL:'震荡',long:'做多',short:'做空',neutral:'震荡',up:'做多',down:'做空'};
const OPTION_ACTION_LABELS={Call:'做：买认购',Put:'做：买认沽','不做':'不做'};
const MONITOR_LABELS={HEALTHY:'正常持有',WEAKENING:'正在转弱',INVALID:'逻辑失效'};
const STRUCTURE_LABELS={SUPPORT:'结构支持',CONFLICT:'结构冲突',NEUTRAL:'结构中性',UNKNOWN:'结构未知',backwardation:'近强远弱',contango:'近弱远强',flat:'平坦'};
const TERM_TIPS={
 dir:'方向分：衡量趋势方向强弱，正数偏多，负数偏空。',
 start:'启动分：衡量是否刚从准备区进入可交易启动状态。',
 rps:'相对强弱：本品种涨跌幅在全市场里的排名位置。',
 vol:'量能强度：成交量相对活跃程度，越高说明资金参与越明显。',
 oi:'持仓变化：未平仓合约数量变化，用来判断新资金是否进场。',
 option:'期权动作：方向、启动和商品结构同时通过时才提示可做；否则显示不做。',
 delta:'Delta：标的价格变动1元时，期权理论价格大约变化多少。',
 strike:'行权价：期权到期时可按该价格买入或卖出标的的价格。',
 adx:'趋势强度：衡量趋势是否有力度，不直接代表方向。'
};
const fmt=value=>value==null||Number.isNaN(value)?'—':typeof value==='number'?value.toFixed(2):String(value);
const signed=value=>value==null||Number.isNaN(value)?'—':`${value>=0?'+':''}${value.toFixed(2)}`;
const pct=value=>value==null||Number.isNaN(value)?'—':`${value>=0?'+':''}${value.toFixed(2)}%`;
const term=(label,key)=>`${label}<span class="term-tip" title="${TERM_TIPS[key]}">?</span>`;
const stateText=value=>STATE_LABELS[value]||value||'等待';
const directionText=value=>DIRECTION_LABELS[value]||value||'—';
const optionActionText=value=>OPTION_ACTION_LABELS[value]||value||'—';
const structureText=value=>STRUCTURE_LABELS[value]||value||'—';
const rows=()=>data.decisions||data.records||[];
const codeOf=row=>row.ts_code;
const isLong=row=>row.decision_side==='long'||row.decision_direction==='LONG';
const isShort=row=>row.decision_side==='short'||row.decision_direction==='SHORT';
const directionClass=row=>isLong(row)?'up':isShort(row)?'down':'muted';
const score=row=>Number(row.start_score??row.startup_score??0);
const dirScore=row=>Number(row.dir_score??0);
const stateRank={START:0,TREND:1,PREPARE:2,EXHAUST:3,WAIT:4};

function sortedRows(source=rows()){
 return [...source].sort((a,b)=>
  (stateRank[a.state_v2]??9)-(stateRank[b.state_v2]??9)||
  score(b)-score(a)||
  Math.abs(dirScore(b))-Math.abs(dirScore(a))
 );
}
function selectedRow(){
 if(state.selected)return rows().find(row=>codeOf(row)===state.selected)||sortedRows()[0];
 return sortedRows().find(row=>row.state_v2==='START')||sortedRows()[0];
}
function selectRow(row,view='detail'){
 state.selected=codeOf(row);
 setView(view);
}
function setView(view){
 state.view=view;
 document.querySelectorAll('.top-tabs button').forEach(button=>button.classList.toggle('active',button.dataset.view===view));
 render();
}
function header(){
 const [eyebrow,title,question]=VIEW_TITLES[state.view];
 return `<div class="page-hero"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${question}</p></div><div class="hero-actions"><label class="inline-label">观察窗口<select id="window"><option value="20">20交易日</option><option value="60" selected>60交易日</option><option value="120">120交易日</option><option value="250">250交易日</option></select></label><button id="export-csv">导出当前页</button></div></div>`;
}
function statCards(){
 const all=rows();
 const strongLong=all.filter(row=>dirScore(row)>=70).length;
 const strongShort=all.filter(row=>dirScore(row)<=-70).length;
 const start=all.filter(row=>row.state_v2==='START').length;
 const prepare=all.filter(row=>row.state_v2==='PREPARE').length;
 const today=all.filter(row=>['START','PREPARE'].includes(row.state_v2)).slice(0,5).length;
 return `<section class="radar-stats">
  ${[['强多品种数',strongLong,'up'],['强空品种数',strongShort,'down'],['启动信号数',start,''],['准备观察数',prepare,''],['今日新增机会',today,'']].map(([label,value,cls])=>`<div class="metric-card"><span>${label}</span><strong class="${cls}">${value}</strong></div>`).join('')}
 </section>`;
}
function decisionTable(source,limit=80,compact=false){
 const body=sortedRows(source).slice(0,limit).map(row=>`<tr data-code="${codeOf(row)}">
  <td><strong>${row.name}</strong><span class="contract">${row.main_code||codeOf(row)}</span></td>
  <td class="${directionClass(row)}">${directionText(row.decision_direction||row.trend_direction||row.direction)}</td>
  <td><span class="status-pill state-${String(row.state_v2||'wait').toLowerCase()}">${stateText(row.state_v2)}</span></td>
  <td class="${dirScore(row)>0?'up':dirScore(row)<0?'down':''}">${signed(row.dir_score)}</td>
  <td>${fmt(row.start_score??row.startup_score)}</td>
  <td>${fmt(row.price_rps??row.directional_rps20??row.rps20)}</td>
  <td>${fmt(row.vol_rps??row.volume_ratio)}</td>
  <td>${row.oi_behavior||pct(row.oi_change5)}</td>
  <td>${structureText(row.structure_confirm||row.structure)}</td>
  <td><span class="option-decision ${row.option_action==='不做'||!row.option_action?'skip':'do'}">${optionActionText(row.option_action)}</span></td>
  <td>${compact?'详情 / T型':`<button class="mini-action" data-action="detail" data-code="${codeOf(row)}">详情</button><button class="mini-action" data-action="options" data-code="${codeOf(row)}">T型</button>`}</td>
 </tr>`).join('');
 return `<div class="table-wrap"><table class="decision-table"><thead><tr><th>品种 / 主力</th><th>方向</th><th>状态</th><th>${term('方向分','dir')}</th><th>${term('启动分','start')}</th><th>${term('相对强弱','rps')}</th><th>${term('量能强度','vol')}</th><th>${term('持仓变化','oi')}</th><th>商品结构</th><th>${term('期权动作','option')}</th><th>操作</th></tr></thead><tbody>${body||'<tr><td colspan="11" class="empty">暂无匹配品种</td></tr>'}</tbody></table></div>`;
}
function renderMarket(){
 const leaders=sortedRows().slice(0,3);
 app.innerHTML=header()+statCards()+`<section class="radar-grid">
  <article class="decision-panel wide"><div class="section-heading"><div><h2>机会雷达</h2><div class="muted small">默认排序：先看启动状态，再看启动分，最后看方向强弱。</div></div></div>${decisionTable(rows())}</article>
  <aside class="decision-panel"><h2>当前优先观察</h2><div class="focus-list">${leaders.map(row=>`<button data-code="${codeOf(row)}" data-view-target="detail"><strong>${row.name}</strong><span>${directionText(row.decision_direction)} · ${stateText(row.state_v2)} · 启动分 ${fmt(row.start_score??row.startup_score)}</span></button>`).join('')}</div></aside>
 </section><section class="chart-section decision-panel"><div class="section-heading"><h2>大类等权走势</h2><span class="muted small">点击表格进入商品详情</span></div><div id="chart"></div></section>`;
 renderSectorChart();
}
function renderCandidates(){
 const tabs=['PREPARE','START','TREND'];
 const source=rows().filter(row=>row.state_v2===state.candidateTab);
 app.innerHTML=header()+`<section class="decision-panel"><div class="candidate-tabs">${tabs.map(tab=>`<button data-candidate-tab="${tab}" class="${state.candidateTab===tab?'active':''}">${stateText(tab)}<span>${rows().filter(row=>row.state_v2===tab).length}</span></button>`).join('')}</div>${decisionTable(source)}</section>`;
}
function metricBlocks(row){
 const items=[['方向结论',directionText(row.decision_direction||row.trend_direction)],['状态',stateText(row.state_v2)],['方向分',signed(row.dir_score)],['启动分',fmt(row.start_score??row.startup_score)],['相对强弱',fmt(row.price_rps??row.directional_rps20??row.rps20)],['量能强度',fmt(row.vol_rps??row.volume_ratio)],['持仓变化',row.oi_behavior||pct(row.oi_change5)],['商品结构',structureText(row.structure_confirm||row.structure)],['期权动作',optionActionText(row.option_action)],['趋势强度',fmt(row.adx)]];
 return `<div class="detail-metrics">${items.map(([label,value])=>`<div><span>${label}</span><strong>${value||'—'}</strong></div>`).join('')}</div>`;
}
function renderDetail(){
 const row=selectedRow();
 app.innerHTML=header()+`<section class="detail-layout">
  <article class="decision-panel conclusion-panel"><div class="section-heading"><div><h2>${row.name} · ${codeOf(row)}</h2><div class="muted small">${row.main_code||'—'} / ${row.secondary_code||'—'}</div></div><button data-jump-options="${codeOf(row)}">查看T型报价</button></div>${metricBlocks(row)}<p class="phase-rationale">${row.phase_reason||'暂无阶段说明。'} V2按方向闸门、启动证据、商品结构和期权表达顺序给出当前动作。</p></article>
  <article class="decision-panel chart-card"><div class="section-heading"><h2>K线与多周期</h2><div class="timeframe-tabs"><span>D1</span><span>60m</span><span>15m</span><span>5m</span></div></div><div id="single-chart"></div></article>
  <article class="decision-panel"><h2>趋势 + 资金</h2>${metricBlocks(row)}</article>
  <article class="decision-panel"><h2>商品结构</h2><div class="structure-grid"><div><span>期限结构</span><strong>${structureText(row.structure)}</strong></div><div><span>结构确认</span><strong>${structureText(row.structure_confirm)}</strong></div><div><span>价差变化</span><strong>${pct(row.spread_change5)}</strong></div><div><span>持有成本变化</span><strong>${pct(row.carry_change5)}</strong></div></div></article>
 </section>`;
 renderSingleChart(row);
}
function optionTargetSide(row){return isShort(row)?'P':'C'}
function optionModeRange(){
 if(state.optionMode==='steady')return [.4,.55,'稳健'];
 if(state.optionMode==='aggressive')return [.15,.3,'激进'];
 return [.25,.4,'默认'];
}
async function ensureOptions(){
 if(state.optionChain)return state.optionChain;
 try{state.optionChain=await api('/api/options'+(asofQuery()?'?'+asofQuery():''));}
 catch(error){state.optionChain={records:[],status:error.message};}
 return state.optionChain;
}
function optionRows(row,chain){
 const side=optionTargetSide(row);
 const [min,max]=optionModeRange();
 const candidates=(chain.records||[]).filter(item=>item.main_code===codeOf(row)||item.underlying_code===row.main_code||item.underlying_code===row.secondary_code);
 const byStrike=new Map();
 candidates.forEach(item=>{
  const key=String(item.exercise_price);
  byStrike.set(key,{...(byStrike.get(key)||{}),[item.call_put]:item});
 });
 if(!byStrike.size)return `<tr><td colspan="7" class="empty">${chain.status||'暂无该品种期权链'}</td></tr>`;
 return [...byStrike.entries()].sort((a,b)=>Number(a[0])-Number(b[0])).map(([strike,pair])=>{
  const call=pair.C,put=pair.P;
  const best=item=>item&&Math.abs(Math.abs(item.delta||0)-((min+max)/2))<=(max-min)/2;
  const callHot=side==='C'&&best(call),putHot=side==='P'&&best(put);
  return `<tr>
   <td class="${side==='C'?'option-aligned':'option-faded'}">${call?optionCell(call,callHot):'—'}</td>
   <td class="${side==='C'?'option-aligned':'option-faded'}">${call?fmt(call.delta):'—'}</td>
   <td class="strike-cell">${fmt(Number(strike))}</td>
   <td class="${side==='P'?'option-aligned':'option-faded'}">${put?fmt(put.delta):'—'}</td>
   <td class="${side==='P'?'option-aligned':'option-faded'}">${put?optionCell(put,putHot):'—'}</td>
  </tr>`;
 }).join('');
}
function optionCell(item,hot){
 const score=item.tradability?.score;
 return `<button class="option-contract ${hot?'recommended':''}" title="${item.ts_code}">${item.ts_code}<span>权利金 ${fmt(item.premium)} · 分 ${score??'—'}</span></button>`;
}
async function renderOptions(){
 const row=selectedRow();
 app.innerHTML=header()+`<section class="decision-panel"><div class="section-heading"><div><h2>${row.name} · ${directionText(row.decision_direction)} T型报价</h2><div class="muted small">方向侧高亮，反向侧灰显；合约筛选按敏感度区间执行。</div></div><div class="mode-tabs"><button data-option-mode="steady" class="${state.optionMode==='steady'?'active':''}">稳健 .40-.55</button><button data-option-mode="default" class="${state.optionMode==='default'?'active':''}">默认 .25-.40</button><button data-option-mode="aggressive" class="${state.optionMode==='aggressive'?'active':''}">激进 .15-.30</button></div></div><div class="loading-panel">正在读取期权链…</div></section>`;
 const chain=await ensureOptions();
 if(state.view!=='options')return;
 app.innerHTML=header()+`<section class="decision-panel"><div class="section-heading"><div><h2>${row.name} · ${directionText(row.decision_direction)} T型报价</h2><div class="muted small">${chain.status||'期权链'} · 当前模式 ${optionModeRange()[2]}</div></div><div class="mode-tabs"><button data-option-mode="steady" class="${state.optionMode==='steady'?'active':''}">稳健 .40-.55</button><button data-option-mode="default" class="${state.optionMode==='default'?'active':''}">默认 .25-.40</button><button data-option-mode="aggressive" class="${state.optionMode==='aggressive'?'active':''}">激进 .15-.30</button></div></div><div class="table-wrap t-chain"><table><thead><tr><th>认购</th><th>${term('敏感度','delta')}</th><th>${term('行权价','strike')}</th><th>${term('敏感度','delta')}</th><th>认沽</th></tr></thead><tbody>${optionRows(row,chain)}</tbody></table></div></section>`;
}
function monitorState(row){
 if(row.state_v2==='START'||row.state_v2==='TREND')return 'HEALTHY';
 if(row.state_v2==='PREPARE'||row.state_v2==='EXHAUST')return 'WEAKENING';
 return 'INVALID';
}
function renderPositions(){
 const active=sortedRows(rows().filter(row=>['START','TREND','PREPARE','EXHAUST'].includes(row.state_v2))).slice(0,24);
 app.innerHTML=header()+`<section class="decision-panel"><div class="section-heading"><h2>持仓状态只保留三类</h2><span class="muted small">正常持有 / 正在转弱 / 逻辑失效</span></div><div class="position-grid">${active.map(row=>`<button class="position-card ${monitorState(row).toLowerCase()}" data-code="${codeOf(row)}" data-view-target="detail"><span>${MONITOR_LABELS[monitorState(row)]}</span><strong>${row.name}</strong><small>${directionText(row.decision_direction)} · ${stateText(row.state_v2)} · 方向分 ${signed(row.dir_score)}</small></button>`).join('')}</div></section>`;
}
function renderAlerts(){
 const alerts=sortedRows(rows().filter(row=>['START','TREND','EXHAUST'].includes(row.state_v2))).slice(0,40);
 app.innerHTML=header()+`<section class="decision-panel"><div class="timeline">${alerts.map(row=>`<button class="alert-row" data-code="${codeOf(row)}" data-view-target="detail"><span class="status-pill state-${String(row.state_v2).toLowerCase()}">${stateText(row.state_v2)}</span><strong>${row.name}</strong><em>${row.state_v2==='START'?'准备观察 → 启动':row.state_v2==='TREND'?'启动 → 趋势持有':'趋势持有 → 衰竭'}</em><small>方向分 ${signed(row.dir_score)} · 启动分 ${fmt(row.start_score??row.startup_score)}</small></button>`).join('')}</div></section>`;
}
function renderReview(){
 const all=rows(),start=all.filter(row=>row.state_v2==='START'),trend=all.filter(row=>row.state_v2==='TREND');
 app.innerHTML=header()+`<section class="review-grid">
  <article class="decision-panel"><h2>信号统计</h2><div class="review-stats"><div><span>启动平均分</span><strong>${fmt(start.reduce((s,r)=>s+score(r),0)/(start.length||1))}</strong></div><div><span>趋势持有数量</span><strong>${trend.length}</strong></div><div><span>结构支持</span><strong>${all.filter(r=>r.structure_confirm==='SUPPORT').length}</strong></div></div></article>
  <article class="decision-panel"><h2>关键参数</h2><div class="settings-list"><label>强方向阈值<input type="number" value="70"></label><label>启动观察阈值<input type="number" value="60"></label><label>结构冲突处理<select><option>禁止开仓</option><option>降级观察</option></select></label></div></article>
  <article class="decision-panel wide"><h2>复盘样本</h2>${decisionTable([...start,...trend],20,true)}</article>
 </section>`;
}
function renderSectorChart(){
 if(!data.sectors||!data.curves)return;
 const series=Object.keys(data.sectors).map(name=>({id:name,label:name,values:sectorSeries(name)}));
 renderChart($('chart'),series,{window:Number($('window')?.value||60),title:'各大类等权走势'});
}
function sectorSeries(sector){
 const members=data.sectors[sector].members.filter(code=>data.curves[code]);
 const points=members.map(code=>data.curves[code].slice(-61));
 if(!points.length)return [];
 return points[0].map((point,index)=>[point[0],points.reduce((sum,values)=>sum+values[index][1]/values[0][1]*100,0)/points.length]);
}
function renderSingleChart(row){
 if(!data.curves?.[codeOf(row)])return;
 const values=data.curves[codeOf(row)];
 const moving=data.moving?.[codeOf(row)]||{};
 renderChart($('single-chart'),[{id:codeOf(row),label:row.name,values},...['ma20','ma60','ma120'].filter(key=>moving[key]).map(key=>({id:key,label:key.toUpperCase(),values:values.map((point,index)=>[point[0],moving[key][index]])}))],{window:Number($('window')?.value||60),price:true,title:`${row.name}复权收盘与均线`});
}
function render(){
 if(!data)return;
 if(state.view==='market')renderMarket();
 if(state.view==='candidates')renderCandidates();
 if(state.view==='detail')renderDetail();
 if(state.view==='options'){renderOptions().then(wireView);return}
 if(state.view==='positions')renderPositions();
 if(state.view==='alerts')renderAlerts();
 if(state.view==='review')renderReview();
 wireView();
}
function wireView(){
 $('window')?.addEventListener('change',()=>render());
 $('export-csv')?.addEventListener('click',()=>download(`趋势决策-${data.asof}-${state.view}.csv`,csvFor(sortedRows()),'text/csv;charset=utf-8'));
 document.querySelectorAll('[data-code]').forEach(node=>node.addEventListener('click',event=>{
  const action=event.target.closest('[data-action]')?.dataset.action;
  const row=rows().find(item=>codeOf(item)===node.dataset.code);
  if(!row)return;
  selectRow(row,action==='options'?'options':node.dataset.viewTarget||'detail');
 }));
 document.querySelectorAll('[data-candidate-tab]').forEach(button=>button.addEventListener('click',()=>{state.candidateTab=button.dataset.candidateTab;renderCandidates();wireView();}));
 document.querySelectorAll('[data-option-mode]').forEach(button=>button.addEventListener('click',()=>{state.optionMode=button.dataset.optionMode;renderOptions().then(wireView);}));
 document.querySelectorAll('[data-jump-options]').forEach(button=>button.addEventListener('click',()=>setView('options')));
 document.querySelectorAll('.decision-table').forEach(enableTableSorting);
}
function csvFor(source){
 const fields=['ts_code','name','sector','main_code','decision_direction','state_v2','dir_score','start_score','price_rps','vol_rps','oi_change5','structure_confirm','option_action'];
 return '\ufeff'+[fields.join(','),...source.map(row=>fields.map(key=>`"${String(row[key]??'').replaceAll('"','""')}"`).join(','))].join('\r\n');
}
async function init(){
 try{
  data=await api('/api/data'+(asofQuery()?'?'+asofQuery():''));
  $('data-date').textContent=`收盘日 ${data.asof.slice(0,4)}.${data.asof.slice(4,6)}.${data.asof.slice(6)} · ${rows().length}条决策`;
  document.querySelectorAll('.top-tabs button').forEach(button=>button.addEventListener('click',()=>setView(button.dataset.view)));
  await mountToolbar().catch(()=>{});
  render();
 }catch(error){
  $('error').hidden=false;
  $('error').textContent=error.message;
  app.innerHTML='<section class="loading-panel">数据读取失败</section>';
 }
}
init();
