import {api,asofQuery,mountToolbar} from './common.mjs';

const $=id=>document.getElementById(id);
const fmt=(v,d=2)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toFixed(d);
const signedPct=v=>v==null?'—':`${v>0?'+':''}${fmt(v,1)}%`;
const DIR_TEXT={long:'多头',short:'空头',neutral:'震荡'};
const STATE_TEXT={START:'启动',TREND:'趋势持有',PREPARE:'准备观察',EXHAUST:'衰竭',WAIT:'等待'};
const TOP_N=5;

let report=null,toolbar=null,expanded=new Set(),dteBand=[7,120],busy=false;

const currentFilters=()=>({
  minScore:Number($('min-score').value),
  side:$('side-filter').value,
  alignedOnly:$('aligned-only').checked,
  q:$('product-search').value.trim().toLowerCase(),
});

function visibleContracts(group,f){
  return group.contracts.filter(c=>c.score>=f.minScore
    &&(f.side==='all'||c.call_put===f.side)
    &&(!f.alignedOnly||!c.counter_trend)
    &&Number.isFinite(c.days_to_expiry)
    &&c.days_to_expiry>=dteBand[0]&&c.days_to_expiry<=dteBand[1]);
}

function chainHref(group,c,f){
  const p=new URLSearchParams(location.search);
  p.set('code',group.main_code);
  if(c){
    p.set('ts_code',c.ts_code);
    p.set('min_days',String(dteBand[0]));p.set('max_days',String(dteBand[1]));
    p.set('min_score',String(f.minScore));p.set('side',f.side);
    p.set('align',f.alignedOnly?'aligned':'all');
  }else{
    p.set('min_days','0');p.set('max_days','120');
    p.set('min_score','');p.set('side','all');p.set('align','all');
  }
  return `/options.html?${p.toString()}`;
}

function gradeClass(grade){return grade==='优'?'grade-best':grade==='良'?'grade-good':'grade-watch'}

function trendBadge(group){
  const span=document.createElement('span');
  const dir=group.trend_direction;
  span.className=`trend-pill opp-dir opp-dir-${dir||'none'}`;
  span.textContent=`${DIR_TEXT[dir]||'—'} · ${group.phase||'阶段未知'}`;
  return span;
}

function contractRow(group,c,f){
  const tr=document.createElement('tr');
  if(c.counter_trend)tr.className='opp-counter';
  const first=document.createElement('td');
  const code=document.createElement('strong');code.textContent=c.ts_code;
  const sub=document.createElement('span');sub.className='contract';
  sub.textContent=`${c.underlying_code} · ${c.role==='main'?'主力':'次主力'} · 到期 ${c.maturity_date}`;
  first.append(code,sub);tr.appendChild(first);
  const side=document.createElement('td');side.textContent=c.call_put==='C'?'认购 Call':'认沽 Put';tr.appendChild(side);
  const cell=(value,cls)=>{const td=document.createElement('td');td.textContent=value;if(cls)td.className=cls;tr.appendChild(td);return td};
  cell(fmt(c.exercise_price));
  cell(signedPct(c.moneyness_pct));
  cell(c.days_to_expiry,c.days_to_expiry<=7?'opp-dte-near':null);
  cell(fmt(c.delta));
  cell(fmt(c.premium_per_lot,0));
  cell(c.iv_reference==null?'—':`${fmt(c.iv_reference,1)}%`);
  const prem=c.iv_premium_pct;
  cell(signedPct(prem),prem==null?'':(prem<=0?'up':'down'));
  cell(`${c.vol??'—'} / ${c.oi??'—'}`);
  const score=document.createElement('td');
  const strong=document.createElement('strong');strong.className=gradeClass(c.grade);
  strong.textContent=String(c.score);
  score.append(strong,document.createTextNode(` ${c.grade||''}`));
  if(c.counter_trend)score.appendChild(document.createTextNode(' · 逆趋势'));
  tr.appendChild(score);
  const tags=document.createElement('td');tags.className='opp-tags';tags.textContent=(c.tags||[]).join(' · ')||'—';tr.appendChild(tags);
  tr.tabIndex=0;
  const open=()=>{location.href=chainHref(group,c,f)};
  tr.onclick=open;
  tr.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open()}};
  return tr;
}

function groupCard(group,rows,f){
  const card=document.createElement('section');card.className='opp-card';
  const head=document.createElement('header');head.className='opp-head';
  const title=document.createElement('div');title.className='opp-title';
  const name=document.createElement('strong');name.textContent=group.name||group.main_code;
  const meta=document.createElement('span');meta.className='muted small';
  meta.textContent=[group.main_code,group.sector].filter(Boolean).join(' · ');
  title.append(name,meta,trendBadge(group));
  if(group.state_v2){
    const state=document.createElement('span');
    state.className=`status-pill state-${String(group.state_v2).toLowerCase()}`;
    state.textContent=STATE_TEXT[group.state_v2]||group.state_v2;
    title.appendChild(state);
  }
  const best=document.createElement('div');best.className='opp-sum';
  const bestLabel=document.createElement('span');bestLabel.textContent='当前筛选最佳';
  const bestValue=document.createElement('strong');
  bestValue.className=gradeClass(rows[0].grade);
  bestValue.textContent=`${fmt(rows[0].score,1)} ${rows[0].grade||''}`;
  best.append(bestLabel,bestValue);
  const count=document.createElement('div');count.className='opp-sum';
  const countLabel=document.createElement('span');countLabel.textContent='可做合约';
  const calls=rows.filter(c=>c.call_put==='C').length;
  const countValue=document.createElement('strong');
  countValue.textContent=`${rows.length} 张（Call ${calls} / Put ${rows.length-calls}）`;
  count.append(countLabel,countValue);
  const links=document.createElement('div');links.className='opp-links';
  const full=document.createElement('a');full.href=chainHref(group,null,f);full.textContent='完整期权链';
  links.appendChild(full);
  head.append(title,best,count,links);
  if(rows.length>TOP_N){
    const more=document.createElement('button');more.className='mini-action';
    const isOpen=expanded.has(group.main_code);
    more.textContent=isOpen?'收起':`展开其余 ${rows.length-TOP_N} 张`;
    more.onclick=()=>{expanded.has(group.main_code)?expanded.delete(group.main_code):expanded.add(group.main_code);render()};
    links.appendChild(more);
  }
  card.appendChild(head);
  const wrap=document.createElement('div');wrap.className='table-wrap';
  const table=document.createElement('table');
  table.innerHTML='<thead><tr><th>期权合约</th><th>方向</th><th>行权价</th><th>虚值%</th><th>剩余天</th><th>Delta</th><th>权利金/手</th><th>参考IV</th><th>IV较HV20</th><th>量 / 仓</th><th>可做性</th><th>爆发力标签</th></tr></thead>';
  const body=document.createElement('tbody');
  rows.slice(0,expanded.has(group.main_code)?undefined:TOP_N).forEach(c=>body.appendChild(contractRow(group,c,f)));
  table.appendChild(body);wrap.appendChild(table);card.appendChild(wrap);
  return card;
}

function render(){
  const f=currentFilters();
  const list=$('opp-list');list.replaceChildren();
  let products=0,contracts=0,calls=0;
  for(const group of report.groups){
    if(f.q&&!`${group.name||''} ${group.main_code||''} ${group.sector||''}`.toLowerCase().includes(f.q))continue;
    const rows=visibleContracts(group,f);
    if(!rows.length)continue;
    products++;contracts+=rows.length;calls+=rows.filter(c=>c.call_put==='C').length;
    list.appendChild(groupCard(group,rows,f));
  }
  $('stat-products').textContent=products;
  $('stat-contracts').textContent=contracts;
  $('stat-calls').textContent=calls;
  $('stat-puts').textContent=contracts-calls;
  const empty=$('opp-empty');
  if(products===0){
    empty.hidden=false;
    empty.textContent=report.groups.length
      ?'当前筛选条件下没有可做期权：可降低可做性阈值、切换到期区间/方向，或取消“仅顺势”。'
      :'该日期没有任何可做性≥50的期权合约。';
  }else empty.hidden=true;
}

async function load(){
  $('opp-error').textContent='';
  try{
    report=await api('/api/options/opportunities'+(asofQuery()?'?'+asofQuery():''));
    $('data-date').textContent=`收盘日 ${report.asof} · 期权机会总览`;
    $('opp-status').textContent=report.status||'';
    $('opp-note').textContent=report.note||'';
    const failures=report.failures||[];
    $('opp-coverage').textContent=`覆盖状态：${report.status||'—'}；覆盖失败 ${failures.length} 项。`
      +(failures.length?' 失败明细：'+failures.map(x=>`${x.exchange} ${x.underlying_code||''} ${x.reason||''}`.trim()).join('；'):'');
    const notCollected=(report.status||'').includes('尚未采集');
    if(notCollected){
      $('opp-empty').hidden=false;
      $('opp-empty').innerHTML='该日期尚未采集期权链。点击右上角“采集期权链”开始（全市场约需几分钟），完成后本页自动刷新。';
      $('opp-list').replaceChildren();
      $('stat-products').textContent=$('stat-contracts').textContent=$('stat-calls').textContent=$('stat-puts').textContent='0';
      return;
    }
    render();
  }catch(error){$('opp-error').textContent=error.message}
}

async function refreshChain(){
  if(busy||!report)return;
  const btn=$('refresh-options');busy=true;btn.disabled=true;
  try{
    await api('/api/options/refresh',{asof:report.asof});
    let job;
    do{
      await new Promise(r=>setTimeout(r,2000));
      job=await api('/api/jobs');
      $('opp-status').textContent=`期权采集中：${job.message||'…'}`;
    }while(['queued','running'].includes(job.status));
    if(['success','partial'].includes(job.status)){await load()}
    else $('opp-error').textContent=job.message||'采集失败';
  }catch(error){$('opp-error').textContent=error.message}
  finally{busy=false;btn.disabled=false}
}

function updateAlignedHint(){
  const hint=$('aligned-hint');
  hint.textContent=(!$('aligned-only').checked&&Number($('min-score').value)>55)
    ?'逆趋势合约评分硬封顶55，需同时把阈值切到「≥50 可关注」':'';
}

async function init(){
  $('min-score').onchange=()=>{updateAlignedHint();render()};
  $('side-filter').onchange=render;
  $('aligned-only').onchange=()=>{updateAlignedHint();render()};
  $('product-search').oninput=render;
  document.querySelectorAll('#dte-band button').forEach(button=>{
    button.onclick=()=>{
      document.querySelectorAll('#dte-band button').forEach(b=>b.classList.toggle('active',b===button));
      dteBand=button.dataset.band.split(',').map(Number);render();
    };
  });
  $('refresh-options').onclick=refreshChain;
  await load();
  toolbar=await mountToolbar();
}
init();
