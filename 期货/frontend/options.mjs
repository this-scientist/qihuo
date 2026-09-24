import {api,asofQuery,mountToolbar,download,mountTips} from './common.mjs';
import {withAverageIV,selectOptions} from './options-filter.mjs';
import {renderChart} from './charts.mjs';
import {enableTableSorting} from './sortable.mjs';
const GLOSSARY={
 '期权 / 标的':'期权合约代码与其对应的真实期货月份合约（主力/次主力）。副标题显示该期货标的的趋势方向与阶段。',
 '可做性':'0–100综合分，判断这张期权"快速上涨"的潜力：标的发动机55（期货趋势/突破/ADX/RPS/增仓）+Gamma与IV结构30+到期时间15。≥80优、≥65良、≥50可关注。',
 '爆发力标签':'评分依据的白话标签：Gamma甜区=平值附近Gamma最大；末日轮=≤7天高Gamma高风险；IV便宜/透支=期权相对实际波动的贵贱；逆趋势=期权方向与期货趋势相反；深虚值=|Delta|<0.10易归零。',
 '剩余天数':'距期权到期的自然日（含当天）。7–15天Gamma强且行情来得及；≤2天极易归零。',
 '参考IV':'由期权权利金用Black-76反推的隐含波动率（年化%），≈为美式期权欧式近似。',
 '同组平均IV':'同一标的、同一到期日、同一方向全部行权价的IV平均，用来判断这张期权比同组贵还是便宜。',
 '成交量（手）':'当日成交手数；与持仓量取小值用于流动性评分，≥2000手为充足。',
 '持仓量（手）':'未平仓合约手数，代表市场深度；太小则买卖难以成交。',
};
const tips=mountTips(GLOSSARY);
const $=id=>document.getElementById(id);let data,chain,filtered=[],toolbar,detailRequest=0,filterRequest=0,autoOpenCode=null;
const fmt=value=>value==null?'—':Number(value).toFixed(2);
const DIR_TEXT={long:'多头',short:'空头',neutral:'震荡'};
const ns='http://www.w3.org/2000/svg';
function svgElement(tag,attrs={},text){const node=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([key,value])=>node.setAttribute(key,value));if(text!==undefined)node.textContent=text;return node}
function payoff(option){
 const container=$('payoff-chart');container.replaceChildren();const width=Math.max(280,container.getBoundingClientRect().width),height=290,left=72,right=18,top=23,bottom=47;
 const future=option.underlying_close,strike=option.exercise_price,mult=option.multiplier||1,premium=option.premium;
 const points=Array.from({length:41},(_,i)=>{const price=future*(.6+i*.02),intrinsic=Math.max(0,option.call_put==='C'?price-strike:strike-price);return {x:price,y:(intrinsic-premium)*mult}});
 const low=Math.min(0,...points.map(p=>p.y)),high=Math.max(0,...points.map(p=>p.y)),pad=Math.max(1,(high-low)*.08),x=value=>left+(value-points[0].x)/(points.at(-1).x-points[0].x)*(width-left-right),y=value=>top+(high+pad-value)/(high-low+2*pad)*(height-top-bottom);
 const svg=svgElement('svg',{class:'chart-svg',viewBox:`0 0 ${width} ${height}`,height,role:'img','aria-label':'买方持有至到期的理论终值损益曲线'});svg.append(svgElement('title',{},'买方到期终值：行权收益减日线权利金，不含费用'));
 svg.append(svgElement('rect',{x:left,y:top,width:width-left-right,height:height-top-bottom,fill:'none',stroke:'#e2e7ee'}));
 for(let i=0;i<5;i++){const value=low+(high-low)*i/4;svg.append(svgElement('text',{x:left-8,y:y(value)+4,'text-anchor':'end'},value.toFixed(0)))}
 for(let i=0;i<4;i++){const value=points[0].x+(points.at(-1).x-points[0].x)*i/3;svg.append(svgElement('text',{x:x(value),y:height-27,'text-anchor':i===0?'start':i===3?'end':'middle'},value.toFixed(0)))}
 svg.append(svgElement('line',{x1:left,x2:width-right,y1:y(0),y2:y(0),stroke:'#cbd3df'}));
 svg.append(svgElement('path',{d:points.map((p,i)=>`${i?'L':'M'}${x(p.x)},${y(p.y)}`).join(' '),stroke:'#2362cf','stroke-width':2,fill:'none','data-payoff':'true'}));
 svg.append(svgElement('text',{x:left,y:13,class:'axis-title'},option.multiplier?'每手到期损益（元）':'每报价单位到期损益'));
 svg.append(svgElement('text',{x:(width+left-right)/2,y:height-7,'text-anchor':'middle',class:'axis-title'},'标的到期价格'));container.appendChild(svg);
 const table=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr');['标的价格变化','到期标的价格',option.multiplier?'每手到期损益':'每报价单位损益'].forEach(label=>{const th=document.createElement('th');th.textContent=label;tr.appendChild(th)});head.appendChild(tr);table.appendChild(head);const body=document.createElement('tbody');
 [-30,-20,-10,0,10,20,30].forEach(change=>{const price=future*(1+change/100),intrinsic=Math.max(0,option.call_put==='C'?price-strike:strike-price),row=document.createElement('tr');[`${change>0?'+':''}${change}%`,fmt(price),fmt((intrinsic-premium)*mult)].forEach(value=>{const td=document.createElement('td');td.textContent=value;row.appendChild(td)});body.appendChild(row)});table.appendChild(body);$('option-scenarios').replaceChildren(table);
}
function renderTradability(option){
 let panel=$('tradability-panel');
 if(!panel){panel=document.createElement('div');panel.id='tradability-panel';panel.className='options-summary';$('option-detail-context').after(panel)}
 panel.replaceChildren();
 const tb=option.tradability;
 if(!tb){const div=document.createElement('div');div.className='muted';div.textContent='该期权缺少 Greeks 或标的数据，无法评估可做性。';panel.appendChild(div);return}
 if(tb.counter_trend){
  const warn=document.createElement('div');
  warn.style.cssText='color:#b42318;font-weight:700;margin-bottom:6px';
  warn.textContent=`⚠ 逆趋势：标的当前为${DIR_TEXT[tb.trend_direction]??''}趋势，这是${option.call_put==='C'?'看涨':'看跌'}期权。发动机分已半折、总分封顶55；抄底/摸顶须自担趋势延续风险，不作为顺势候选。`;
  panel.appendChild(warn);
 }
 const b=tb.breakdown||{};
 const rows=[['可做性',tb.score==null?'—':`${tb.score}（${tb.grade}）`],
  ['标的',tb.underlying_name?`${tb.underlying_name} · ${DIR_TEXT[tb.trend_direction]??'—'} · ${tb.phase??'—'}（期权综合分${fmt(tb.explosion)}）`:'—'],
  ['标的发动机',`${b.underlying??'—'}/${b.underlying_max??55}`],
  ['Gamma/Delta',`${b.gamma??'—'}/10 + ${b.delta??'—'}/5`],
  ['IV贵贱',b.iv==null?`缺失（0/${b.iv_max??10}）`:`${b.iv}/${b.iv_max??10}${tb.iv_premium_pct==null?'':`（较HV20 ${tb.iv_premium_pct>0?'+':''}${tb.iv_premium_pct}%）`}`],
  ['流动性',`${b.liquidity??'—'}/5（量仓较小值 ${tb.depth??'—'}手）`],
  ['时间(Theta)',`${b.dte??'—'}/15（DTE ${option.days_to_expiry}）`],
  ['标签',(tb.tags||[]).join(' · ')||'—']];
 rows.forEach(([label,value])=>{const div=document.createElement('div'),span=document.createElement('span');span.textContent=label;div.append(span,document.createTextNode(String(value)));panel.appendChild(div)});
}
async function show(option,scroll=true){
 const request=++detailRequest;
 $('option-underlying-chart').textContent='正在加载真实月份走势…';
 $('option-detail').hidden=false;$('option-detail-title').textContent=option.ts_code;
 $('option-detail-context').textContent=`真实标的 ${option.underlying_code}，收盘 ${fmt(option.underlying_close)}；到期日 ${option.maturity_date}；盈亏平衡价 ${fmt(option.break_even)}；日线权利金 ${fmt(option.premium)}，每手 ${fmt(option.premium_per_lot)}。${option.iv_status}；年利率${fmt(option.rate*100)}%，期限按自然日/365。${option.multiplier?'每手最大到期亏损为所付权利金（不含费用）。':'合约乘数缺失，不计算每手成本。'}`;
 renderTradability(option);
 payoff(option);
 try{const underlying=await api(`/api/options/underlying?asof=${data.asof}&code=${encodeURIComponent(option.underlying_code)}`);if(request!==detailRequest)return;if(!underlying.values.length){$('option-underlying-chart').textContent=underlying.reason||'该真实月份合约暂无有效历史';return}renderChart($('option-underlying-chart'),underlying.values.length?[{id:underlying.code,label:`真实标的 ${underlying.code}`,values:underlying.values},...Object.entries(underlying.moving||{}).map(([key,values])=>({id:key,label:key.toUpperCase(),values:underlying.values.map((v,i)=>[v[0],values[i]])}))]:[],{window:60,price:true,priceLabel:'真实合约价格',title:`期权对应真实月份 ${option.underlying_code} 走势`})}catch(error){if(request!==detailRequest)return;$('option-underlying-chart').textContent=error.message}
 if(scroll)$('option-detail').scrollIntoView({behavior:'smooth',block:'start'});
}
async function apply(){
 const request=++filterRequest;++detailRequest;
 $('option-error').textContent='';$('apply-options').disabled=true;
 $('option-detail').hidden=true;$('option-underlying-chart').replaceChildren();
 try{
  const settings=Object.fromEntries(['min-days','max-days','min-vol','min-oi','max-distance','reference-rate'].map(id=>[id,$(id).value===''?NaN:Number($(id).value)]));
  if(Object.values(settings).some(v=>!Number.isFinite(v)||v<0)||settings['max-days']<settings['min-days']||settings['reference-rate']>20)throw Error('筛选阈值无效，请检查天数区间与非负数值');
  const code=$('option-code').value,side=$('option-side').value,role=$('option-role').value;
  const minScoreRaw=$('min-score').value;
  const minScore=minScoreRaw===''?null:Number(minScoreRaw);
  const response=await api(`/api/options?asof=${data.asof}&rate=${settings['reference-rate']/100}${code==='all'?'':'&code='+encodeURIComponent(code)}`);
  if(request!==filterRequest)return;
  chain=response;
  filtered=selectOptions(withAverageIV(chain.records),{minDays:settings['min-days'],maxDays:settings['max-days'],minVol:settings['min-vol'],minOi:settings['min-oi'],maxDistance:settings['max-distance'],side,role,sort:$('option-sort').value,minScore,align:$('align-mode').value});
  $('option-count').textContent=`${filtered.length} / ${chain.records.length}`;$('option-rows').replaceChildren();
  filtered.forEach(option=>{const row=document.createElement('tr');row.dataset.option=option.ts_code;
   const first=document.createElement('td'),name=document.createElement('strong'),under=document.createElement('span');name.textContent=option.ts_code;
   const tb=option.tradability;
   const underText=`${option.underlying_code} · ${option.role==='main'?'主力':'次主力'} · ${option.call_put==='C'?'认购':'认沽'} · 行权价 ${fmt(option.exercise_price)} · 到期 ${option.maturity_date}`+
    (tb&&tb.underlying_name?` · 标的：${tb.underlying_name} ${DIR_TEXT[tb.trend_direction]??''}·${tb.phase??''}`:'');
   under.className='contract';under.textContent=underText;first.append(name,under);row.appendChild(first);
   const scoreCell=document.createElement('td');
   if(tb&&tb.score!=null){const s=document.createElement('strong');s.textContent=String(tb.score);const g=document.createElement('span');g.className='contract';g.textContent=tb.grade;scoreCell.append(s,document.createTextNode(' '),g);scoreCell.dataset.sort=String(tb.score)}else{scoreCell.textContent='—'}
   row.appendChild(scoreCell);
   const tagCell=document.createElement('td');tagCell.className='small muted';tagCell.textContent=tb?(tb.tags||[]).join(' · ')||'—':'—';row.appendChild(tagCell);
   for(const value of [option.days_to_expiry,option.iv_reference==null?'—':fmt(option.iv_reference)+'%'+(option.model_approximation?' ≈':''),option.average_iv==null?'—':`${fmt(option.average_iv)}%（${option.iv_sample_count}个）`,option.vol,option.oi]){const td=document.createElement('td');td.textContent=value;row.appendChild(td)}
   row.tabIndex=0;row.setAttribute('aria-label',`查看 ${option.ts_code} 及对应期货走势`);row.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();show(option)}};
   row.onclick=()=>show(option);$('option-rows').appendChild(row);
  });
  if(!filtered.length){const row=document.createElement('tr'),td=document.createElement('td');td.colSpan=8;td.className='empty';td.textContent=chain.records.length?'当前条件下无匹配期权：可降低"只看可做性"阈值、扩大天数区间或放宽量仓条件':chain.status||'该日期期权链尚未采集';row.appendChild(td);$('option-rows').appendChild(row)}
  $('option-coverage').textContent=`${chain.status}；${chain.coverage?.filter(item=>!item.underlying_code).map(item=>`${item.exchange} ${item.count}条`).join('；')||'无覆盖报告'}；失败 ${chain.failures?.length||0}。`+(chain.failures?.map(f=>`${f.exchange} ${f.underlying_code||''} ${f.reason}`).join('；')||'');$('option-limitations').textContent=(chain.limitations||[]).join('；');
  $('option-context').textContent=`数据日期 ${data.asof} · 到期剩余 ${settings['min-days']}–${settings['max-days']} 个自然日（含两端） · 点击任一期权查看对应真实月份走势。`;
  const target=autoOpenCode?filtered.find(option=>option.ts_code===autoOpenCode):null;
  if(target){show(target,false);autoOpenCode=null}
  else if(filtered.length)show(filtered[0],false);
 }catch(error){if(request===filterRequest)$('option-error').textContent=error.message}finally{if(request===filterRequest)$('apply-options').disabled=false}
}
async function init(){
 try{
  data=await api('/api/data'+(asofQuery()?'?'+asofQuery():''));$('data-date').textContent=`收盘日 ${data.asof} · 独立期权观察`;
  Object.keys(data.names).sort().forEach(code=>{const option=document.createElement('option');option.value=code;option.textContent=`${data.names[code]} · ${code}`;$('option-code').appendChild(option)});
  const params=new URLSearchParams(location.search);
  const code=params.get('code');
  if(code&&data.names[code]){$('option-code').value=code;const trend=data.records.find(r=>r.ts_code===code);if(!params.has('side')&&trend.trend_direction==='short')$('option-side').value='P'}
  // 支持从期权机会总览等页面带筛选参数/指定合约深链。
  [['min_days','min-days'],['max_days','max-days'],['min_vol','min-vol'],['min_oi','min-oi'],
   ['max_distance','max-distance'],['reference_rate','reference-rate'],
   ['side','option-side'],['role','option-role'],['align','align-mode'],['min_score','min-score']]
   .forEach(([key,id])=>{if(params.has(key))$(id).value=params.get(key)});
  autoOpenCode=params.get('ts_code');
  enableTableSorting(document.querySelector('.table-wrap table'));
  tips.decorate();
  document.querySelectorAll('[data-days]').forEach(button=>button.onclick=()=>{const [min,max]=button.dataset.days.split(',');$('min-days').value=min;$('max-days').value=max;apply()});
  $('pick-dom').onclick=()=>{$('min-days').value=0;$('max-days').value=10;$('option-side').value='all';$('option-role').value='all';$('align-mode').value='aligned';$('option-sort').value='trade';if(!$('min-score').value)$('min-score').value='50';apply()};
  $('option-sort').onchange=apply;$('min-score').onchange=apply;$('option-side').onchange=apply;$('option-role').onchange=apply;$('align-mode').onchange=apply;
  toolbar=await mountToolbar();$('apply-options').onclick=apply;await apply();
  $('option-code').onchange=()=>{$('option-detail').hidden=true;$('option-underlying-chart').replaceChildren();apply()};
  $('refresh-options').onclick=async()=>{try{await api('/api/options/refresh',{asof:data.asof});toolbar.watch()}catch(error){$('option-error').textContent=error.message}};
  $('close-option-detail').onclick=()=>{++detailRequest;$('option-detail').hidden=true};
  $('export-options').onclick=()=>{const fields=['ts_code','underlying_code','call_put','exercise_price','maturity_date','days_to_expiry','premium','premium_per_lot','vol','oi','iv_reference','average_iv','iv_sample_count','hv20','moneyness_pct','status'];const extra=row=>[row.tradability?.score??'',row.tradability?.grade??'',(row.tradability?.tags||[]).join(' '),row.tradability?.phase??''];const header=[...fields,'tradability_score','tradability_grade','tradability_tags','underlying_phase'];download(`期权观察-${data.asof}.csv`,'\ufeff'+[header.join(','),...filtered.map(row=>[...fields.map(key=>`"${String(row[key]??'').replaceAll('"','""')}"`),...extra(row).map(v=>`"${String(v).replaceAll('"','""')}"`)].join(','))].join('\r\n'),'text/csv;charset=utf-8')};
 }catch(error){$('option-error').textContent=error.message}
}
init();
