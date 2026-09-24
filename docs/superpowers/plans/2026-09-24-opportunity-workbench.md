# Opportunity Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a page-level opportunity workbench that groups existing futures and option data into clearer research queues without changing factor collection, persisted payloads, or database schemas.

**Architecture:** Add a pure frontend derivation module that consumes existing `/api/data`, `/api/options`, and `/api/execution` objects. The home market view renders opportunity queues above the existing full market matrix. Option review gates only affect display grouping and labels.

**Tech Stack:** Native ES modules, existing Python HTTP server, Node-based frontend unit tests, Python unittest for existing backend tests.

---

### Task 1: Frontend Opportunity Derivation

**Files:**
- Create: `期货/frontend/opportunity-workbench.mjs`
- Test: `期货/frontend/opportunity-workbench.test.mjs`

- [ ] **Step 1: Write failing tests**

Create tests covering queue assignment and option display gates:

```javascript
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
assert.equal(optionExpressionStatus(base(), [option({tradability: {...option().tradability, counter_trend: true}})]).status, 'avoid');
assert.equal(optionExpressionStatus(base(), [option({tradability: {...option().tradability, tags: ['IV透支']}})]).status, 'watch');
assert.equal(optionExpressionStatus(base(), [option({days_to_expiry: 2})]).status, 'avoid');
assert.equal(optionExpressionStatus(base(), [option({tradability: {...option().tradability, depth: 120}})]).status, 'watch');

const rows = buildOpportunityRows({
  records: [
    base({ts_code: 'A.DCE', name: '重点', state_v2: 'START'}),
    base({ts_code: 'B.DCE', name: '等待', state_v2: 'TREND', extension_atr: 3.4}),
    base({ts_code: 'C.DCE', name: '观察', state_v2: 'PREPARE', start_score: 58}),
    base({ts_code: 'D.DCE', name: '回避', state_v2: 'EXHAUST'}),
    base({ts_code: 'E.DCE', name: '冲突', structure_confirm: 'CONFLICT'}),
  ],
}, {'A.DCE': {exec_score: 80}, 'B.DCE': {exec_score: 35}}, {records: [option({main_code: 'A.DCE'})]});

assert.equal(rows.focus[0].code, 'A.DCE');
assert.equal(rows.wait[0].code, 'B.DCE');
assert.equal(rows.watch[0].code, 'C.DCE');
assert.deepEqual(rows.avoid.map(row => row.code), ['D.DCE', 'E.DCE']);
```

- [ ] **Step 2: Run tests and verify failure**

Run: `node 期货/frontend/opportunity-workbench.test.mjs`

Expected: FAIL because `opportunity-workbench.mjs` does not exist.

- [ ] **Step 3: Implement pure derivation functions**

Implement exported functions:

```javascript
export function optionExpressionStatus(record, optionRows = []) { ... }
export function buildOpportunityRows(data, execution = {}, options = {records: []}) { ... }
```

The implementation must not mutate input records.

- [ ] **Step 4: Run tests and verify pass**

Run: `node 期货/frontend/opportunity-workbench.test.mjs`

Expected: PASS.

### Task 2: Render Workbench Above Full Matrix

**Files:**
- Modify: `期货/frontend/app.mjs`
- Test: `期货/frontend/opportunity-workbench.test.mjs`

- [ ] **Step 1: Import derivation module**

Import `buildOpportunityRows` from `./opportunity-workbench.mjs`.

- [ ] **Step 2: Load options for display derivation**

Add optional option payload state for the market view. If options are missing or fail to load, render futures queues with option status `missing`; do not block the page.

- [ ] **Step 3: Render queue sections**

Add `renderOpportunityWorkbench()` that creates four sections: `重点研究`, `等待位置`, `启动观察`, `风险回避`. Each card includes action label, reasons, risk, and buttons to detail/options.

- [ ] **Step 4: Preserve full matrix**

Keep the existing `decisionTable(filteredRows())` output under a "全市场矩阵" section below the queues.

- [ ] **Step 5: Run frontend tests**

Run: `node 期货/frontend/opportunity-workbench.test.mjs && node 期货/frontend/options-filter.test.mjs && node 期货/frontend/rules.test.mjs && node 期货/frontend/sortable.test.mjs`

Expected: all commands exit 0.

### Task 3: Styling and Visual Safety

**Files:**
- Modify: `期货/frontend/style.css`

- [ ] **Step 1: Add restrained workbench CSS**

Add styles for queue sections and cards without changing existing table layout.

- [ ] **Step 2: Run browser smoke test if available**

Run: `../.venv/bin/python 期货/tests/check_unified_browser.cjs` only if the existing command is valid; otherwise run existing Node/Python unit tests and report that browser smoke was not available.

### Task 4: Final Verification

**Files:**
- Verify: all modified files

- [ ] **Step 1: Run frontend tests**

Run: `node 期货/frontend/opportunity-workbench.test.mjs && node 期货/frontend/options-filter.test.mjs && node 期货/frontend/rules.test.mjs && node 期货/frontend/sortable.test.mjs`

- [ ] **Step 2: Run related Python tests**

Run: `.venv/bin/python -m unittest 期货.tests.test_option_scanner 期货.tests.test_dashboard_data`

- [ ] **Step 3: Inspect diff**

Run: `git diff --stat && git diff -- 期货/frontend docs/superpowers/plans/2026-09-24-opportunity-workbench.md`

Confirm no backend schema, collector, database, or payload persistence files changed.
