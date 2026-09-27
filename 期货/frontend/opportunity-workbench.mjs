const STATE_RANK = {START: 0, TREND: 1, PREPARE: 2, EXHAUST: 3, WAIT: 4};
const OPTION_DEPTH_WATCH = 300;
const OPTION_SCORE_USABLE = 65;

const finite = value => typeof value === 'number' && Number.isFinite(value);
const codeOf = record => record.ts_code;
const sideOf = record => record.decision_side || record.trend_direction || record.direction;
const optionSideFor = side => side === 'long' ? 'C' : side === 'short' ? 'P' : null;
const signed = value => finite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(1)}` : null;
const truthy = value => value === true || String(value).toLowerCase() === 'true';

export function ema20Summary(record){
  const direction={rising:'上行',falling:'下行',flat:'走平',unavailable:'数据不足'}[record?.ema20_direction]||'数据不足';
  const strength={strong:'强',medium:'中',weak:'弱',unavailable:'数据不足'}[record?.ema20_strength]||'数据不足';
  const status=record?.ema20_actionability||'not_actionable';
  const label=record?.ema20_actionability_label||{actionable:'可做',wait_pullback:'等待回踩',do_not_chase:'不可追',not_actionable:'不可做'}[status]||'不可做';
  const format=value=>finite(value)?`${value>=0?'+':''}${value.toFixed(2)} ATR`:'—';
  return {status,label,tone:status==='actionable'?'up':status==='not_actionable'||status==='do_not_chase'?'down':'watch',
    direction,strength,slope:finite(record?.ema20_slope5_atr)?`${format(record.ema20_slope5_atr)} / 5日`:'—',
    distance:format(record?.directional_ema20_distance_atr),
    reason:(record?.ema20_actionability_reasons||[])[0]||'EMA20数据不足'};
}

export function optionExpressionStatus(record, optionRows = []){
  const desiredSide = optionSideFor(sideOf(record));
  if(!desiredSide)return {status: 'missing', label: '期权方向缺失', best: null, risk: '标的方向不明确'};
  const candidates = optionRows.filter(row => row.call_put === desiredSide);
  if(!candidates.length)return {status: 'missing', label: '无匹配期权链', best: null, risk: '该方向暂无可评估期权'};

  const ranked = [...candidates].sort((a, b) =>
    Number(b.tradability?.recommendable === true) - Number(a.tradability?.recommendable === true) ||
    Number(b.tradability?.eligible === true) - Number(a.tradability?.eligible === true) ||
    ((b.tradability?.scenario?.conservative_rr ?? -1) - (a.tradability?.scenario?.conservative_rr ?? -1)) ||
    (b.tradability?.score ?? -1) - (a.tradability?.score ?? -1) ||
    (b.tradability?.depth ?? Math.min(b.vol ?? 0, b.oi ?? 0)) - (a.tradability?.depth ?? Math.min(a.vol ?? 0, a.oi ?? 0)) ||
    String(a.ts_code).localeCompare(String(b.ts_code)),
  );
  const best = ranked[0];
  const tradability = best.tradability || {};
  const tags = tradability.tags || [];
  const depth = tradability.depth ?? Math.min(best.vol ?? 0, best.oi ?? 0);
  const dte = best.days_to_expiry;
  if(tradability.eligible !== true){
    return {status: 'avoid', label: '期权量仓不合格', best,
      risk: tradability.block_reasons?.[0] || '单张期权量仓未通过'};
  }
  if(tradability.recommendable !== true){
    return {status: 'avoid', label: '期权不推荐', best,
      risk: tradability.recommendation_reasons?.[0] || '未通过系统推荐条件'};
  }
  if(finite(dte) && dte <= 2){
    return {status: 'avoid', label: '末日轮高风险', best, risk: '剩余时间过短，不进正常机会'};
  }
  if(tags.includes('IV透支')){
    return {status: 'watch', label: 'IV偏贵', best, risk: '隐波已透支，方向对也可能被波动率回落抵消'};
  }
  if(finite(depth) && depth < OPTION_DEPTH_WATCH){
    return {status: 'watch', label: '流动性偏薄', best, risk: '成交/持仓深度不足，滑点风险高'};
  }
  if((tradability.score ?? 0) >= OPTION_SCORE_USABLE){
    return {status: 'usable', label: `期权${tradability.grade || '可用'}`, best, risk: null};
  }
  return {status: 'watch', label: '期权仅观察', best, risk: '合约可做性未达到良好阈值'};
}

function reasonList(record, executionItem){
  const reasons = [];
  const ema=ema20Summary(record);
  reasons.push(`EMA20 ${ema.direction}·${ema.strength}，距离 ${ema.distance}`);
  if(record.trend_state_label)reasons.push(record.trend_state_label);
  else if(record.state_v2)reasons.push(record.state_v2);
  if(record.structure_confirm === 'SUPPORT')reasons.push('商品结构同向支持');
  if(record.structure_confirm === 'CONFLICT')reasons.push('趋势与结构冲突');
  if(finite(record.rps_accel) && Math.abs(record.rps_accel) >= 8)reasons.push(`RPS五日变化${signed(record.rps_accel)}`);
  if(finite(record.oi_change5) && record.oi_change5 > 0)reasons.push(`OI五日增加${signed(record.oi_change5)}%`);
  if(finite(record.volume_ratio) && record.volume_ratio >= 1.2)reasons.push(`量比${record.volume_ratio.toFixed(1)}`);
  if(executionItem?.exec_score != null)reasons.push(`盘中可执行性${executionItem.exec_score}`);
  return [...new Set(reasons)].slice(0, 3);
}

export function commodityReminderReasons(record, executionItem){
  const reasons = [];
  if(record.ema20_actionability && record.ema20_actionability!=='actionable')reasons.push(...(record.ema20_actionability_reasons||[ema20Summary(record).label]));
  if(record.state_v2 === 'EXHAUST')reasons.push('趋势进入衰竭或过度延伸区');
  if(record.structure_confirm === 'CONFLICT')reasons.push('商品结构与价格趋势背离');
  if(finite(record.directional_ema20_distance_atr) && record.directional_ema20_distance_atr > 3)reasons.push(`价格距EMA20达到${record.directional_ema20_distance_atr.toFixed(1)} ATR，追单风险高`);
  if(finite(executionItem?.exec_score) && executionItem.exec_score < 50)reasons.push(`盘中可执行性${executionItem.exec_score}，当前位置不足50`);

  if(['WAIT','PREPARE'].includes(record.state_v2)){
    if(!finite(record.dir_score))reasons.push('方向分缺失，暂时无法确认趋势方向');
    else if(Math.abs(record.dir_score) < 25)reasons.push(`方向分${record.dir_score.toFixed(1)}，未达到±25方向门槛`);
    if(!finite(record.start_score))reasons.push('启动分缺失，暂时无法确认启动强度');
    else if(record.start_score < 70)reasons.push(`启动分${record.start_score.toFixed(1)}，未达到70启动门槛`);
    if(!truthy(record.signal_base_breakout) && !truthy(record.technical_start))reasons.push('尚未出现基底突破或技术启动');
    if(!finite(record.adx))reasons.push('ADX缺失，暂时无法确认趋势强度');
    else if(record.adx < 20)reasons.push(`ADX ${record.adx.toFixed(1)}，趋势强度未达到20`);
    if(!finite(record.volume_ratio))reasons.push('商品量比缺失，暂时无法确认量能');
    else if(record.volume_ratio < 1.2)reasons.push(`商品量比${record.volume_ratio.toFixed(2)}，尚未达到1.20`);
    if(!finite(record.oi_change5))reasons.push('商品OI五日变化缺失，暂时无法确认增仓');
    else if(record.oi_change5 <= 0)reasons.push(`商品OI五日${signed(record.oi_change5)}%，未出现增仓`);
  }

  if(record.structure_confirm === 'UNKNOWN')reasons.push('商品结构数据不足，尚无法确认是否同向');
  else if(record.structure_confirm === 'NEUTRAL')reasons.push('商品结构尚未同向确认');
  if(reasons.length)return [...new Set(reasons)];

  const side = sideOf(record);
  if(side === 'long' && finite(record.today_support))return [`失效关注：跌破今日支撑${record.today_support.toFixed(2)}`];
  if(side === 'short' && finite(record.today_resistance))return [`失效关注：突破今日压力${record.today_resistance.toFixed(2)}`];
  return ['当前商品信号较完整，主要观察趋势状态是否转弱'];
}

export function reminderDisplay(reasons, limit=2){
  const all = (reasons || []).filter(Boolean);
  return {visible: all.slice(0, limit), full: all.join('；'), hiddenCount: Math.max(0, all.length-limit)};
}

function queueFor(record, executionItem){
  const state = record.state_v2;
  if(record.ema20_actionability==='not_actionable')return 'avoid';
  if(['wait_pullback','do_not_chase'].includes(record.ema20_actionability))return 'wait';
  if(state === 'EXHAUST' || record.structure_confirm === 'CONFLICT')return 'avoid';
  if((finite(record.extension_atr) && record.extension_atr > 3) || (executionItem?.exec_score != null && executionItem.exec_score < 50))return 'wait';
  if(state === 'START' || state === 'TREND')return 'focus';
  if(state === 'PREPARE')return 'watch';
  return 'avoid';
}

function actionLabel(queue, record){
  if(queue === 'focus')return '重点研究：复核商品趋势与结构';
  if(queue === 'wait')return '等待位置：逻辑可看，暂不追';
  if(queue === 'watch')return '启动观察：等信号补齐';
  return record.structure_confirm === 'CONFLICT' ? '风险回避：结构冲突' : '风险回避';
}

function avoidSeverity(row){
  if(row.state === 'EXHAUST')return 0;
  if(row.record?.structure_confirm === 'CONFLICT')return 1;
  return 2;
}

function sortRows(a, b){
  return (a.queue === 'avoid' && b.queue === 'avoid' ? avoidSeverity(a) - avoidSeverity(b) : 0) ||
    (STATE_RANK[a.state] ?? 9) - (STATE_RANK[b.state] ?? 9) ||
    (b.score ?? -Infinity) - (a.score ?? -Infinity) ||
    Math.abs(b.dirScore ?? 0) - Math.abs(a.dirScore ?? 0) ||
    a.code.localeCompare(b.code);
}

export function buildOpportunityRows(data, execution = {}){
  const groups = {focus: [], wait: [], watch: [], avoid: []};
  for(const record of data?.decisions || data?.records || []){
    const code = codeOf(record);
    const executionItem = execution?.[code] || null;
    const queue = queueFor(record, executionItem);
    const riskReasons = commodityReminderReasons(record, executionItem);
    const row = {
      code,
      name: record.name || code,
      mainCode: record.main_code || code,
      sector: record.sector || '其他',
      side: sideOf(record),
      state: record.state_v2,
      score: record.start_score ?? record.burst_score ?? record.startup_score ?? null,
      dirScore: record.dir_score ?? null,
      action: actionLabel(queue, record),
      reasons: reasonList(record, executionItem),
      risk: riskReasons[0],
      riskReasons,
      execution: executionItem,
      record,
      ema20: ema20Summary(record),
      queue,
    };
    groups[queue].push(row);
  }
  Object.values(groups).forEach(rows => rows.sort(sortRows));
  return groups;
}
