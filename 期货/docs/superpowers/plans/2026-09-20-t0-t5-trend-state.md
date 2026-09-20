# T0-T5 Trend State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-version T0-T5 trend state machine using existing reliable indicators, then surface it in decisions, UI, MySQL import, and option gating.

**Architecture:** Create a small `trend_state.py` classifier that consumes one selected decision row and returns normalized fields. `decision_v2.py` remains the orchestration layer and attaches the new state to each commodity decision. The frontend reads the enriched API payload without changing route shape.

**Tech Stack:** Python standard library, existing decision payload dictionaries, browser-rendered ES modules, MySQL schema/import helpers.

---

### Task 1: Trend State Classifier

**Files:**
- Create: `期货/trend_state.py`
- Test: `期货/tests/test_trend_state.py`

- [ ] **Step 1: Write failing tests**

Cover neutral T0, forming T1, breakout T2, acceleration T3, continuation T4, exhaustion T5, and option permission fields.

- [ ] **Step 2: Run test to verify it fails**

Run: `..\ .venv\Scripts\python.exe -m unittest tests.test_trend_state -v` from `期货/`.

- [ ] **Step 3: Implement minimal classifier**

Implement `classify_trend_state(row, side, state_v2, start_score)` returning:
`trend_state`, `trend_state_label`, `trend_state_score`, `trend_transition`, `trend_state_reason`, `trend_speed_level`, `trend_accel_level`, `trend_option_gate`.

- [ ] **Step 4: Run focused tests**

Run: `..\ .venv\Scripts\python.exe -m unittest tests.test_trend_state -v`.

### Task 2: Decision Integration

**Files:**
- Modify: `期货/decision_v2.py`
- Test: `期货/tests/test_decision_v2.py`

- [ ] **Step 1: Add assertions to existing decision tests**

Assert strong trend becomes T4, breakout becomes T2, exhaustion becomes T5, neutral becomes T0, and option action obeys T-state gate.

- [ ] **Step 2: Wire classifier into `build_decisions`**

Attach trend state fields after `state_v2`, before option action. Gate `option_action` with `trend_option_gate`.

- [ ] **Step 3: Run focused tests**

Run: `..\ .venv\Scripts\python.exe -m unittest tests.test_trend_state tests.test_decision_v2 -v`.

### Task 3: UI And Persistence

**Files:**
- Modify: `期货/frontend/app.mjs`
- Modify: `期货/mysql_store.py`
- Modify: `期货/scripts/mysql_import.py`
- Test: `期货/tests/check_dashboard_browser.py`

- [ ] **Step 1: Add dashboard table fields**

Show "趋势状态" and "状态迁移" in market radar and detail metrics. Keep existing basic dashboard functions intact.

- [ ] **Step 2: Add MySQL columns**

Persist `trend_state`, `trend_state_label`, `trend_transition`, `trend_option_gate` in `commodity_decision_daily`.

- [ ] **Step 3: Run browser and unit tests**

Run dashboard browser check, option browser check, Python unit tests, and Node frontend tests.
