import {api,asofQuery,mountToolbar,download} from './common.mjs';
import {enableTableSorting} from './sortable.mjs';
const $=id=>document.getElementById(id);let data,report,toolbar;
const labels={adx_min:'强趋势ADX',forming_adx:'方向形成ADX',strong_rps:'强趋势方向RPS',startup_rps:'启动方向RPS',max_extension_atr:'最大偏离ATR',startup_adx_rise:'启动ADX五日升幅',startup_rps_rise:'启动RPS五日升幅'};
const fmt=value=>value==null?'—':Number(value).toFixed(2);
function renderReport(value){
 report=value;$('study-summary').hidden=false;$('study-summary').replaceChildren();
 const summary=report.summary;
 [['信号数',summary.signals],['已结束 / 未结束',`${summary.completed} / ${summary.pending}`],['方向收益为正比例',fmt(summary.positive_rate)+'%'],['平均方向净收益',fmt(summary.mean_return)+'%'],['平均最大有利',fmt(summary.mean_mfe)+'%'],['平均最大不利',fmt(summary.mean_mae)+'%']].forEach(([label,value])=>{const div=document.createElement('div'),span=document.createElement('span');span.textContent=label;div.append(span,document.createTextNode(String(value)));$('study-summary').appendChild(div)});
 $('events').replaceChildren();report.events.forEach(event=>{const tr=document.createElement('tr');for(const value of [data.names[event.ts_code]||event.ts_code,event.signal_date,event.direction==='long'?'多头':'空头',event.entry_date||'—',event.exit_date||'—',event.net_return==null?'—':fmt(event.net_return)+'%',event.mfe==null?'—':fmt(event.mfe)+'%',event.mae==null?'—':fmt(event.mae)+'%',event.rolls??'—',event.status==='completed'?'已结束':'未结束']){const td=document.createElement('td');td.textContent=value;tr.appendChild(td)}$('events').appendChild(tr)});
 if(!report.events.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=10;td.className='empty';td.textContent='在当前有效历史与参数下没有新信号，不构造样本。';tr.appendChild(td);$('events').appendChild(tr)}
 $('study-limitations').textContent=report.limitations.join('；')+`。缺失规则涉及 ${summary.missing_rows} 条观察。运行ID ${report.id}。`;$('export-study').hidden=false;
}
async function run(){
 $('study-error').textContent='';$('run-study').disabled=true;$('run-study').textContent='逐日验证中…';
 try{
  let config={rules:[],match:'all'};
  if($('mode').value==='custom'){
   const saved=localStorage.getItem('commodity-dashboard-config-v1');if(!saved)throw Error('请先在总览保存因子配置');config=JSON.parse(saved);
   if(!config.rules.some(r=>r.enabled!==false))throw Error('自定义验证至少需要一项有效条件');
  }
  const value=await api('/api/validate',{asof:data.asof,mode:$('mode').value,direction:$('study-direction').value,sector:$('study-sector').value,
   hold:Number($('hold').value),cooldown:Number($('cooldown').value),cost_bps:Number($('cost').value),rules:config.rules,match:config.match,phase_settings:data.phase_settings});renderReport(value);
 }catch(error){$('study-error').textContent=error.message}finally{$('run-study').disabled=false;$('run-study').textContent='运行验证'}
}
async function init(){
  try{
   data=await api('/api/data'+(asofQuery()?'?'+asofQuery():''));$('data-date').textContent=`收盘日 ${data.asof} · 探索性验证`;
   enableTableSorting(document.querySelector('.content-split .table-wrap table'));
  Object.keys(data.sectors).forEach(name=>{const option=document.createElement('option');option.value=name;option.textContent=name;$('study-sector').appendChild(option)});
  Object.entries(data.phase_settings).forEach(([key,value])=>{const label=document.createElement('label'),input=document.createElement('input');label.textContent=labels[key];input.type='number';input.step='any';input.value=value;input.dataset.key=key;label.appendChild(input);$('phase-settings').appendChild(label)});
  toolbar=await mountToolbar();$('run-study').onclick=run;
  $('mode').onchange=()=>{const saved=localStorage.getItem('commodity-dashboard-config-v1');const config=saved?JSON.parse(saved):null;$('study-config').textContent=$('mode').value==='custom'?(config?`将使用已保存的 ${config.rules.filter(r=>r.enabled!==false).length} 项条件；历史不可重建因子保持缺失`:'尚未保存自定义条件'):'技术启动：新突破、低位ADX抬升、RPS跃升，未过度偏离'};
  $('export-study').onclick=()=>{const fields=['ts_code','signal_date','direction','entry_date','exit_date','net_return','mfe','mae','rolls','status'];const csv=[fields.join(','),...report.events.map(e=>fields.map(f=>e[f]??'').join(','))].join('\r\n');download(`信号验证-${data.asof}.csv`,'\ufeff'+csv,'text/csv;charset=utf-8')};
  $('save-phases').onclick=async()=>{try{const values=Object.fromEntries([...$('phase-settings').querySelectorAll('input')].map(input=>[input.dataset.key,input.value===''?null:Number(input.value)]));await api('/api/phases',values);$('phase-message').textContent='参数已保存，重算中；完成后可用上方数据日期查看';toolbar.watch()}catch(error){$('phase-message').textContent=error.message}};
  const history=await api('/api/snapshots');$('snapshot-history').textContent=history.snapshots.map(s=>`${s.asof} · ${s.universe}品种 · 数据指纹${s.data_hash.slice(0,8)}`).join('；');
  const runs=await api('/api/runs');$('filter-history').textContent=runs.length?runs.map(run=>`${run.time} · ${run.asof} · ${run.matches.length}品种 · ${run.config.rules.filter(r=>r.enabled!==false).length}条件`).join('；'):'尚无保存的筛选运行。可在总览点击“保存本次结果”。';
  $('fundamental-template').onclick=async()=>download('补充基本面模板.json',JSON.stringify(await api('/api/template'),null,2));
  $('fundamental-import').onclick=()=>$('fundamental-file').click();$('fundamental-file').onchange=async()=>{try{const file=$('fundamental-file').files[0];if(!file)return;const input=JSON.parse(await file.text());const result=await api('/api/supplements',{records:input.records||input});$('fundamental-status').textContent=`已保存 ${result.rows} 行，重算中`;toolbar.watch()}catch(error){$('fundamental-status').textContent=error.message}finally{$('fundamental-file').value=''}};
  const statuses=data.supplemental_status;$('fundamental-coverage').textContent=`现货/基差覆盖 ${statuses.filter(s=>s.basis).length}/${statuses.length}；全品种OI覆盖 ${statuses.filter(s=>s.commodity_oi).length}/${statuses.length}。`;
 }catch(error){$('study-error').textContent=error.message}
}
init();
