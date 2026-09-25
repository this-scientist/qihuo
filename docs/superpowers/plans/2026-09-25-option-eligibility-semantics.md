# Option Eligibility Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `eligible` mean only per-contract volume/open-interest qualification and express RR, data, direction, stage, structure, and score through a separate recommendation result.

**Architecture:** Refactor `option_tradability` into three outputs: liquidity qualification, non-blocking warnings, and recommendation eligibility. Backend opportunity aggregation and frontend system picks consume `recommendable`, while the full option chain displays both conclusions and the exact low-RR reason.

**Tech Stack:** Python 3/unittest, JavaScript ES modules, Node assertions, existing static frontend.

---

### Task 1: Lock backend semantics with failing tests

**Files:**
- Modify: `期货/tests/test_option_scanner.py`

- [ ] Replace the old hard-gate expectations with explicit qualification assertions:

```python
def test_only_volume_and_oi_control_eligibility(self):
    variants = [
        (dict(state_v2='WAIT'), '商品阶段不允许'),
        (dict(state_v2='EXHAUST'), '趋势衰竭'),
        (dict(structure_confirm='CONFLICT'), '商品结构冲突'),
        (dict(decision_side='short', trend_direction='short'), '逆趋势'),
    ]
    for changes, warning in variants:
        record = strong_record('long')
        record.update(changes)
        row = option_row(100, 'C', dte=30)
        tb = self._annotated([row], record)[row['ts_code']]
        self.assertTrue(tb['eligible'])
        self.assertNotIn(warning, tb['block_reasons'])
        self.assertIn(warning, tb['warnings'])

def test_missing_greeks_warns_without_failing_liquidity_qualification(self):
    row = option_row(100, 'C', dte=30)
    row['gamma'] = None
    tb = self._annotated([row], strong_record('long'))[row['ts_code']]
    self.assertTrue(tb['eligible'])
    self.assertIn('Greeks缺失', tb['warnings'])
    self.assertIsNotNone(tb['score'])
```

- [ ] Patch `option_scenario` in a focused test so the exact RR result is deterministic:

```python
@patch('option_scanner.option_scenario', return_value={
    'status': 'ok', 'signal_level': '不可做', 'conservative_rr': 1.19})
def test_low_rr_is_a_recommendation_failure_not_an_eligibility_failure(self, _scenario):
    row = option_row(100, 'C', dte=30)
    tb = self._annotated([row], strong_record('long'))[row['ts_code']]
    self.assertTrue(tb['eligible'])
    self.assertFalse(tb['recommendable'])
    self.assertEqual(tb['recommendation_reasons'], ['盈亏比为1.19，不合格'])
```

- [ ] Update manually constructed opportunity fixtures with `recommendable=True`, and add a fixture with `eligible=True, recommendable=False` that must be excluded.
- [ ] Run `& 'D:\project\期货\.venv\Scripts\python.exe' -m unittest tests.test_option_scanner -v` from `期货/` and verify failures point at the old eligibility semantics.

### Task 2: Implement backend qualification and recommendation separation

**Files:**
- Modify: `期货/option_scanner.py`

- [ ] Initialize separate lists and move diagnostics to `warnings`:

```python
tags, block_reasons, warnings, recommendation_reasons = [], [], [], []
```

- [ ] Keep only strict volume/OI checks in `block_reasons`, then compute qualification and display score:

```python
eligible = not block_reasons
score = raw_score if eligible else None
grade = raw_grade if eligible else '不可做'
```

- [ ] Compute the recommendation result after scenario evaluation:

```python
if scenario.get('status') != 'ok':
    recommendation_reasons.append(scenario.get('reason') or '情景评估失败')
elif scenario.get('signal_level') == '不可做':
    recommendation_reasons.append(f"盈亏比为{format_rr(scenario.get('conservative_rr'))}，不合格")
if eligible and score is not None and score < OPPORTUNITY_FLOOR:
    recommendation_reasons.append(f'综合分低于{OPPORTUNITY_FLOOR:g}')
recommendable = eligible and not recommendation_reasons
```

- [ ] Return `warnings`, `recommendable`, and `recommendation_reasons`; copy them through `_opportunity_contract`.
- [ ] In `build_opportunities`, require `tb.get('recommendable') is True` in addition to a finite score/floor check.
- [ ] Run the focused Python command again and verify it passes.
- [ ] Commit the backend change with `git commit -m "fix: separate option qualification from recommendation"`.

### Task 3: Lock and implement frontend wording

**Files:**
- Modify: `期货/frontend/opportunity-workbench.test.mjs`
- Modify: `期货/frontend/opportunity-workbench.mjs`
- Modify: `期货/frontend/options.mjs`
- Modify: `期货/frontend/app.mjs`
- Modify: `期货/frontend/opportunities.mjs`
- Modify: `期货/frontend/options.html`
- Modify: `期货/frontend/opportunities.html`

- [ ] Add an eligible-but-not-recommendable fixture and assertions:

```javascript
const lowRR = option({tradability: {
  ...option().tradability,
  eligible: true,
  recommendable: false,
  recommendation_reasons: ['盈亏比为1.19，不合格'],
  scenario: {status: 'ok', conservative_rr: 1.19},
}});
assert.equal(optionExpressionStatus(base(), [lowRR]).status, 'avoid');
assert.equal(optionExpressionStatus(base(), [lowRR]).risk, '盈亏比为1.19，不合格');
```

- [ ] Run `node frontend/opportunity-workbench.test.mjs` and verify the new assertion fails because the old helper treats the contract as usable.
- [ ] Sort contracts by `recommendable`, then `eligible`, RR, score, and depth; return a distinct non-recommendable status before counter-trend/IV diagnostics.
- [ ] In `options.mjs`, render separate rows:

```javascript
['量仓资格', tb.eligible ? '通过' : `不通过：${(tb.block_reasons||[]).join('；')}`],
['推荐结论', tb.recommendable ? '可进入系统候选' : (tb.recommendation_reasons||[]).join('；')],
['风险提示', (tb.warnings||[]).join('；') || '—'],
```

- [ ] Require `recommendable===true` in `app.mjs` system picks and `opportunities.mjs` visible contracts.
- [ ] Replace user-facing copy that calls direction, stage, structure, Greeks, or RR a qualification gate; retain the separate optional “仅顺势” display filter.
- [ ] Run `node frontend/options-filter.test.mjs`, `node frontend/opportunity-workbench.test.mjs`, `node frontend/rules.test.mjs`, and `node frontend/sortable.test.mjs`; expect all exits to be zero.
- [ ] Run `node --check frontend/options.mjs`, `node --check frontend/app.mjs`, `node --check frontend/opportunity-workbench.mjs`, and `node --check frontend/opportunities.mjs`; expect all exits to be zero.

### Task 4: Full verification and integration

**Files:**
- Modify: `README.md`

- [ ] Replace README’s combined hard-gate paragraph with the `eligible`/`recommendable` split and exact RR wording.
- [ ] Run `& 'D:\project\期货\.venv\Scripts\python.exe' -m unittest discover -s tests -v` from `期货/`; expect 228 or more tests and `OK`.
- [ ] Repeat all four frontend files and four syntax checks; expect zero exits.
- [ ] Run `git diff --check`, `git status --short`, and `git diff --stat`; inspect every modified file.
- [ ] Commit remaining documentation/frontend changes.
- [ ] Merge `codex/option-eligibility-semantics` into `main`, rerun the same full verification on `main`, remove the worktree and merged branch, and confirm `期货/tests/_tmp_wedge_probe.py` is still the only unrelated untracked file.
