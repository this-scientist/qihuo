const STATE_RANK = {START: 0, TREND: 1, PREPARE: 2, EXHAUST: 3, WAIT: 4};
const OPTION_DEPTH_WATCH = 300;
const OPTION_SCORE_USABLE = 65;

const finite = value => typeof value === 'number' && Number.isFinite(value);
const codeOf = record => record.ts_code;
const sideOf = record => record.decision_side || record.trend_direction || record.direction;
const optionSideFor = side => side === 'long' ? 'C' : side === 'short' ? 'P' : null;
const signed = value => finite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(1)}` : null;

function optionsByMain(options){
  const groups = new Map();
  for(const row of options?.records || []){
    const key = row.main_code;
    if(!key)continue;
    if(!groups.has(key))groups.set(key, []);
    groups.get(key).push(row);
  }
  return groups;
}

export function optionExpressionStatus(record, optionRows = []){
  const desiredSide = optionSideFor(sideOf(record));
  if(!desiredSide)return {status: 'missing', label: '期权方向缺失', best: null, risk: '标的方向不明确'};
  const candidates = optionRows.filter(row => row.call_put === desiredSide);
  if(!candidates.length)return {status: 'missing', label: '无匹配期权链', best: null, risk: '该方向暂无可评估期权'};

  const ranked = [...candidates].sort((a, b) =>
    (b.tradability?.score ?? -1) - (a.tradability?.score ?? -1) ||
    (b.tradability?.depth ?? Math.min(b.vol ?? 0, b.oi ?? 0)) - (a.tradability?.depth ?? Math.min(a.vol ?? 0, a.oi ?? 0)) ||
    String(a.ts_code).localeCompare(String(b.ts_code)),
  );
  const best = ranked[0];
  const tradability = best.tradability || {};
  const tags = tradability.tags || [];
  const depth = tradability.depth ?? Math.min(best.vol ?? 0, best.oi ?? 0);
  const dte = best.days_to_expiry;
  if(tradability.counter_trend){
    return {status: 'avoid', label: '期权逆趋势', best, risk: '合约方向与标的趋势相反'};
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

function reasonList(record, optionStatus, executionItem){
  const reasons = [];
  if(record.trend_state_label)reasons.push(record.trend_state_label);
  else if(record.state_v2)reasons.push(record.state_v2);
  if(record.structure_confirm === 'SUPPORT')reasons.push('商品结构同向支持');
  if(record.structure_confirm === 'CONFLICT')reasons.push('趋势与结构冲突');
  if(finite(record.rps_accel) && Math.abs(record.rps_accel) >= 8)reasons.push(`RPS五日变化${signed(record.rps_accel)}`);
  if(finite(record.oi_change5) && record.oi_change5 > 0)reasons.push(`OI五日增加${signed(record.oi_change5)}%`);
  if(finite(record.volume_ratio) && record.volume_ratio >= 1.2)reasons.push(`量比${record.volume_ratio.toFixed(1)}`);
  if(executionItem?.exec_score != null)reasons.push(`盘中可执行性${executionItem.exec_score}`);
  if(optionStatus.status === 'usable')reasons.push(optionStatus.label);
  return [...new Set(reasons)].slice(0, 3);
}

function riskText(record, optionStatus, executionItem){
  if(record.state_v2 === 'EXHAUST')return '趋势进入衰竭或过度延伸区';
  if(record.structure_confirm === 'CONFLICT')return '结构与价格趋势背离';
  if(finite(record.extension_atr) && record.extension_atr > 3)return '偏离MA20超过3ATR，追单风险高';
  if(executionItem?.exec_score != null && executionItem.exec_score < 50)return '当前位置可执行性不足';
  if(optionStatus.risk)return optionStatus.risk;
  if(optionStatus.status === 'missing')return '期权表达缺失，不影响期货研究';
  return '等待后续信号确认';
}

function queueFor(record, optionStatus, executionItem){
  const state = record.state_v2;
  if(state === 'EXHAUST' || record.structure_confirm === 'CONFLICT' || optionStatus.status === 'avoid')return 'avoid';
  if((finite(record.extension_atr) && record.extension_atr > 3) || (executionItem?.exec_score != null && executionItem.exec_score < 50))return 'wait';
  if(state === 'START' || state === 'TREND')return 'focus';
  if(state === 'PREPARE')return 'watch';
  return 'avoid';
}

function actionLabel(queue, record, optionStatus){
  if(queue === 'focus')return optionStatus.status === 'usable' ? '重点研究：标的与期权均可复核' : '重点研究：先看期货标的';
  if(queue === 'wait')return '等待位置：逻辑可看，暂不追';
  if(queue === 'watch')return '启动观察：等信号补齐';
  return record.structure_confirm === 'CONFLICT' ? '风险回避：结构冲突' : '风险回避';
}

function avoidSeverity(row){
  if(row.state === 'EXHAUST')return 0;
  if(row.record?.structure_confirm === 'CONFLICT')return 1;
  if(row.optionStatus?.status === 'avoid')return 2;
  return 3;
}

function sortRows(a, b){
  return (a.queue === 'avoid' && b.queue === 'avoid' ? avoidSeverity(a) - avoidSeverity(b) : 0) ||
    (STATE_RANK[a.state] ?? 9) - (STATE_RANK[b.state] ?? 9) ||
    (b.score ?? -Infinity) - (a.score ?? -Infinity) ||
    Math.abs(b.dirScore ?? 0) - Math.abs(a.dirScore ?? 0) ||
    a.code.localeCompare(b.code);
}

export function buildOpportunityRows(data, execution = {}, options = {records: []}){
  const groups = {focus: [], wait: [], watch: [], avoid: []};
  const optionGroups = optionsByMain(options);
  for(const record of data?.decisions || data?.records || []){
    const code = codeOf(record);
    const executionItem = execution?.[code] || null;
    const optionRows = optionGroups.get(code) || [];
    const optionStatus = optionExpressionStatus(record, optionRows);
    const queue = queueFor(record, optionStatus, executionItem);
    const row = {
      code,
      name: record.name || code,
      mainCode: record.main_code || code,
      sector: record.sector || '其他',
      side: sideOf(record),
      state: record.state_v2,
      score: record.start_score ?? record.burst_score ?? record.startup_score ?? null,
      dirScore: record.dir_score ?? null,
      action: actionLabel(queue, record, optionStatus),
      reasons: reasonList(record, optionStatus, executionItem),
      risk: riskText(record, optionStatus, executionItem),
      optionStatus,
      execution: executionItem,
      record,
      queue,
    };
    groups[queue].push(row);
  }
  Object.values(groups).forEach(rows => rows.sort(sortRows));
  return groups;
}
