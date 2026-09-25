# Option Eligibility and Scenario Risk/Reward Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add strict option-contract recommendation rules and Black-76 target/stop scenarios without using option availability or eligibility to filter, rank, or regroup commodity underlyings.

**Architecture:** Add a focused `option_scenario.py` module for level conversion, Black-76 repricing, and risk/reward classification. Keep commodity ranking and workbench queue assignment independent of option data. After a commodity is displayed, `option_scanner.py` evaluates concrete contracts using directional indexing, shared IV assessment, liquidity thresholds and scenarios; hard failures return `score=None` and never enter option recommendation lists, while the underlying commodity remains unchanged.

**Tech Stack:** Python 3/unittest, Black-76 analytics, JavaScript ES modules/Node test runner, existing static frontend.

---

## File map

- Create `期货/option_scenario.py`: pure scenario-level selection, repricing, RR, and signal classification.
- Modify `期货/option_analysis.py`: correct Black-76 theta.
- Modify `期货/option_scanner.py`: shared IV assessment, directional indexing, contract-only eligibility, scenario integration, candidate filtering/sorting, option-independent commodity ranking.
- Modify `期货/tests/test_options.py`: theta finite-difference regression.
- Modify `期货/tests/test_option_scanner.py`: liquidity boundaries, state gates, row-order invariance, IV consistency, scenarios, RR boundaries, opportunity exclusion.
- Modify `期货/frontend/options.mjs`: show eligibility reasons and scenario values.
- Modify `期货/frontend/app.mjs`: only recommend eligible contracts and sort by signal/RR first.
- Modify `期货/frontend/opportunity-workbench.mjs`: report ineligible contracts without changing the commodity queue.
- Modify `期货/frontend/options-filter.mjs`: exclude ineligible contracts when a score threshold is active.
- Modify relevant frontend test modules for the new contract fields.

### Task 1: Correct Black-76 theta

**Files:**
- Modify: `期货/tests/test_options.py`
- Modify: `期货/option_analysis.py:27-38`

- [ ] **Step 1: Write the failing finite-difference test**

```python
def test_theta_matches_one_calendar_day_repricing(self):
    for side in ['C', 'P']:
        current = black76(100, 100, .5, .02, .25, side)
        next_day = black76(100, 100, .5 - 1/365, .02, .25, side)
        theta = greeks(100, 100, .5, .02, .25, side)['theta']
        self.assertAlmostEqual(theta, next_day-current, places=4)
```

- [ ] **Step 2: Run the test and verify RED**

Run: `..\.venv\Scripts\python.exe -m unittest tests.test_options`

Expected: FAIL because the current rate terms produce different ATM Call/Put theta and disagree with one-day repricing.

- [ ] **Step 3: Implement the corrected theta**

```python
price = black76(future, strike, time, rate, volatility, side)
theta = (-discount * future * pdf * volatility / (2 * math.sqrt(time)) + rate * price) / 365
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `..\.venv\Scripts\python.exe -m unittest tests.test_options`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- '期货/option_analysis.py' '期货/tests/test_options.py'
git commit -m "fix: correct Black-76 theta"
```

### Task 2: Add pure option scenario calculations

**Files:**
- Create: `期货/option_scenario.py`
- Modify: `期货/tests/test_option_scanner.py`

- [ ] **Step 1: Write failing scenario tests**

Add tests that assert:

```python
self.assertEqual(stage_horizon('START'), 5)
self.assertEqual(stage_horizon('PREPARE'), 10)
self.assertEqual(stage_horizon('TREND'), 10)
self.assertEqual(classify_rr(3.0), '强烈信号')
self.assertEqual(classify_rr(2.0), '可做')
self.assertEqual(classify_rr(1.2), '观察')
self.assertEqual(classify_rr(1.19), '不可做')
```

Use a Call record with `close=100`, `raw_close=100`, `tomorrow_support=95`, `tomorrow_resistance=110`, `tomorrow_breakout=112`, `tomorrow_reversal=92`; assert target=110, stop=95, three IV scenarios exist, and conservative RR is finite. Add mirrored Put coverage and assert insufficient DTE returns `status='blocked'` with `到期时间不足`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m unittest tests.test_option_scanner`

Expected: ERROR because `option_scenario` does not exist.

- [ ] **Step 3: Implement `option_scenario.py`**

Expose:

```python
STAGE_HORIZONS = {'START': 5, 'PREPARE': 10, 'TREND': 10}
IV_FACTORS = {'conservative': .90, 'base': 1.0, 'optimistic': 1.10}

def stage_horizon(state): ...
def classify_rr(value): ...
def scenario_levels(record, option, direction): ...
def option_scenario(record, option, direction): ...
```

`scenario_levels` scales the four `tomorrow_*` values using `underlying_close / close`, chooses the nearest valid target and stop on the correct side of the real underlying price, and returns an explicit blocked reason when either side is unavailable. `option_scenario` converts trading days to calendar days with `ceil(days*7/5)`, reprices target and stop through `black76`, computes conservative RR with the specified risk floor, and returns rounded values plus `status`, `signal_level`, and `notes`.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `..\.venv\Scripts\python.exe -m unittest tests.test_option_scanner`

Expected: PASS for the new pure scenario tests.

- [ ] **Step 5: Commit**

```powershell
git add -- '期货/option_scenario.py' '期货/tests/test_option_scanner.py'
git commit -m "feat: add option target and risk reward scenarios"
```

### Task 3: Make contract eligibility and directional data authoritative

**Files:**
- Modify: `期货/tests/test_option_scanner.py`
- Modify: `期货/option_scanner.py:1-824`

- [ ] **Step 1: Write failing hard-gate tests**

Add independent tests for:

```python
# Strict boundaries
vol_2000 -> eligible is False and '成交量不足' in block_reasons
vol_2001 -> passes the volume gate
oi_1000 -> eligible is False and '持仓量不足' in block_reasons
oi_1001 -> passes the OI gate
```

Also assert missing volume/OI, `WAIT`, `EXHAUST`, neutral direction, structural conflict, and counter-trend contracts return `score=None`, `grade='不可做'`. Assert START, PREPARE, and TREND reach scenario evaluation. Create opposite long/short `directional_rps20` inputs and verify reversing input row order leaves Call and Put explosion values unchanged.

Add a separate regression asserting `build_scanner` returns the same commodity order when its option chain is missing, below the contract thresholds, or qualified. Option readiness may be displayed as metadata but must not participate in commodity sorting.

- [ ] **Step 2: Write failing IV-consistency and opportunity tests**

For `IV=45`, `HV20=40`, assert scanner IV points and contract IV points use the same relative-premium bucket and `iv_not_hot` agrees. Assert `build_opportunities` excludes `eligible=false`, includes RR observations, and sorts strong signals ahead of lower levels, then conservative RR descending.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `..\.venv\Scripts\python.exe -m unittest tests.test_option_scanner`

Expected: FAIL on eligibility fields, input-order invariance, IV consistency, and opportunity filtering.

- [ ] **Step 4: Add shared constants and IV assessment**

In `option_scanner.py` add:

```python
MIN_OPTION_VOLUME = 2000
MIN_OPTION_OI = 1000

def iv_assessment(iv, hv20):
    # return score, premium_pct, tag, not_hot using 0/15/30 percent buckets
```

Make `scan_one`, `_signals`, `tenbagger`, and `option_tradability` consume this one helper. Keep IV/liquidity visible in the scanner breakdown but calculate the 55-point underlying engine from non-option items only, using a fixed 80-point denominator and explicit coverage.

- [ ] **Step 5: Fix directional indexing**

Replace the lossy `records_by_code` dictionary with:

```python
records_by_side = {(r.get('ts_code'), r.get('direction')): r for r in payload.get('records', [])}
```

For each chain, build the long scan from the long row and the short scan from the short row. Pass the matching directional row into `option_tradability`. Do not depend on input order.

- [ ] **Step 6: Apply hard gates and scenario classification**

Compute `raw_score` first. Accumulate `block_reasons` from volume, OI, state, direction, structure, missing inputs, and scenario status. If any reason exists or conservative RR is below 1.2, return `eligible=false`, `score=None`, and `grade='不可做'`; otherwise return the raw score, existing numeric grade, `eligible=true`, `signal_level`, and `scenario`. PREPARE adds an `酝酿候选` tag; RR>=3 adds the stage-specific strong tag.

- [ ] **Step 7: Filter and sort opportunities at the backend**

`build_opportunities` must require `eligible is True` and a non-null score. Include `signal_level`, `scenario`, and thresholds in `_opportunity_contract`. Sort contracts using signal rank, conservative RR, score, volume, and OI; derive group best values from that order.

- [ ] **Step 8: Run focused tests and verify GREEN**

Run: `..\.venv\Scripts\python.exe -m unittest tests.test_option_scanner tests.test_options tests.test_decision_v2 tests.test_unified_factors`

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
git add -- '期货/option_scanner.py' '期货/tests/test_option_scanner.py'
git commit -m "feat: enforce option eligibility gates"
```

### Task 4: Unify frontend contract eligibility without changing commodity queues

**Files:**
- Modify: `期货/frontend/options.mjs`
- Modify: `期货/frontend/options-filter.mjs`
- Modify: `期货/frontend/app.mjs`
- Modify: `期货/frontend/opportunity-workbench.mjs`
- Modify: `期货/frontend/options-filter.test.mjs`
- Modify: `期货/frontend/opportunity-workbench.test.mjs`

- [ ] **Step 1: Write failing frontend tests**

Add tests asserting that:

```javascript
// Score filters never admit an explicitly ineligible contract.
selectOptions([{...row, tradability:{eligible:false, score:null}}], settings).length === 0

// Workbench labels an ineligible best contract as avoid/watch with its block reason.
optionExpressionStatus(record, [blocked]).label.includes('不可做')

// The same START/TREND commodity stays in the same queue whether options are absent,
// ineligible, or eligible.
buildOpportunityRows(data, execution, options).focus.map(row => row.code)

// Eligible strong RR wins over a merely high raw score in candidate selection/sorting helpers.
```

- [ ] **Step 2: Run tests and verify RED**

Run: `node --test frontend/options-filter.test.mjs frontend/opportunity-workbench.test.mjs`

Expected: FAIL because current filters do not understand `eligible` or scenarios.

- [ ] **Step 3: Update filtering and workbench status**

When a minimum score is selected, require `tradability.eligible===true`. In `optionExpressionStatus`, check `eligible===false` before score and return the first `block_reasons` entry. Preserve missing-chain behavior. Remove `optionStatus.status==='avoid'` from `queueFor`: queue assignment is based only on commodity state, commodity structure/extension and execution quality.

- [ ] **Step 4: Render scenario diagnostics**

In `options.mjs`, show:

- eligibility/blocked reasons;
- signal level and stage tag;
- target and stop underlying prices;
- conservative/base/optimistic option target prices;
- conservative RR and estimated horizon;
- a visible “日线模型研究值，非可成交报价” note.

In `app.mjs`, require `eligible===true` in `optionCandidates` and sort by signal rank (`强烈信号`, `可做`, `观察`), conservative RR, raw score, then volume/OI.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `node --test frontend/options-filter.test.mjs frontend/opportunity-workbench.test.mjs frontend/rules.test.mjs frontend/sortable.test.mjs`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add -- '期货/frontend/options.mjs' '期货/frontend/options-filter.mjs' '期货/frontend/app.mjs' '期货/frontend/opportunity-workbench.mjs' '期货/frontend/options-filter.test.mjs' '期货/frontend/opportunity-workbench.test.mjs'
git commit -m "feat: show option eligibility and scenario returns"
```

### Task 5: Full regression and documentation alignment

**Files:**
- Modify: `README.md`
- Modify: `期货/frontend/scanner.mjs`

- [ ] **Step 1: Update user-facing rules**

Document strict contract-level `vol>2000`, `oi>1000`, stage horizons, three IV scenarios, RR levels, and the absence of executable bid/ask quotes. Explicitly state that none of these option conditions participate in commodity filtering or queue assignment. Replace the old “标的发动机55（综合分折算）” wording with “标的发动机55（仅RPS、ADX、突破、OI、量能和商品结构）”，and state that IV and liquidity are scored once at the contract layer.

- [ ] **Step 2: Run the complete relevant Python suite**

Run:

```powershell
..\.venv\Scripts\python.exe -m unittest tests.test_options tests.test_option_scanner tests.test_decision_v2 tests.test_unified_factors tests.test_intraday tests.test_candidate_ai tests.test_dashboard_data
```

Expected: PASS with zero failures/errors.

- [ ] **Step 3: Run the complete frontend suite**

Run:

```powershell
node --test frontend/options-filter.test.mjs frontend/opportunity-workbench.test.mjs frontend/rules.test.mjs frontend/sortable.test.mjs
node --check frontend/options.mjs frontend/app.mjs frontend/opportunity-workbench.mjs
```

Expected: PASS and syntax checks exit 0.

- [ ] **Step 4: Verify the original reproductions**

Run the focused Python tests proving blocked EXHAUST/WAIT/conflict records no longer receive scores, the volume/OI boundaries are strict, directional results are input-order invariant, IV classifications agree, and theta matches finite-difference repricing.

- [ ] **Step 5: Review the diff and workspace state**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; the pre-existing untracked `期货/tests/_tmp_wedge_probe.py` remains untouched.

- [ ] **Step 6: Commit documentation**

```powershell
git add -- 'README.md' '期货/frontend/scanner.mjs'
git commit -m "docs: explain option eligibility and risk reward"
```
