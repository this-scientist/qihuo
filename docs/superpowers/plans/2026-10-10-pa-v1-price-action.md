# PA V1 Price Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first V1 slice of the simplified option-buyer system: deterministic price-action event detection exposed through the existing futures signal API.

**Architecture:** Add a focused `price_action.py` module that computes structure side, lifecycle, event type, trade model, structure RR, and breakout quality from OHLC history. Reuse it from `futures_signals.signal_for_history` so existing dashboard consumers can read the new simplified design fields without changing data loading yet.

**Tech Stack:** Python, pandas, unittest.

---

### Task 1: Price Action Module

**Files:**
- Create: `期货/price_action.py`
- Test: `期货/tests/test_price_action.py`

- [ ] Write failing tests for 60-day breakout, range/no-event, and structure RR.
- [ ] Run `python3 -m unittest tests.test_price_action -v` and verify failures are due to missing module.
- [ ] Implement minimal deterministic detection.
- [ ] Run `python3 -m unittest tests.test_price_action -v` and verify pass.

### Task 2: Futures Signal Integration

**Files:**
- Modify: `期货/futures_signals.py`
- Test: `期货/tests/test_futures_signals.py`

- [ ] Add failing test asserting `signal_for_history` includes `price_action`.
- [ ] Run `python3 -m unittest tests.test_futures_signals -v` and verify failure.
- [ ] Merge price-action summary into signal output.
- [ ] Run `python3 -m unittest tests.test_futures_signals tests.test_price_action -v` and verify pass.

### Task 3: Baseline Verification

**Files:**
- No new files.

- [ ] Run targeted unittest suite for changed modules.
- [ ] Record pytest environment issue separately if `pytest` still points to the wrong Python.
