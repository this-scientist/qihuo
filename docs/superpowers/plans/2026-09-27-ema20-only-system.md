# EMA20-Only System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every active moving-average dependency with one canonical EMA20 and make EMA20 strength plus ATR-normalized price distance the primary actionability signal.

**Architecture:** `strategy.indicators()` remains the single indicator producer and publishes `ema20`, `ema20_slope5_atr`, and `ema20_distance_atr`. A focused `ema20_signal.py` module owns strength classification and actionability so legacy scoring, V2 decisions, phases, scanners, and UI consume one conclusion. Payload/schema versions reject stale data, and persistence migrates atomically to EMA20-only columns.

**Tech Stack:** Python 3.11, pandas/numpy, unittest, browser ES modules, Node test runner, MySQL/PyMySQL.

---

### Task 1: Canonical EMA20 Metrics and Actionability

**Files:**
- Create: `期货/ema20_signal.py`
- Create: `期货/tests/test_ema20_signal.py`
- Modify: `期货/strategy.py`
- Modify: `期货/tests/test_strategy.py`

- [ ] **Step 1: Write failing indicator and actionability tests**

Add tests asserting `indicators()` publishes `ema20`, `ema20_slope5_atr`, and `ema20_distance_atr`, computes EMA with `ewm(span=20, adjust=False)`, and publishes none of `ma20`, `ma60`, `ma120`, `slope20`, `slope60`, `slope120`, `trend_spread`, or `ma_spread_atr_change5`. Add table-driven long/short tests for the `0.25`, `0.75`, `2`, and `3` boundaries and missing ATR.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_ema20_signal tests.test_strategy -v`

Expected: FAIL because `ema20_signal` and EMA20-only output do not exist.

- [ ] **Step 3: Implement the minimal shared API**

Create:

```python
@dataclass(frozen=True)
class Ema20Settings:
    medium_slope_atr: float = .25
    strong_slope_atr: float = .75
    actionable_distance_atr: float = 2
    max_distance_atr: float = 3

def ema20_assessment(row, side, quality_ok=True, settings=None):
    # Return direction, strength, signed slope/distance, status, label, reasons.
```

Update `indicators()` so ATR is calculated before the normalized EMA fields and remove every other moving-average calculation and derivative.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m unittest tests.test_ema20_signal tests.test_strategy -v`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add canonical EMA20 actionability`

### Task 2: Migrate Trend Scoring and Phase Logic

**Files:**
- Modify: `期货/trend_model.py`
- Modify: `期货/trend_phases.py`
- Modify: `期货/strategy.py`
- Modify: `期货/tests/test_unified_factors.py`
- Modify: `期货/tests/test_research.py`
- Modify: `期货/tests/test_strategy.py`

- [ ] **Step 1: Write failing score, crossing, and phase tests**

Require the price component to average only clipped EMA20 distance and EMA20 slope, require the startup signal to detect price crossing EMA20, and require phase classification to work with no legacy moving-average keys.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m unittest tests.test_unified_factors tests.test_research tests.test_strategy -v`

Expected: FAIL on legacy field requirements.

- [ ] **Step 3: Replace legacy formulas**

Use:

```python
price = (clip(row['ema20_distance_atr'] / 2)
         + clip(row['ema20_slope5_atr'])) / 2
price_cross = ((data.close-data.ema20)*direction > 0) & ((data.close.shift(1)-data.ema20.shift(1))*direction <= 0)
```

Keep the price group and legacy EMA score budgets unchanged, but derive them only from price position and directional EMA20 slope. Remove multi-average phase branches; return EMA20-specific rationales.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2 and expect PASS.

- [ ] **Step 5: Commit**

Commit message: `refactor: make trend logic EMA20 only`

### Task 3: Publish EMA20 Actionability in Decisions

**Files:**
- Modify: `期货/decision_v2.py`
- Modify: `期货/trend_state.py`
- Modify: `期货/option_scanner.py`
- Modify: `期货/factor_audit.py`
- Modify: `期货/tests/test_decision_v2.py`
- Modify: `期货/tests/test_trend_state.py`
- Modify: `期货/tests/test_option_scanner.py`

- [ ] **Step 1: Write failing decision tests**

Assert every directional decision contains `ema20_direction`, `ema20_strength`, `ema20_slope5_atr`, `ema20_distance_atr`, `ema20_actionability`, `ema20_actionability_label`, and ordered reasons. Assert `actionable`, `wait_pullback`, `do_not_chase`, and `not_actionable` gate option actions as 可做, 等待, and 不做.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m unittest tests.test_decision_v2 tests.test_trend_state tests.test_option_scanner -v`

Expected: FAIL because decision payloads lack EMA20 conclusions.

- [ ] **Step 3: Integrate one shared assessment**

Call `ema20_assessment()` after direction selection. Treat EMA20 `not_actionable` and `do_not_chase` as blocking, `wait_pullback` as conditional/waiting, and `actionable` as eligible for the remaining ADX/DI, RPS, breakout, structure, liquidity, and option gates. Replace all MA20 extension wording with EMA20 distance wording.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2 and expect PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: expose EMA20 trade assessment`

### Task 4: Migrate Payloads, Charts, and Cache Schemas

**Files:**
- Modify: `期货/dashboard_data.py`
- Modify: `期货/research_server.py`
- Modify: `期货/tests/test_dashboard_data.py`
- Modify: `期货/tests/test_candidate_ai.py`
- Modify: `期货/tests/test_persistence.py`

- [ ] **Step 1: Write failing payload tests**

Assert chart moving data is exactly `{'ema20': [...]}`, factors contain the EMA20 assessment fields and no removed fields, AI context names EMA20 distance, option-underlying history returns EMA20 only, and previous payload/chart schema versions are rejected.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m unittest tests.test_dashboard_data tests.test_candidate_ai tests.test_persistence -v`

Expected: FAIL on the old payload schema.

- [ ] **Step 3: Implement the payload migration**

Increment both schema versions, replace labels/groups with explicit EMA20 terminology, serialize only `ema20`, and calculate option-underlying EMA20 with `close.ewm(span=20, adjust=False).mean()`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2 and expect PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: publish EMA20-only payloads`

### Task 5: Migrate MySQL Persistence

**Files:**
- Modify: `期货/mysql_store.py`
- Modify: `期货/scripts/mysql_import.py`
- Modify: `期货/tests/test_persistence.py`

- [ ] **Step 1: Write failing schema/import tests**

Assert the active table schema and import SQL contain `ema20`, `ema20_slope5_atr`, and `ema20_distance_atr`, contain no obsolete moving-average column identifiers, and expose an idempotent exact-column migration.

- [ ] **Step 2: Run the persistence tests and verify RED**

Run: `python -m unittest tests.test_persistence -v`

Expected: FAIL on legacy schema/import columns.

- [ ] **Step 3: Update schema and guarded migration**

Declare the EMA20-only columns. In `ensure_schema()`, inspect `information_schema.columns`, add missing EMA20 columns, then drop each exact obsolete column if present. Never copy SMA values into EMA20.

- [ ] **Step 4: Run persistence tests and verify GREEN**

Run the command from Step 2 and expect PASS.

- [ ] **Step 5: Commit**

Commit message: `refactor: persist EMA20-only metrics`

### Task 6: Make EMA20 Prominent in the UI

**Files:**
- Modify: `期货/frontend/app.mjs`
- Modify: `期货/frontend/charts.mjs`
- Modify: `期货/frontend/scanner.mjs`
- Modify: `期货/frontend/research.html`
- Modify: `期货/frontend/opportunity-workbench.mjs`
- Modify: `期货/frontend/rules.test.mjs`
- Modify: `期货/frontend/charts.test.mjs`
- Modify: `期货/frontend/opportunity-workbench.test.mjs`

- [ ] **Step 1: Write failing frontend tests**

Assert the EMA20 summary renderer shows direction, strength, slope ATR, distance ATR, status, and reason; chart series and labels expose only EMA20; opportunity warnings use EMA20; rule fixtures contain no removed fields.

- [ ] **Step 2: Run frontend tests and verify RED**

Run every `frontend/*.test.mjs` directly with Node and expect the new assertions to fail.

- [ ] **Step 3: Implement the UI**

Add a prominent assessment strip/card in market opportunity and detail views. Render labels 可做, 等待回踩, 不可追, 不可做 with existing semantic tones. Rename generic moving-average copy to EMA20 and preserve the unrelated option-contract changes when merging back to the main working tree.

- [ ] **Step 4: Run frontend tests and verify GREEN**

Run every `frontend/*.test.mjs` directly with Node and expect PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: highlight EMA20 actionability`

### Task 7: Current Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `期货/docs/趋势筛选设计.md`
- Modify: `期货/docs/评分规则.md`
- Modify: `期货/docs/研究闭环设计.md`
- Modify: `期货/docs/总览页面设计.md`
- Modify: `期货/docs/统一因子与趋势检验-20260922.md`

- [ ] **Step 1: Update current documentation**

Describe EMA20 exponential calculation, ATR-normalized slope/distance, four actionability conclusions, and the removal of multi-average ordering. Mark the dated validation report's obsolete formulas as historical findings and state they are no longer active.

- [ ] **Step 2: Run forbidden-reference scan**

Run an `rg` scan over active code, tests, and current docs for `ma20`, `ma60`, `ma120`, old slope/spread fields, and generic multi-average UI copy. Expected: no active matches; only immutable historical specs/plans may retain historical names.

- [ ] **Step 3: Run all Python tests**

Inject `OAR_TUSHARE_TOKEN` from the main workspace `.env` without printing it, then run `python -m unittest discover -s tests -p 'test_*.py'`. Expected: all tests pass.

- [ ] **Step 4: Run all frontend tests**

Run each `frontend/*.test.mjs` directly with Node. Expected: all tests pass.

- [ ] **Step 5: Review diff and commit**

Verify only EMA20 work and the plan are present, then commit with `docs: document EMA20-only system`.
