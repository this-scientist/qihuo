import {renderChart,renderCandlestickChart} from './charts.mjs';
import {api,asofQuery,mountToolbar,download} from './common.mjs';
import {enableTableSorting} from './sortable.mjs';

const $=id=>document.getElementById(id);
const app=$('app');
const state={view:'market',selected:null,candidateTab:'START',optionMode:'default',optionChain:null,search:'',sector:'all',side:'all',stage:'all',quotes:null,quoteMeta:null,execution:null};
let data;

const VIEW_TITLES={
 market:['COMMODITIES','商品总览',''],
 candidates:['CANDIDATES','候选池 / 启动榜','谁正在启动？'],
 detail:['COMMODITY DETAIL','商品详情','为什么做它？'],
 options:['OPTION CHAIN','期权 T 型报价','具体买哪张？'],
 positions:['POSITION MONITOR','持仓监控','买完以后还对不对？'],
 alerts:['STATE ALERTS','预警中心','哪个品种状态刚发生变化？'],
 review:['REVIEW & SETTINGS','复盘 / 系统设置','哪些信号有效？参数是否需要调整？']
};
const STATE_LABELS={START:'启动',PREPARE:'准备观察',TREND:'趋势持有',EXHAUST:'衰竭',WAIT:'等待'};
const DIRECTION_LABELS={LONG:'偏多',SHORT:'偏空',NEUTRAL:'中性',long:'偏多',short:'偏空',neutral:'中性',up:'偏多',down:'偏空',多:'偏多',空:'偏空',unknown:'数据不足'};
const SECTOR_DIRECTION_LABELS={long:'大类偏多',short:'大类偏空',flat:'大类震荡',unknown:''};
const OPTION_ACTION_LABELS={Call:'做：买认购',Put:'做：买认沽','不做':'不做'};
const OPTION_GATE_LABELS={ALLOW:'允许新仓',WATCH:'观察小仓',CONDITIONAL:'等待回调',BLOCK:'不新开仓'};
const MONITOR_LABELS={HEALTHY:'正常持有',WEAKENING:'正在转弱',INVALID:'逻辑失效'};
const STRUCTURE_LABELS={SUPPORT:'同向',CONFLICT:'背离',NEUTRAL:'中性',UNKNOWN:'数据不足',Backwardation:'近强远弱',Contango:'近弱远强',backwardation:'近强远弱',contango:'近弱远强',flat:'平坦'};
const TERM_TIPS={
 dir:'价格趋势分 -100~100：价格/均线40、波动归一动量35、DI/ADX25。≥25偏多，≤-25偏空；规则分不是胜率。',
 start:'启动分：衡量是否刚从准备区进入可交易启动状态。',
 rps:'相对强弱：本品种涨跌幅在全市场里的排名位置。',
 vol:'量能强度：成交量相对活跃程度，越高说明资金参与越明显。',
 oi:'当前固定主力和次主力合约合计OI变化；不是全市场持仓，也不能据此识别净多或净空。',
 day:'主力当日收盘 / 昨日结算 - 1；收盘快照，非实时涨幅。',
 accel:'RPS20今日值减去5个交易日前的值，单位为百分点；是五日变化，不是数学二阶加速度。',
 burst:'标的爆发指数0~100：突破25、方向RPS变化20、ADX增量20、ATR扩张15、量比10、OI增幅10。缺失不补分，不是胜率或期权收益预测。',
 option:'期权动作：方向、启动和商品结构同时通过时才提示可做；否则显示不做。',
 trend:'趋势状态：T0无趋势、T1酝酿、T2启动、T3加速、T4延续、T5衰竭。',
 transition:'状态迁移：用当前证据近似标记从观察到启动、从启动到加速、或从延续到衰竭的变化。',
 delta:'Delta：标的价格变动1元时，期权理论价格大约变化多少。',
 strike:'行权价：期权到期时可按该价格买入或卖出标的的价格。',
 adx:'趋势强度：衡量趋势是否有力度，不直接代表方向。',
 sector:'大类内相对强度 -100~100：先按大类等权指数的MA20五日斜率定大类方向，再用品种相对该大类的20日超额收益在类内排分位，并按大类方向翻转。与大类方向相反的品种取负（-100最强反向、+100最强顺势），所以整列从-100单调到+100。类内成员少于2个时分位无意义。',
 quote:'盘中最新价与买卖一档，来自新浪公开网页行情（非官方接口）。注意口径：这里的涨跌是「最新价 / 本交易日昨结算」，而左侧「当日%」是最近一个收盘日的涨跌，两者不是同一天，不要直接相减。报价只作盘中参考，不参与任何评分，也不改变收盘口径的决策与快照。',
 exec:'盘中可执行性 0~100 = 位置分×0.6 + 日线方向分×0.4。位置分看实时价落在「次日支撑~阻力」箱体的哪里：顺向近端（回调/反弹到位）90 分最优，刚破远端 75 分次之，区间中部 50，接近远端 35，逆势越界 30，反向破位 8。方向分按日线状态取值（START100/TREND85/PREPARE60/EXHAUST30/WAIT20）。按此列降序即实时排名；日线无方向的品种不参与排名。这是规则分，不是胜率，也未回测。'
};
const fmt=value=>value==null||Number.isNaN(value)?'—':typeof value==='number'?value.toFixed(2):String(value);
const signed=value=>value==null||Number.isNaN(value)?'—':`${value>=0?'+':''}${value.toFixed(2)}`;
const pct=value=>value==null||Number.isNaN(value)?'—':`${value>=0?'+':''}${value.toFixed(2)}%`;
const count=value=>value==null?'—':Number(value).toLocaleString('zh-CN',{maximumFractionDigits:0});
const tone=value=>value>0?'up':value<0?'down':'muted';
const sectorClass=row=>row.sector_counter?'sector-counter':tone(row.sector_strength);
const sectorNote=row=>row.sector_members>1?`第${row.sector_rank}/${row.sector_members}`:(row.sector_members?'类内仅1个':'');
const price=value=>value==null||Number.isNaN(value)?'—':Number(value).toLocaleString('zh-CN',{maximumFractionDigits:4});
const contractOf=row=>row.main_code||codeOf(row);
const quoteOf=row=>state.quotes?.[contractOf(row)]||null;
const quoteStale=quote=>quote&&quote.age_seconds!=null&&quote.age_seconds>300;
function quoteCell(row){
 const contract=contractOf(row);
 if(!state.quotes)return `<td class="quote-cell muted" data-quote="${contract}">…</td>`;
 const quote=quoteOf(row);
 if(!quote)return `<td class="quote-cell muted" data-quote="${contract}">—<span class="contract">无盘中报价</span></td>`;
 const note=[`${fmt(quote.time)}抓取`,`昨结 ${price(quote.pre_settle)}`,
  quote.spread==null?'':'价差 '+price(quote.spread),quoteStale(quote)?'报价超过5分钟未更新':''].filter(Boolean).join(' · ');
 return `<td class="quote-cell ${tone(quote.change_pct)}" data-quote="${contract}" title="${note}">`
  +`${price(quote.last)}<span class="contract">${pct(quote.change_pct)} 买${price(quote.bid)}/卖${price(quote.ask)}</span></td>`;
}
function quoteMetrics(row){
 const quote=quoteOf(row);
 if(!quote)return '<div><span>盘中报价</span><strong>—</strong></div>';
 return `<div><span>盘中最新价（${fmt(quote.time)}）</span><strong>${price(quote.last)}</strong></div>`
  +`<div><span>盘中涨跌（对昨结 ${price(quote.pre_settle)}）</span><strong>${pct(quote.change_pct)}</strong></div>`
  +`<div><span>买一 / 卖一</span><strong>${price(quote.bid)} / ${price(quote.ask)}</strong></div>`
  +`<div><span>盘口价差${quoteStale(quote)?'（报价已过期）':''}</span><strong>${price(quote.spread)}</strong></div>`;
}
const execOf=row=>state.execution?.[codeOf(row)]||null;
const execTone=item=>['broken','crossed','runaway'].includes(item.stance)?'sector-counter'
 :item.exec_score>=75?'exec-strong':item.exec_score>=50?'exec-mid':'exec-weak';
const execNote=item=>[`最新 ${price(item.last)}`,
 `支撑 ${price(item.support)} / 阻力 ${price(item.resistance)}`,
 `突破 ${price(item.breakout)} / 反转 ${price(item.reversal)}`,
 item.progress==null?'':`推进度 ${item.progress.toFixed(2)}（0=顺着方向的近端价位，1=远端）`,
 `位置分 ${item.position_score==null?'—':item.position_score} · 方向分 ${item.direction_score}（START100/TREND85/PREPARE60/EXHAUST30/WAIT20）· 合成权重 位置0.6／方向0.4`,
 '规则分，不是胜率，也未回测'
].filter(Boolean).join(' · ');
function execCell(row){
 const code=codeOf(row);
 if(!state.execution)return `<td class="exec-cell muted" data-exec="${code}">…</td>`;
 const item=execOf(row);
 if(!item||item.exec_score==null)return `<td class="exec-cell muted" data-exec="${code}" title="${item?execNote(item):''}">—`
  +`<span class="contract">${item&&item.stance_label&&item.stance_label!=='无价位'?item.stance_label:'无日线方向'}</span></td>`;
 return `<td class="exec-cell ${execTone(item)}" data-exec="${code}" data-sort="${item.exec_score}" title="${execNote(item)}">`
  +`<strong>${item.exec_score}</strong><span class="contract">${item.stance_label} ${DIRECTION_LABELS[item.side]||item.side}</span></td>`;
}
function execMetrics(row){
 const item=execOf(row);
 if(!item)return '<div><span>盘中可执行性</span><strong>—</strong></div>';
 const state=item.exec_score==null?'不参与排名（无日线方向）':`${item.stance_label} ${DIRECTION_LABELS[item.side]||''}`;
 return `<div><span>盘中可执行性（${state}）</span><strong>${item.exec_score==null?'—':item.exec_score}</strong></div>`
  +`<div><span>次日支撑 / 阻力</span><strong>${price(item.support)} / ${price(item.resistance)}</strong></div>`
  +`<div><span>次日突破 / 反转</span><strong>${price(item.breakout)} / ${price(item.reversal)}</strong></div>`
  +`<div><span>推进度（0=近端，1=远端）</span><strong>${item.progress==null?'—':item.progress.toFixed(2)}</strong></div>`;
}
const term=(label,key)=>`${label}<span class="term-tip" title="${TERM_TIPS[key]}">?</span>`;
const stateText=value=>STATE_LABELS[value]||value||'等待';
const directionText=value=>DIRECTION_LABELS[value]||value||'—';
const optionActionText=value=>OPTION_ACTION_LABELS[value]||value||'—';
const optionGateText=value=>OPTION_GATE_LABELS[value]||value||'—';
const structureText=value=>STRUCTURE_LABELS[value]||value||'—';
const signalClass=row=>row.signal_side==='long'?'up':row.signal_side==='short'?'down':'muted';
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
 const coverage=data?.quality?.coverage_warning;
 const banner=coverage?`<div class="notice coverage-warning" role="alert">⚠ 数据不完整：${coverage.trade_date} 未采集 ${coverage.missing_exchanges.join('、')}。${coverage.note}</div>`:'';
 return `${banner}<div class="page-hero"><div><h1>${title}</h1></div><div class="hero-actions"><label class="inline-label">观察窗口<select id="window"><option value="20">20交易日</option><option value="60" selected>60交易日</option><option value="120">120交易日</option><option value="250">250交易日</option></select></label><button id="export-csv">导出数据</button></div></div>`;
}
function statCards(){
 const all=rows();
 const strongLong=all.filter(row=>isLong(row)).length;
 const strongShort=all.filter(row=>isShort(row)).length;
 const start=all.filter(row=>row.state_v2==='START').length;
 const prepare=all.filter(row=>row.state_v2==='PREPARE').length;
 const today=all.filter(row=>row.structure_confirm==='CONFLICT').length;
 return `<section class="radar-stats">
  ${[['趋势偏多',strongLong,'up'],['趋势偏空',strongShort,'down'],['启动信号',start,''],['准备观察',prepare,''],['趋势 / 结构背离',today,'']].map(([label,value,cls])=>`<div class="metric-card"><span>${label}</span><strong class="${cls}">${value}</strong></div>`).join('')}
 </section>`;
}
function decisionTable(source,limit=80,compact=false){
 const body=sortedRows(source).slice(0,limit).map(row=>`<tr data-code="${codeOf(row)}">
  <td><strong>${row.name}</strong><span class="contract">${row.main_code||codeOf(row)}</span></td>
  <td class="${directionClass(row)}">${directionText(row.decision_side)}</td>
  <td class="${row.structure_direction==='long'?'up':row.structure_direction==='short'?'down':'muted'}">${directionText(row.structure_direction)}<span class="contract">${structureText(row.structure_confirm)}</span></td>
  <td class="${tone(row.day_change)}">${pct(row.day_change)}</td>
  ${quoteCell(row)}
  ${execCell(row)}
  <td class="${tone(row.return5)}">${pct(row.return5)}</td>
  <td class="${tone(row.return20)}">${pct(row.return20)}</td>
  <td>${fmt(row.rps5)}</td><td>${fmt(row.rps20)}</td>
  <td class="${tone(row.rps_accel)}">${signed(row.rps_accel)}</td>
  <td class="${sectorClass(row)}" data-sort="${row.sector_strength??''}" title="${row.sector_counter?'该品种方向与大类方向相反：负分代表反向强度，越负越强':''}">${signed(row.sector_strength)}<span class="contract">${sectorNote(row)}</span></td>
  <td class="${dirScore(row)>0?'up':dirScore(row)<0?'down':''}">${signed(row.dir_score)}</td>
  <td>${row.trend_state_label||'—'}</td>
  <td class="${signalClass(row)}">${row.signal_label||'—'}<span class="contract">${row.today_support!=null&&row.today_resistance!=null?`支 ${fmt(row.today_support)} / 阻 ${fmt(row.today_resistance)}`:'—'}</span></td>
  <td title="因子覆盖 ${fmt(row.burst_coverage)}%">${fmt(row.burst_score)}</td>
  <td>${count(row.main_oi)}</td><td>${count(row.pair_oi)}</td>
  <td class="${tone(row.oi_change5)}">${pct(row.oi_change5)}</td>
  <td>${signed(row.spread)}<span class="contract">5日 ${signed(row.spread_change5)}</span></td>
  <td>${structureText(row.structure)}<span class="contract">Carry ${pct(row.carry_annualized)}</span></td>
  <td>${row.sector||'—'}<span class="contract">${SECTOR_DIRECTION_LABELS[row.sector_direction]||''}</span></td>
  <td>${signed(row.structure_score)}<span class="contract">覆盖 ${fmt(row.structure_evidence?.group_coverage)}%</span></td>
  <td><button class="mini-action" data-action="options" data-code="${codeOf(row)}">T型</button></td>
 </tr>`).join('');
 return `<div class="table-wrap overview-table"><table class="decision-table"><thead><tr><th>品种 / 主力</th><th>趋势方向</th><th>结构方向</th><th>${term('当日%','day')}</th><th>${term('实时价','quote')}</th><th>${term('可执行性','exec')}</th><th>5日%</th><th>20日%</th><th>${term('RPS5','rps')}</th><th>${term('RPS20','rps')}</th><th>${term('RPS加速度','accel')}</th><th>${term('大类内强度','sector')}</th><th>${term('趋势得分','dir')}</th><th>${term('趋势阶段','trend')}</th><th>技术信号</th><th>${term('爆发指数','burst')}</th><th>主力持仓</th><th>主次OI</th><th>${term('OI 5日%','oi')}</th><th>跨期价差</th><th>期限结构</th><th>大类</th><th>结构得分</th><th>期权</th></tr></thead><tbody>${body||'<tr><td colspan="24" class="empty">暂无匹配品种</td></tr>'}</tbody></table></div>`;
}
function filteredRows(){return rows().filter(row=>(state.sector==='all'||row.sector===state.sector)&&(state.side==='all'||row.decision_side===state.side)&&(state.stage==='all'||row.state_v2===state.stage)&&`${row.name} ${row.ts_code} ${row.main_code}`.toLowerCase().includes(state.search.toLowerCase()))}
function renderMarket(){
 app.innerHTML=header()+statCards()+`<section class="commodity-section"><div class="commodity-filters"><input id="commodity-search" type="search" aria-label="搜索商品" placeholder="商品 / 合约"><select id="sector-filter" aria-label="所属大类"><option value="all">全部大类</option>${[...new Set(rows().map(r=>r.sector))].map(s=>`<option>${s}</option>`).join('')}</select><select id="side-filter" aria-label="趋势方向"><option value="all">全部方向</option><option value="long">偏多</option><option value="short">偏空</option><option value="neutral">中性</option></select><select id="stage-filter" aria-label="趋势阶段"><option value="all">全部阶段</option>${Object.entries(STATE_LABELS).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select><span id="result-count" class="muted small">${filteredRows().length} 个品种</span><span id="quote-status" class="muted small"></span></div><div id="commodity-results">${decisionTable(filteredRows())}</div></section><section class="chart-section decision-panel"><div class="section-heading"><h2>大类等权走势</h2></div><div id="chart"></div></section>`;
 $('commodity-search').value=state.search;$('sector-filter').value=state.sector;$('side-filter').value=state.side;$('stage-filter').value=state.stage;
 renderSectorChart();
}
function renderCandidates(){
 const tabs=['PREPARE','START','TREND'];
 const source=rows().filter(row=>row.state_v2===state.candidateTab);
 app.innerHTML=header()+`<section class="decision-panel"><div class="candidate-tabs">${tabs.map(tab=>`<button data-candidate-tab="${tab}" class="${state.candidateTab===tab?'active':''}">${stateText(tab)}<span>${rows().filter(row=>row.state_v2===tab).length}</span></button>`).join('')}</div>${decisionTable(source)}</section>`;
}
function metricBlocks(row){
 const items=[['趋势方向',directionText(row.decision_side)],['技术信号',row.signal_label],['今日支撑 / 阻力',`${fmt(row.today_support)} / ${fmt(row.today_resistance)}`],['明日突破 / 反转',`${fmt(row.tomorrow_breakout)} / ${fmt(row.tomorrow_reversal)}`],['商品结构',directionText(row.structure_direction)],['趋势 / 结构',structureText(row.structure_confirm)],['所属大类',row.sector],['趋势得分',signed(row.dir_score)],['趋势阶段',row.trend_state_label],['当日涨幅（昨结）',pct(row.day_change)],['1日涨幅（昨收）',pct(row.return1)],['5日涨幅',pct(row.return5)],['20日涨幅',pct(row.return20)],['RPS5',fmt(row.rps5)],['RPS20',fmt(row.rps20)],['RPS加速度（百分点）',signed(row.rps_accel)],['大类内相对强度',signed(row.sector_strength)],['爆发指数',fmt(row.burst_score)],['爆发因子覆盖',`${fmt(row.burst_coverage)}%`],['ADX',fmt(row.adx)]];
 return `<div class="detail-metrics">${items.map(([label,value])=>`<div><span>${label}</span><strong>${value||'—'}</strong></div>`).join('')}<div class="quote-metrics" data-intraday="${contractOf(row)}">${quoteMetrics(row)}${execMetrics(row)}</div></div>`;
}
function renderDetail(){
 const row=selectedRow();
 if(!row){app.innerHTML=header()+'<p class="empty">当前日期暂无商品数据</p>';return}
 app.innerHTML=header()+`<section class="detail-layout">
  <article class="decision-panel conclusion-panel"><div class="section-heading"><div><h2>${row.name} · ${codeOf(row)}</h2><div class="muted small">${row.main_code||'—'} / ${row.secondary_code||'—'}</div></div><button data-jump-options="${codeOf(row)}">查看T型报价</button></div>${metricBlocks(row)}<p class="phase-rationale">${row.trend_state_reason||'暂无阶段说明。'}</p><div class="factor-contributions">${Object.entries(row.trend_components||{}).map(([key,value])=>`<span>${{price:'价格 / 均线',momentum:'绝对动量',di:'DI / ADX'}[key]} <strong class="${tone(value)}">${signed(value)}</strong></span>`).join('')}</div></article>
  <article class="decision-panel chart-card"><div class="section-heading"><h2>日线K线与均线</h2></div><div id="single-chart"></div></article>
  <article class="decision-panel"><h2>量仓</h2><div class="structure-grid">${[['主力OI（手）',count(row.main_oi)],['次主力OI（手）',count(row.secondary_oi)],['主次合计OI（手）',count(row.pair_oi)],['固定月对OI 5日',pct(row.oi_change5)],['固定月对OI 20日',pct(row.oi_change20)],['成交量比',fmt(row.volume_ratio)],['量价表现',row.structure_evidence?.oi?.state],['移仓迹象',row.rollover_transfer?'有':row.rollover_transfer===false?'无':'缺失'],['席位多空持仓','未接入']].map(([label,value])=>`<div><span>${label}</span><strong>${value||'—'}</strong></div>`).join('')}</div></article>
  <article class="decision-panel"><h2>商品结构 · ${directionText(row.structure_direction)}</h2><div class="structure-grid">${[['结构得分',signed(row.structure_score)],['趋势 / 结构',structureText(row.structure_confirm)],['期限形态',structureText(row.structure)],['年化Carry',pct(row.carry_annualized)],['近月 / 远月',`${row.near_code||'—'} / ${row.far_code||'—'}`],['跨期价差',signed(row.spread)],['价差5日变化（价格单位）',signed(row.spread_change5)],['Carry 5日变化（百分点）',signed(row.carry_change5)],['有效因子组',`${row.structure_evidence?.effective_groups??0} / 4`],['现货 / 库存',`${row.structure_evidence?.basis?.status==='ok'?'有现货':'现货缺失'} / ${row.structure_evidence?.inventory?.status==='ok'?'有库存':'库存缺失'}`]].map(([label,value])=>`<div><span>${label}</span><strong>${value}</strong></div>`).join('')}</div></article>
 </section>`;
 renderSingleChart(row);
}
function optionTargetSide(row){return isShort(row)?'P':isLong(row)?'C':null}
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
function optionCandidates(row,chain){
 if(!['Call','Put'].includes(row.option_action))return [];
 const side=optionTargetSide(row);
 const candidates=(chain.records||[]).filter(item=>(item.main_code===codeOf(row)||item.underlying_code===row.main_code||item.underlying_code===row.secondary_code)&&item.call_put===side&&item.tradability?.counter_trend!==true);
 const inBand=item=>Number.isFinite(item.days_to_expiry)&&item.days_to_expiry>=7&&item.days_to_expiry<=45&&Number.isFinite(item.delta)&&Math.abs(item.delta)>=.1&&Math.abs(item.delta)<=.6;
 return candidates.filter(inBand).sort((a,b)=>(b.tradability?.score??-1)-(a.tradability?.score??-1)||Math.min(b.vol||0,b.oi||0)-Math.min(a.vol||0,a.oi||0)).slice(0,3);
}
function recommendationType(item,index){
 const d=Math.abs(item.delta||0);
 if(d>=.45)return '稳健型';
 if(d>=.25)return '平衡型';
 if(d>=.1)return '激进型';
 return ['稳健型','平衡型','激进型'][index]||'候选';
}
function optionContextPanel(row,chain){
 const picks=optionCandidates(row,chain);
 const gate=row.trend_option_gate;
 const gateText=row.structure_confirm==='CONFLICT'?'价格趋势与商品结构背离。':gate==='BLOCK'?'当前阶段不新开仓。':gate==='CONDITIONAL'?'趋势延续，等待回调。':gate==='WATCH'?'趋势酝酿，等待确认。':'趋势窗口已通过。';
 return `<div class="option-workbench"><section class="underlying-state"><div><span>标的趋势 / 得分</span><strong>${directionText(row.decision_side)} · ${signed(row.dir_score)}</strong><small>${row.trend_state_label||'无趋势'} · ${gateText}</small></div><div><span>商品结构 / 期权动作</span><strong>${directionText(row.structure_direction)} · ${optionActionText(row.option_action)}</strong><small>RPS5 ${fmt(row.rps5)} · RPS20 ${fmt(row.rps20)} · ADX ${fmt(row.adx)} · OI 5日 ${pct(row.oi_change5)}</small></div></section><section class="recommend-panel"><h3>系统候选</h3>${picks.length?picks.map((item,index)=>`<div class="recommend-card"><span>${recommendationType(item,index)}</span><strong>${item.ts_code}</strong><small>分 ${item.tradability?.score??'—'} · Delta ${fmt(item.delta)} · DTE ${item.days_to_expiry} · IV ${fmt(item.iv_reference)} · 量/仓 ${fmt(item.vol)}/${fmt(item.oi)}</small></div>`).join(''):'<div class="empty mini">当前无通过标的与合约条件的候选。</div>'}</section></div>`;
}
async function renderOptions(){
 const row=selectedRow();
 if(!row){app.innerHTML=header()+'<p class="empty">当前日期暂无商品数据</p>';return}
 app.innerHTML=header()+`<section class="decision-panel"><div class="section-heading"><div><h2>${row.name} · ${directionText(row.decision_direction)} T型报价</h2><div class="muted small">方向侧高亮，反向侧灰显；合约筛选按敏感度区间执行。</div></div><div class="mode-tabs"><button data-option-mode="steady" class="${state.optionMode==='steady'?'active':''}">稳健 .40-.55</button><button data-option-mode="default" class="${state.optionMode==='default'?'active':''}">默认 .25-.40</button><button data-option-mode="aggressive" class="${state.optionMode==='aggressive'?'active':''}">激进 .15-.30</button></div></div><div class="loading-panel">正在读取期权链…</div></section>`;
 const chain=await ensureOptions();
 if(state.view!=='options')return;
 app.innerHTML=header()+`<section class="decision-panel"><div class="section-heading"><div><h2>${row.name} · ${directionText(row.decision_direction)} T型报价</h2><div class="muted small">${chain.status||'期权链'} · 当前模式 ${optionModeRange()[2]}</div></div><div class="mode-tabs"><button data-option-mode="steady" class="${state.optionMode==='steady'?'active':''}">稳健 .40-.55</button><button data-option-mode="default" class="${state.optionMode==='default'?'active':''}">默认 .25-.40</button><button data-option-mode="aggressive" class="${state.optionMode==='aggressive'?'active':''}">激进 .15-.30</button></div></div>${optionContextPanel(row,chain)}<div class="table-wrap t-chain"><table><thead><tr><th>认购</th><th>${term('敏感度','delta')}</th><th>${term('行权价','strike')}</th><th>${term('敏感度','delta')}</th><th>认沽</th></tr></thead><tbody>${optionRows(row,chain)}</tbody></table></div></section>`;
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
 if(!data.candles?.[codeOf(row)])return;
 renderCandlestickChart($('single-chart'),{candles:data.candles[codeOf(row)],moving:data.moving?.[codeOf(row)]||{},signals:data.technical_signals?.[codeOf(row)]||[]},{window:Number($('window')?.value||60),title:`${row.name}日线K线与均线`});
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
 updateQuoteStatus();
}
function wireView(){
 $('window')?.addEventListener('change',()=>render());
 $('export-csv')?.addEventListener('click',()=>download(`趋势决策-${data.asof}-${state.view}.csv`,csvFor(state.view==='market'?sortedRows(filteredRows()):state.view==='detail'||state.view==='options'?[selectedRow()].filter(Boolean):sortedRows()),'text/csv;charset=utf-8'));
 $('commodity-search')?.addEventListener('input',event=>{state.search=event.target.value;$('commodity-results').innerHTML=decisionTable(filteredRows());$('result-count').textContent=`${filteredRows().length} 个品种`;wireRows();document.querySelectorAll('.decision-table').forEach(enableTableSorting)});
 for(const [id,key] of [['sector-filter','sector'],['side-filter','side'],['stage-filter','stage']])$(id)?.addEventListener('change',event=>{state[key]=event.target.value;render()});
 wireRows();
 document.querySelectorAll('[data-candidate-tab]').forEach(button=>button.addEventListener('click',()=>{state.candidateTab=button.dataset.candidateTab;renderCandidates();wireView();}));
 document.querySelectorAll('[data-option-mode]').forEach(button=>button.addEventListener('click',()=>{state.optionMode=button.dataset.optionMode;renderOptions().then(wireView);}));
 document.querySelectorAll('[data-jump-options]').forEach(button=>button.addEventListener('click',()=>setView('options')));
 document.querySelectorAll('.decision-table').forEach(enableTableSorting);
}
function wireRows(){
 document.querySelectorAll('[data-code]:not(.mini-action)').forEach(node=>node.addEventListener('click',event=>{
  const action=event.target.closest('[data-action]')?.dataset.action;
  const row=rows().find(item=>codeOf(item)===node.dataset.code);
  if(!row)return;
  selectRow(row,action==='options'?'options':node.dataset.viewTarget||'detail');
 }));
}
function csvFor(source){
 const fields=['ts_code','name','sector','main_code','decision_direction','signal_label','today_support','today_resistance','tomorrow_breakout','tomorrow_reversal','day_change','return1','return5','return20','rps5','rps20','rps_accel','dir_score','trend_state_label','burst_score','burst_coverage','main_oi','secondary_oi','pair_oi','oi_change5','oi_change20','volume_ratio','near_code','far_code','spread','spread_change5','structure','carry_annualized','carry_change5','structure_direction','structure_score','structure_confirm','option_action'];
 return '\ufeff'+[fields.join(','),...source.map(row=>fields.map(key=>`"${String(row[key]??'').replaceAll('"','""')}"`).join(','))].join('\r\n');
}
const QUOTE_REFRESH_MS=30000;
let quoteTimer=null;
function inTradingSession(){
 const now=new Date(),minutes=now.getHours()*60+now.getMinutes();
 if(now.getDay()===0||now.getDay()===6)return false;
 return minutes>=1255||minutes<=155||(minutes>=535&&minutes<=905);
}
function updateQuoteStatus(){
 const box=$('quote-status');
 if(!box)return;
 const meta=state.quoteMeta;
 if(!meta){box.textContent='';return}
 box.textContent=meta.error?`盘中报价不可用：${meta.error}`
  :`盘中报价 ${meta.count}/${meta.requested} 条 · ${meta.at} 抓取 · 交易时段每30秒刷新`;
}
function applyQuotes(){
 document.querySelectorAll('td[data-quote]').forEach(cell=>{
  const row=rows().find(item=>contractOf(item)===cell.dataset.quote);
  if(row)cell.outerHTML=quoteCell(row);
 });
 document.querySelectorAll('td[data-exec]').forEach(cell=>{
  const row=rows().find(item=>codeOf(item)===cell.dataset.exec);
  if(row)cell.outerHTML=execCell(row);
 });
 document.querySelectorAll('[data-intraday]').forEach(box=>{
  const row=rows().find(item=>contractOf(item)===box.dataset.intraday);
  if(row)box.innerHTML=quoteMetrics(row)+execMetrics(row);
 });
 updateQuoteStatus();
}
async function refreshQuotes(){
 const at=new Date().toLocaleTimeString('zh-CN',{hour12:false});
 try{
  const result=await api('/api/execution'+(asofQuery()?'?'+asofQuery():''));
  state.quotes=result.quotes||{};
  state.execution=Object.fromEntries((result.execution||[]).map(item=>[item.ts_code,item]));
  state.quoteMeta={error:result.error||null,count:result.count||0,requested:result.requested||0,at};
 }catch(error){
  if(!state.quotes)state.quotes={};
  if(!state.execution)state.execution={};
  state.quoteMeta={error:error.message,count:0,requested:0,at};
 }
 applyQuotes();
}
async function init(){
 try{
  data=await api('/api/data'+(asofQuery()?'?'+asofQuery():''));
  $('data-date').textContent=`收盘日 ${data.asof.slice(0,4)}.${data.asof.slice(4,6)}.${data.asof.slice(6)} · ${rows().length}条决策`;
  document.querySelectorAll('.top-tabs button').forEach(button=>button.addEventListener('click',()=>setView(button.dataset.view)));
  const oppLink=$('nav-opportunities');if(oppLink)oppLink.href='/opportunities.html'+(asofQuery()?'?'+asofQuery():'');
  await mountToolbar().catch(()=>{});
  render();
  await refreshQuotes();
  if(quoteTimer)clearInterval(quoteTimer);
  quoteTimer=setInterval(()=>{if(document.visibilityState==='visible'&&inTradingSession())refreshQuotes()},QUOTE_REFRESH_MS);
 }catch(error){
  $('error').hidden=false;
  $('error').textContent=error.message;
  app.innerHTML='<section class="loading-panel">数据读取失败</section>';
 }
}
init();
