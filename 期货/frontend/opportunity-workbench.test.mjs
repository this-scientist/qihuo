import assert from 'node:assert/strict';
import {buildOpportunityRows, commodityReminderReasons, optionExpressionStatus, reminderDisplay} from './opportunity-workbench.mjs';

const base = overrides => ({
  ts_code: 'JM.DCE',
  name: '焦煤',
  sector: '黑色',
  main_code: 'JM2609.DCE',
  decision_side: 'long',
  state_v2: 'START',
  structure_confirm: 'SUPPORT',
  dir_score: 72,
  start_score: 81,
  burst_score: 76,
  trend_state_label: '趋势启动',
  signal_label: '突破',
  rps_accel: 14,
  oi_change5: 3,
  volume_ratio: 1.5,
  extension_atr: 1.2,
  today_support: 95,
  today_resistance: 110,
  ...overrides,
});

const option = overrides => ({
  main_code: 'JM.DCE',
  ts_code: 'JM2609-C-100.DCE',
  call_put: 'C',
  days_to_expiry: 30,
  tradability: {
    eligible: true,
    recommendable: true,
    score: 76,
    grade: '良',
    depth: 1200,
    counter_trend: false,
    block_reasons: [],
    recommendation_reasons: [],
    warnings: [],
    tags: ['Gamma甜区'],
  },
  ...overrides,
});

assert.equal(optionExpressionStatus(base(), [option()]).status, 'usable');
assert.equal(optionExpressionStatus(base(), []).status, 'missing');
assert.equal(
  optionExpressionStatus(base(), [option({tradability: {...option().tradability, counter_trend: true}})]).status,
  'usable',
);
assert.equal(
  optionExpressionStatus(base(), [option({tradability: {...option().tradability, tags: ['IV透支']}})]).status,
  'watch',
);
assert.equal(optionExpressionStatus(base(), [option({days_to_expiry: 2})]).status, 'avoid');
assert.equal(
  optionExpressionStatus(base(), [option({tradability: {...option().tradability, depth: 120}})]).status,
  'watch',
);
const blocked = option({ts_code: 'JM2609-C-98.DCE', tradability: {
  ...option().tradability,
  eligible: false,
  recommendable: false,
  score: null,
  raw_score: 92,
  block_reasons: ['成交量不足'],
}});
assert.equal(optionExpressionStatus(base(), [blocked]).status, 'avoid');
assert.equal(optionExpressionStatus(base(), [blocked]).risk, '成交量不足');
assert.equal(
  optionExpressionStatus(base(), [blocked, option()]).best.ts_code,
  option().ts_code,
);

const lowRR = option({ts_code: 'JM2609-C-102.DCE', tradability: {
  ...option().tradability,
  eligible: true,
  recommendable: false,
  recommendation_reasons: ['盈亏比为1.19，不合格'],
  scenario: {status: 'ok', conservative_rr: 1.19},
}});
assert.equal(optionExpressionStatus(base(), [lowRR]).status, 'avoid');
assert.equal(optionExpressionStatus(base(), [lowRR]).label, '期权不推荐');
assert.equal(optionExpressionStatus(base(), [lowRR]).risk, '盈亏比为1.19，不合格');
assert.equal(optionExpressionStatus(base(), [lowRR, option()]).best.ts_code, option().ts_code);

const rows = buildOpportunityRows(
  {
    records: [
      base({ts_code: 'A.DCE', name: '重点', state_v2: 'START'}),
      base({ts_code: 'B.DCE', name: '等待', state_v2: 'TREND', extension_atr: 3.4}),
      base({ts_code: 'C.DCE', name: '观察', state_v2: 'PREPARE', start_score: 58}),
      base({ts_code: 'D.DCE', name: '回避', state_v2: 'EXHAUST'}),
      base({ts_code: 'E.DCE', name: '冲突', structure_confirm: 'CONFLICT'}),
    ],
  },
  {'A.DCE': {exec_score: 80}, 'B.DCE': {exec_score: 35}},
  {records: [option({main_code: 'A.DCE'})]},
);

assert.equal(rows.focus[0].code, 'A.DCE');
assert.equal(rows.wait[0].code, 'B.DCE');
assert.equal(rows.watch[0].code, 'C.DCE');
assert.deepEqual(rows.avoid.map(row => row.code), ['D.DCE', 'E.DCE']);

assert.deepEqual(commodityReminderReasons(base()), ['失效关注：跌破今日支撑95.00']);
assert.deepEqual(commodityReminderReasons(base({
  state_v2: 'PREPARE', structure_confirm: 'NEUTRAL', dir_score: 32, start_score: 58,
  signal_base_breakout: false, technical_start: false, adx: 16,
  volume_ratio: .9, oi_change5: -1,
})), [
  '启动分58.0，未达到70启动门槛',
  '尚未出现基底突破或技术启动',
  'ADX 16.0，趋势强度未达到20',
  '商品量比0.90，尚未达到1.20',
  '商品OI五日-1.0%，未出现增仓',
  '商品结构尚未同向确认',
]);
assert.equal(commodityReminderReasons(base({state_v2: 'WAIT', decision_side: 'neutral', dir_score: 12, start_score: 0}))[0], '方向分12.0，未达到±25方向门槛');
assert.equal(commodityReminderReasons(base(), {exec_score: 42})[0], '盘中可执行性42，当前位置不足50');
assert.deepEqual(reminderDisplay(['原因一','原因二','原因三']), {
  visible: ['原因一','原因二'], full: '原因一；原因二；原因三', hiddenCount: 1,
});

// 主页商品卡片不得读取或展示任何期权结论；期权链变化不能改变商品文案。
const commoditySnapshots = [];
for(const optionRecords of [[], [blocked], [option()]]){
  const queues = buildOpportunityRows(
    {records: [base({ts_code: 'JM.DCE', state_v2: 'START'})]},
    {},
    {records: optionRecords},
  );
  assert.deepEqual(queues.focus.map(row => row.code), ['JM.DCE']);
  assert.equal(queues.avoid.length, 0);
  const row = queues.focus[0];
  assert.equal('optionStatus' in row, false);
  assert.equal(row.risk, '失效关注：跌破今日支撑95.00');
  assert.deepEqual(row.riskReasons, ['失效关注：跌破今日支撑95.00']);
  commoditySnapshots.push({action: row.action, reasons: row.reasons, risk: row.risk});
}
assert.deepEqual(commoditySnapshots[1], commoditySnapshots[0]);
assert.deepEqual(commoditySnapshots[2], commoditySnapshots[0]);

const optionIndependentOrder = buildOpportunityRows(
  {records: [
    base({ts_code: 'A.DCE', state_v2: 'WAIT', start_score: 50}),
    base({ts_code: 'B.DCE', state_v2: 'WAIT', start_score: 50}),
  ]},
  {},
  {records: [{...blocked, main_code: 'B.DCE'}]},
);
assert.deepEqual(optionIndependentOrder.avoid.map(row => row.code), ['A.DCE', 'B.DCE']);
