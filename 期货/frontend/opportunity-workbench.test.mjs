import assert from 'node:assert/strict';
import {buildOpportunityRows, optionExpressionStatus} from './opportunity-workbench.mjs';

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
  ...overrides,
});

const option = overrides => ({
  main_code: 'JM.DCE',
  ts_code: 'JM2609-C-100.DCE',
  call_put: 'C',
  days_to_expiry: 30,
  tradability: {
    score: 76,
    grade: '良',
    depth: 1200,
    counter_trend: false,
    tags: ['Gamma甜区'],
  },
  ...overrides,
});

assert.equal(optionExpressionStatus(base(), [option()]).status, 'usable');
assert.equal(optionExpressionStatus(base(), []).status, 'missing');
assert.equal(
  optionExpressionStatus(base(), [option({tradability: {...option().tradability, counter_trend: true}})]).status,
  'avoid',
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
