# Market Structure Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a price-action-first market structure engine that classifies `一买` as rebound, CHoCH, BOS, or pullback-confirmed reversal before option priority is raised.

**Architecture:** Add a focused backend module `期货/market_structure.py` that derives swing points, latest structure state, structure events, invalidation levels, and chart annotations from daily OHLCV/OI history. Merge its latest summary into dashboard records/decisions, let `futures_signals.py` consume the summary for `BUY1/SELL1` context, and expose structure events to the existing K-line chart. Frontend changes stay inside the current dashboard/table/detail/chart surfaces.

**Tech Stack:** Python standard library, pandas, existing `unittest` tests, ES modules, Node `node:test`.

---

## File Structure

- Create `期货/market_structure.py`: owns swing detection, structure state/event classification, quality labels, invalidation levels, latest summary, and chart event series.
- Create `期货/tests/test_market_structure.py`: unit tests for swing classification, CHoCH, BOS, pullback confirmation, failed breaks, mirrored short cases, and no-future-bar behavior.
- Modify `期货/dashboard_data.py`: import market structure functions, merge latest structure fields into records/decisions, publish `market_structure_events`, and bump payload/chart schema versions.
- Modify `期货/tests/test_dashboard_data.py`: verify old schema versions are rejected and payload contract accepts new fields.
- Modify `期货/futures_signals.py`: accept optional structure context and prefer market-structure labels over EMA20-only labels.
- Modify `期货/tests/test_futures_signals.py`: update BUY1 context tests to assert rebound/CHoCH/BOS/confirmed labels.
- Modify `期货/frontend/app.mjs`: display structure label, event, break level, invalidation level, and quality in table/detail/export fields.
- Modify `期货/frontend/charts.mjs`: render structure event markers and show event details in tooltips.
- Modify `期货/frontend/charts.test.mjs`: cover marker-safe rendering and tooltip label helpers if extracted.
- Modify relevant frontend tests if existing table/detail helpers assert exact field lists.

## Task 1: Backend Market Structure Module

**Files:**
- Create: `期货/market_structure.py`
- Test: `期货/tests/test_market_structure.py`

- [ ] **Step 1: Write failing tests for swing state classification**

Create `期货/tests/test_market_structure.py`:

```python
import unittest

import pandas as pd

from market_structure import find_structure_swings, structure_for_history


def frame(prices):
    return pd.DataFrame({
        'trade_date': [f'2026{index:04d}' for index in range(1, len(prices) + 1)],
        'open': prices,
        'high': [price + 1 for price in prices],
        'low': [price - 1 for price in prices],
        'close': prices,
        'vol': [1000 for _ in prices],
        'oi': [10000 for _ in prices],
    })


class MarketStructureTests(unittest.TestCase):
    def test_downtrend_state_from_lower_highs_and_lower_lows(self):
        result = structure_for_history(frame([130, 120, 126, 112, 118, 104, 110, 101]), pivot_strength=1)

        self.assertEqual(result['market_structure_state'], 'downtrend')
        self.assertEqual(result['market_structure_side'], 'short')
        self.assertEqual(result['market_structure_label'], '下跌结构')

    def test_uptrend_state_from_higher_highs_and_higher_lows(self):
        result = structure_for_history(frame([100, 110, 104, 118, 112, 126, 120, 130]), pivot_strength=1)

        self.assertEqual(result['market_structure_state'], 'uptrend')
        self.assertEqual(result['market_structure_side'], 'long')
        self.assertEqual(result['market_structure_label'], '上涨结构')

    def test_range_state_when_swings_are_mixed(self):
        result = structure_for_history(frame([100, 110, 103, 109, 102, 108, 101, 107]), pivot_strength=1)

        self.assertEqual(result['market_structure_state'], 'range')
        self.assertEqual(result['market_structure_side'], 'neutral')
        self.assertEqual(result['market_structure_label'], '震荡结构')

    def test_swings_are_serialisable(self):
        swings = find_structure_swings(frame([100, 90, 120, 105, 130]), pivot_strength=1)

        self.assertEqual(swings[0]['kind'], 'low')
        self.assertIn('trade_date', swings[0])
        self.assertIn('price', swings[0])
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_market_structure.py'
```

Expected: FAIL with `ModuleNotFoundError: No module named 'market_structure'`.

- [ ] **Step 3: Implement minimal swing detection and state classification**

Create `期货/market_structure.py`:

```python
"""Price-action market structure engine."""
from __future__ import annotations

import math

import pandas as pd


def _finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _clean_ohlc(history):
    required = {'trade_date', 'open', 'high', 'low', 'close'}
    if history is None or not required.issubset(history.columns):
        return pd.DataFrame(columns=['trade_date', 'open', 'high', 'low', 'close', 'vol', 'oi'])
    fields = ['trade_date', 'open', 'high', 'low', 'close']
    for optional in ['vol', 'oi']:
        if optional in history.columns:
            fields.append(optional)
    data = history.loc[:, fields].copy()
    data['trade_date'] = data['trade_date'].astype(str)
    for field in ['open', 'high', 'low', 'close', 'vol', 'oi']:
        if field in data.columns:
            data[field] = pd.to_numeric(data[field], errors='coerce')
    return data.dropna(subset=['open', 'high', 'low', 'close']).sort_values('trade_date').reset_index(drop=True)


def find_structure_swings(history, pivot_strength=2):
    data = _clean_ohlc(history)
    if len(data) < pivot_strength * 2 + 1:
        return []
    highs = data['high'].values
    lows = data['low'].values
    dates = data['trade_date'].values
    raw = []
    for index in range(pivot_strength, len(data) - pivot_strength):
        is_high = all(highs[index] > highs[index + offset]
                      for offset in range(-pivot_strength, pivot_strength + 1)
                      if offset != 0)
        is_low = all(lows[index] < lows[index + offset]
                     for offset in range(-pivot_strength, pivot_strength + 1)
                     if offset != 0)
        if is_high:
            raw.append(dict(index=index, trade_date=str(dates[index]), price=float(highs[index]), kind='high'))
        elif is_low:
            raw.append(dict(index=index, trade_date=str(dates[index]), price=float(lows[index]), kind='low'))
    merged = []
    for point in raw:
        if merged and merged[-1]['kind'] == point['kind']:
            if point['kind'] == 'high' and point['price'] > merged[-1]['price']:
                merged[-1] = point
            elif point['kind'] == 'low' and point['price'] < merged[-1]['price']:
                merged[-1] = point
        else:
            merged.append(point)
    return merged


def _structure_state(swings):
    highs = [point for point in swings if point['kind'] == 'high'][-3:]
    lows = [point for point in swings if point['kind'] == 'low'][-3:]
    if len(highs) >= 2 and len(lows) >= 2:
        higher_highs = highs[-1]['price'] > highs[-2]['price']
        higher_lows = lows[-1]['price'] > lows[-2]['price']
        lower_highs = highs[-1]['price'] < highs[-2]['price']
        lower_lows = lows[-1]['price'] < lows[-2]['price']
        if higher_highs and higher_lows:
            return 'uptrend', 'long', '上涨结构'
        if lower_highs and lower_lows:
            return 'downtrend', 'short', '下跌结构'
    return 'range', 'neutral', '震荡结构'


def _empty_summary():
    return {
        'market_structure_state': 'range',
        'market_structure_side': 'neutral',
        'market_structure_label': '震荡结构',
        'market_structure_event': 'none',
        'market_structure_event_label': '无结构事件',
        'market_structure_priority': 20,
        'market_structure_break_level': None,
        'market_structure_invalid_level': None,
        'market_structure_last_swing_high': None,
        'market_structure_last_swing_low': None,
        'breakout_quality': 'unknown',
    }


def structure_for_history(history, pivot_strength=2):
    data = _clean_ohlc(history)
    swings = find_structure_swings(data, pivot_strength)
    if not swings:
        return _empty_summary()
    state, side, label = _structure_state(swings)
    last_high = next((point for point in reversed(swings) if point['kind'] == 'high'), None)
    last_low = next((point for point in reversed(swings) if point['kind'] == 'low'), None)
    summary = _empty_summary()
    summary.update({
        'market_structure_state': state,
        'market_structure_side': side,
        'market_structure_label': label,
        'market_structure_priority': 30 if state in {'uptrend', 'downtrend'} else 20,
        'market_structure_last_swing_high': round(last_high['price'], 4) if last_high else None,
        'market_structure_last_swing_low': round(last_low['price'], 4) if last_low else None,
    })
    return summary
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_market_structure.py'
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit Task 1**

```bash
git add 期货/market_structure.py 期货/tests/test_market_structure.py
git commit -m "feat: add market structure swing state"
```

## Task 2: CHoCH, BOS, Pullback, Failed Break, And Quality

**Files:**
- Modify: `期货/market_structure.py`
- Modify: `期货/tests/test_market_structure.py`

- [ ] **Step 1: Add failing event tests**

Append to `MarketStructureTests`:

```python
    def test_choch_up_when_downtrend_lower_high_breaks(self):
        result = structure_for_history(frame([130, 120, 126, 112, 118, 104, 110, 121]), pivot_strength=1)

        self.assertEqual(result['market_structure_state'], 'potential_reversal')
        self.assertEqual(result['market_structure_event'], 'choch_up')
        self.assertEqual(result['market_structure_event_label'], 'CHoCH 潜在多头转向')
        self.assertEqual(result['market_structure_break_level'], 111.0)
        self.assertEqual(result['market_structure_invalid_level'], 103.0)
        self.assertEqual(result['market_structure_priority'], 55)

    def test_bos_up_after_choch_breaks_major_high(self):
        result = structure_for_history(frame([130, 120, 126, 112, 118, 104, 110, 121, 115, 132]), pivot_strength=1)

        self.assertEqual(result['market_structure_event'], 'bos_up')
        self.assertEqual(result['market_structure_event_label'], 'BOS 多头结构突破')
        self.assertEqual(result['market_structure_priority'], 75)

    def test_pullback_confirmed_up_after_bos_holds_level(self):
        result = structure_for_history(frame([130, 120, 126, 112, 118, 104, 110, 121, 115, 132, 124, 133]), pivot_strength=1)

        self.assertEqual(result['market_structure_event'], 'pullback_confirmed_up')
        self.assertEqual(result['market_structure_event_label'], 'BOS 后回踩确认')
        self.assertEqual(result['market_structure_priority'], 90)
        self.assertEqual(result['market_structure_state'], 'uptrend')

    def test_failed_break_up_when_high_pokes_above_but_close_returns_inside(self):
        data = frame([130, 120, 126, 112, 118, 104, 110])
        data.loc[len(data)] = {
            'trade_date': '20260009',
            'open': 109,
            'high': 113,
            'low': 107,
            'close': 109,
            'vol': 900,
            'oi': 9800,
        }

        result = structure_for_history(data, pivot_strength=1)

        self.assertEqual(result['market_structure_event'], 'failed_break_up')
        self.assertEqual(result['breakout_quality'], 'failed')

    def test_short_events_are_mirrored(self):
        result = structure_for_history(frame([100, 110, 104, 118, 112, 126, 120, 109]), pivot_strength=1)

        self.assertEqual(result['market_structure_event'], 'choch_down')
        self.assertEqual(result['market_structure_event_label'], 'CHoCH 潜在空头转向')
        self.assertEqual(result['market_structure_side'], 'short')
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_market_structure.py'
```

Expected: FAIL on event assertions because Task 1 only returned `none`.

- [ ] **Step 3: Add ATR, quality, event classification helpers**

In `期货/market_structure.py`, add helpers above `structure_for_history`:

```python
def _atr14(data):
    high = data['high']
    low = data['low']
    close = data['close']
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    value = tr.ewm(alpha=1 / 14, adjust=False, min_periods=3).mean().iloc[-1]
    return float(value) if _finite(value) and value > 0 else max(float((high - low).tail(5).mean()), 1e-9)


def _breakout_quality(data, side, level, failed=False):
    if failed:
        return 'failed'
    row = data.iloc[-1]
    atr = _atr14(data)
    body_atr = abs(float(row['close']) - float(row['open'])) / atr
    bar_range = max(float(row['high']) - float(row['low']), 1e-9)
    close_pos = (float(row['close']) - float(row['low'])) / bar_range
    if side == 'short':
        close_pos = 1 - close_pos
    beyond = (float(row['close']) - level) if side == 'long' else (level - float(row['close']))
    beyond_atr = beyond / atr
    vol_ratio = None
    if 'vol' in data.columns and len(data) >= 6:
        base = pd.to_numeric(data['vol'].iloc[-6:-1], errors='coerce').mean()
        vol_ratio = float(row['vol']) / float(base) if _finite(base) and base > 0 and _finite(row.get('vol')) else None
    if close_pos >= 0.65 and (body_atr >= 0.5 or beyond_atr >= 0.2) and (vol_ratio is None or vol_ratio >= 0.8):
        return 'clean'
    return 'weak'


def _last_two(swings, kind):
    return [point for point in swings if point['kind'] == kind][-2:]


def _event_summary(data, swings, state):
    summary = {}
    close = float(data.iloc[-1]['close'])
    high = float(data.iloc[-1]['high'])
    low = float(data.iloc[-1]['low'])
    highs = _last_two(swings, 'high')
    lows = _last_two(swings, 'low')
    last_high = highs[-1] if highs else None
    prev_high = highs[-2] if len(highs) >= 2 else None
    last_low = lows[-1] if lows else None
    prev_low = lows[-2] if len(lows) >= 2 else None
    if state == 'downtrend' and last_high and close > last_high['price']:
        major = prev_high and close > prev_high['price']
        event = 'bos_up' if major else 'choch_up'
        label = 'BOS 多头结构突破' if major else 'CHoCH 潜在多头转向'
        priority = 75 if major else 55
        summary.update(dict(market_structure_state='potential_reversal', market_structure_side='long',
            market_structure_label='潜在多头转向', market_structure_event=event,
            market_structure_event_label=label, market_structure_priority=priority,
            market_structure_break_level=round((prev_high if major else last_high)['price'], 4),
            market_structure_invalid_level=round(last_low['price'], 4) if last_low else None,
            breakout_quality=_breakout_quality(data, 'long', (prev_high if major else last_high)['price'])))
    elif state == 'downtrend' and last_high and high > last_high['price'] and close <= last_high['price']:
        summary.update(dict(market_structure_event='failed_break_up', market_structure_event_label='上破失败',
            market_structure_break_level=round(last_high['price'], 4), breakout_quality='failed'))
    elif state == 'uptrend' and last_low and close < last_low['price']:
        major = prev_low and close < prev_low['price']
        event = 'bos_down' if major else 'choch_down'
        label = 'BOS 空头结构突破' if major else 'CHoCH 潜在空头转向'
        priority = 75 if major else 55
        summary.update(dict(market_structure_state='potential_reversal', market_structure_side='short',
            market_structure_label='潜在空头转向', market_structure_event=event,
            market_structure_event_label=label, market_structure_priority=priority,
            market_structure_break_level=round((prev_low if major else last_low)['price'], 4),
            market_structure_invalid_level=round(last_high['price'], 4) if last_high else None,
            breakout_quality=_breakout_quality(data, 'short', (prev_low if major else last_low)['price'])))
    elif state == 'uptrend' and last_low and low < last_low['price'] and close >= last_low['price']:
        summary.update(dict(market_structure_event='failed_break_down', market_structure_event_label='下破失败',
            market_structure_break_level=round(last_low['price'], 4), breakout_quality='failed'))
    return summary
```

- [ ] **Step 4: Wire event helpers into `structure_for_history`**

Replace the end of `structure_for_history` with:

```python
    summary = _empty_summary()
    summary.update({
        'market_structure_state': state,
        'market_structure_side': side,
        'market_structure_label': label,
        'market_structure_priority': 30 if state in {'uptrend', 'downtrend'} else 20,
        'market_structure_last_swing_high': round(last_high['price'], 4) if last_high else None,
        'market_structure_last_swing_low': round(last_low['price'], 4) if last_low else None,
    })
    summary.update(_event_summary(data, swings, state))
    if summary['market_structure_event'] == 'bos_up' and len(data) >= 3:
        last_three = data.tail(3)
        break_level = summary['market_structure_break_level']
        if break_level is not None and float(last_three.iloc[-2]['low']) >= float(break_level) and float(last_three.iloc[-1]['close']) > float(last_three.iloc[-2]['high']):
            summary.update(dict(market_structure_state='uptrend', market_structure_side='long',
                market_structure_label='上涨结构', market_structure_event='pullback_confirmed_up',
                market_structure_event_label='BOS 后回踩确认', market_structure_priority=90,
                market_structure_invalid_level=round(float(last_three.iloc[-2]['low']), 4)))
    if summary['market_structure_event'] == 'bos_down' and len(data) >= 3:
        last_three = data.tail(3)
        break_level = summary['market_structure_break_level']
        if break_level is not None and float(last_three.iloc[-2]['high']) <= float(break_level) and float(last_three.iloc[-1]['close']) < float(last_three.iloc[-2]['low']):
            summary.update(dict(market_structure_state='downtrend', market_structure_side='short',
                market_structure_label='下跌结构', market_structure_event='pullback_confirmed_down',
                market_structure_event_label='BOS 后回踩确认', market_structure_priority=90,
                market_structure_invalid_level=round(float(last_three.iloc[-2]['high']), 4)))
    return summary
```

- [ ] **Step 5: Run tests and refine shapes until all pass**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_market_structure.py'
```

Expected: PASS. If a synthetic sequence does not create the intended confirmed pivots, adjust only the test price sequence, not the expected semantics.

- [ ] **Step 6: Commit Task 2**

```bash
git add 期货/market_structure.py 期货/tests/test_market_structure.py
git commit -m "feat: classify market structure events"
```

## Task 3: Publish Structure In Dashboard Payload

**Files:**
- Modify: `期货/dashboard_data.py`
- Modify: `期货/tests/test_dashboard_data.py`

- [ ] **Step 1: Add failing schema/cache test**

In `期货/tests/test_dashboard_data.py`, update the cache invalidation test:

```python
    def test_market_structure_change_invalidates_old_cache_versions(self):
        self.assertFalse(payload_schema_current({'payload_schema_version': 5}))
        self.assertFalse(chart_schema_current({'chart_schema_version': 4}))
```

If the old test name `test_signal_context_change_invalidates_old_cache_versions` exists, replace it with this test.

- [ ] **Step 2: Add failing payload contract test**

Add a lightweight test near existing chart tests:

```python
    def test_structure_event_payload_key_is_current_schema_contract(self):
        payload = {
            'payload_schema_version': PAYLOAD_SCHEMA_VERSION,
            'chart_schema_version': CHART_SCHEMA_VERSION,
            'market_structure_events': {'JD.DCE': []},
        }

        self.assertTrue(payload_schema_current(payload))
        self.assertTrue(chart_schema_current(payload))
```

- [ ] **Step 3: Run dashboard tests and verify failure**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_dashboard_data.py'
```

Expected: FAIL because versions are still old and payload builder does not yet publish `market_structure_events`.

- [ ] **Step 4: Import and wire structure functions**

In `期货/dashboard_data.py`, add:

```python
from market_structure import structure_for_history, structure_series
```

Change schema constants:

```python
CHART_SCHEMA_VERSION = 5
PAYLOAD_SCHEMA_VERSION = 6
```

In `build_payload`, change:

```python
curves, moving, candles, technical_signals, measured_moves = {}, {}, {}, {}, {}
```

to:

```python
curves, moving, candles, technical_signals, measured_moves, market_structure_events = {}, {}, {}, {}, {}, {}
```

Inside the per-history loop, after `technical_signals[code] = chart_signals(shared.reset_index())`, add:

```python
market_structure_events[code] = structure_series(shared.reset_index())
```

In the `records` loop, after `record.update(signal_for_history(histories[record['ts_code']]))`, add:

```python
record.update(structure_for_history(histories[record['ts_code']]))
```

In the `decisions` loop, after `decision.update(signal_for_history(histories[decision['ts_code']]))`, add:

```python
decision.update(structure_for_history(histories[decision['ts_code']]))
```

In the returned dict, add:

```python
market_structure_events=market_structure_events,
```

- [ ] **Step 5: Implement `structure_series` in `market_structure.py`**

Add:

```python
def structure_series(history, pivot_strength=2):
    data = _clean_ohlc(history)
    if data.empty:
        return []
    events = []
    for end in range(1, len(data) + 1):
        current = data.iloc[:end]
        summary = structure_for_history(current, pivot_strength=pivot_strength)
        if summary.get('market_structure_event') and summary['market_structure_event'] != 'none':
            events.append({
                'trade_date': str(current.iloc[-1]['trade_date']),
                'event': summary['market_structure_event'],
                'label': summary['market_structure_event_label'],
                'side': summary['market_structure_side'],
                'close': round(float(current.iloc[-1]['close']), 6),
                'break_level': summary['market_structure_break_level'],
                'invalid_level': summary['market_structure_invalid_level'],
                'quality': summary['breakout_quality'],
            })
    return events
```

- [ ] **Step 6: Run backend tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_market_structure.py'
python3 -m unittest discover -s tests -p 'test_dashboard_data.py'
```

Expected: PASS for both.

- [ ] **Step 7: Commit Task 3**

```bash
git add 期货/market_structure.py 期货/dashboard_data.py 期货/tests/test_dashboard_data.py
git commit -m "feat: publish market structure payload"
```

## Task 4: Reinterpret BUY1 And SELL1 With Structure Context

**Files:**
- Modify: `期货/futures_signals.py`
- Modify: `期货/tests/test_futures_signals.py`
- Modify: `期货/dashboard_data.py`

- [ ] **Step 1: Add failing tests for structure-aware BUY1 labels**

In `期货/tests/test_futures_signals.py`, add:

```python
    def test_first_buy_uses_market_structure_choch_context(self):
        signal = signal_for_history(
            frame([10, 9, 8, 11]),
            structure=dict(market_structure_event='choch_up', market_structure_state='potential_reversal'),
        )

        self.assertEqual(signal['signal_context'], 'choch_reversal')
        self.assertEqual(signal['signal_context_label'], 'CHoCH 一买')

    def test_first_buy_uses_market_structure_bos_context(self):
        signal = signal_for_history(
            frame([10, 9, 8, 11]),
            structure=dict(market_structure_event='bos_up', market_structure_state='potential_reversal'),
        )

        self.assertEqual(signal['signal_context'], 'bos_reversal')
        self.assertEqual(signal['signal_context_label'], 'BOS 一买')

    def test_first_buy_uses_pullback_confirmed_context(self):
        signal = signal_for_history(
            frame([10, 9, 8, 11]),
            structure=dict(market_structure_event='pullback_confirmed_up', market_structure_state='uptrend'),
        )

        self.assertEqual(signal['signal_context'], 'confirmed_reversal')
        self.assertEqual(signal['signal_context_label'], '回踩确认一买')
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_futures_signals.py'
```

Expected: FAIL with `signal_for_history() got an unexpected keyword argument 'structure'`.

- [ ] **Step 3: Add structure override helper**

In `期货/futures_signals.py`, add above `_trend_context`:

```python
def _structure_context(code, structure):
    if not structure or code not in {'BUY1', 'SELL1'}:
        return None, None
    event = structure.get('market_structure_event')
    if code == 'BUY1':
        mapping = {
            'choch_up': ('choch_reversal', 'CHoCH 一买'),
            'bos_up': ('bos_reversal', 'BOS 一买'),
            'pullback_confirmed_up': ('confirmed_reversal', '回踩确认一买'),
            'failed_break_up': ('downtrend_rebound', '下跌结构反弹一买'),
        }
        if event in mapping:
            return mapping[event]
        if structure.get('market_structure_state') == 'downtrend':
            return 'downtrend_rebound', '下跌结构反弹一买'
    if code == 'SELL1':
        mapping = {
            'choch_down': ('choch_reversal', 'CHoCH 一卖'),
            'bos_down': ('bos_reversal', 'BOS 一卖'),
            'pullback_confirmed_down': ('confirmed_reversal', '回踩确认一卖'),
            'failed_break_down': ('uptrend_pullback', '上涨结构回落一卖'),
        }
        if event in mapping:
            return mapping[event]
        if structure.get('market_structure_state') == 'uptrend':
            return 'uptrend_pullback', '上涨结构回落一卖'
    return None, None
```

- [ ] **Step 4: Thread optional structure into `signal_series` and `signal_for_history`**

Change signatures:

```python
def signal_series(history, structure=None):
```

and:

```python
def signal_for_history(history, structure=None):
```

Change context calculation:

```python
        context, context_label = _structure_context(code, structure)
        if context is None:
            context, context_label = _trend_context(code, side, index, closes)
```

Change latest signal creation:

```python
signals = signal_series(data, structure=structure)
```

- [ ] **Step 5: Pass structure from dashboard data**

In `期货/dashboard_data.py`, replace record signal merge:

```python
record.update(signal_for_history(histories[record['ts_code']]))
record.update(structure_for_history(histories[record['ts_code']]))
```

with:

```python
structure = structure_for_history(histories[record['ts_code']])
record.update(structure)
record.update(signal_for_history(histories[record['ts_code']], structure=structure))
```

Make the same replacement in the `decisions` loop.

- [ ] **Step 6: Run tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_futures_signals.py'
python3 -m unittest discover -s tests -p 'test_dashboard_data.py'
```

Expected: PASS for both.

- [ ] **Step 7: Commit Task 4**

```bash
git add 期货/futures_signals.py 期货/dashboard_data.py 期货/tests/test_futures_signals.py
git commit -m "feat: label signals with market structure"
```

## Task 5: Frontend Structure Display

**Files:**
- Modify: `期货/frontend/app.mjs`
- Modify: `期货/frontend/opportunity-workbench.mjs` if opportunity card reasons need structure copy
- Modify: `期货/frontend/opportunity-workbench.test.mjs`

- [ ] **Step 1: Add failing frontend test for structure labels in opportunity rows**

In `期货/frontend/opportunity-workbench.test.mjs`, add a test near existing row-building tests:

```javascript
test('opportunity reasons include market structure event without promoting CHoCH',()=>{
 const item=buildOpportunityRows([base({
  ts_code:'JD.DCE',
  market_structure_event:'choch_up',
  market_structure_event_label:'CHoCH 潜在多头转向',
  market_structure_priority:55,
  signal_context_label:'CHoCH 一买',
  state_v2:'PREPARE',
 })],{}).watch[0];

 assert.equal(item.queue,'watch');
 assert.ok(item.reasons.some(reason=>reason.includes('CHoCH 潜在多头转向')));
});
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
node --test frontend/opportunity-workbench.test.mjs
```

Expected: FAIL because reasons do not include market structure event yet.

- [ ] **Step 3: Add structure text helpers in `app.mjs`**

Add near `technicalSignalText`:

```javascript
function structureSignalText(row){
 const event=row.market_structure_event_label||row.market_structure_label||'—';
 const quality=row.breakout_quality&&row.breakout_quality!=='unknown'?`质量 ${row.breakout_quality}`:'';
 const level=row.market_structure_break_level!=null?`破位 ${fmt(row.market_structure_break_level)}`:'';
 const invalid=row.market_structure_invalid_level!=null?`失效 ${fmt(row.market_structure_invalid_level)}`:'';
 return [event,quality,level,invalid].filter(Boolean).join(' / ')||'—';
}
```

In `decisionTable`, change the technical signal cell to include structure below existing levels:

```javascript
  <td class="${signalClass(row)}">${technicalSignalText(row).label}<span class="contract">${structureSignalText(row)}</span></td>
```

In `metricBlocks`, add structure fields after `技术信号`:

```javascript
['市场结构', row.market_structure_label],
['结构事件', row.market_structure_event_label],
['结构破位 / 失效', `${fmt(row.market_structure_break_level)} / ${fmt(row.market_structure_invalid_level)}`],
['突破质量', row.breakout_quality],
```

- [ ] **Step 4: Add structure reason in `opportunity-workbench.mjs`**

Inside the reason-building function, add:

```javascript
 if(record.market_structure_event_label && record.market_structure_event && record.market_structure_event!=='none'){
  reasons.push(`市场结构：${record.market_structure_event_label}`);
 }
```

Do not move a CHoCH-only record to `focus`. Keep existing queue rules unless `state_v2` and existing validations already qualify.

- [ ] **Step 5: Run frontend tests**

Run:

```bash
node --test frontend/opportunity-workbench.test.mjs
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add 期货/frontend/app.mjs 期货/frontend/opportunity-workbench.mjs 期货/frontend/opportunity-workbench.test.mjs
git commit -m "feat: show market structure context"
```

## Task 6: Chart Structure Markers And Tooltip

**Files:**
- Modify: `期货/frontend/charts.mjs`
- Modify: `期货/frontend/charts.test.mjs`
- Modify: `期货/frontend/app.mjs`

- [ ] **Step 1: Add chart helper test**

In `期货/frontend/charts.test.mjs`, update import:

```javascript
import {zoomRange, normalizePriceLevels, priceFromPointer, ema20ChartSeries, klineWheelIntent, ema20GapRuns, candleTickLabel, candleTooltipDate, structureEventLabel} from './charts.mjs';
```

Add:

```javascript
test('structureEventLabel prefers event label and levels',()=>{
 assert.equal(structureEventLabel({
  label:'CHoCH 潜在多头转向',
  quality:'weak',
  break_level:111,
  invalid_level:103,
 }), 'CHoCH 潜在多头转向 · weak · 破位 111 · 失效 103');
});
```

- [ ] **Step 2: Run chart test and verify failure**

Run:

```bash
node --test frontend/charts.test.mjs
```

Expected: FAIL because `structureEventLabel` is not exported.

- [ ] **Step 3: Add chart helper and input support**

In `期货/frontend/charts.mjs`, export:

```javascript
export function structureEventLabel(event){
 const parts=[event?.label||event?.event, event?.quality, event?.break_level!=null?`破位 ${event.break_level}`:'', event?.invalid_level!=null?`失效 ${event.invalid_level}`:''].filter(Boolean);
 return parts.join(' · ');
}
```

Change `renderCandlestickChart` signature:

```javascript
export function renderCandlestickChart(container,{candles=[],moving={},signals=[],levels=[],measuredMoves=[],mlSignals=[],structureEvents=[]},{window=80,title='K线图',interactive=false,activity=true,onLevelChange,wheelMode='zoom',onNavigate,fitHeight=false}={}){
```

Inside `draw`, after `visibleMlSignals`, add:

```javascript
const visibleStructureEvents=(structureEvents||[]).filter(event=>visibleDates.has(event.trade_date));
const structureEventsByDate=new Map();
for(const event of visibleStructureEvents){
 const list=structureEventsByDate.get(event.trade_date)||[];
 list.push(event);structureEventsByDate.set(event.trade_date,list);
}
```

Add structure close values to `basePrices`:

```javascript
.concat(visibleStructureEvents.map(event=>event.close).filter(Number.isFinite))
```

Render markers after ML markers:

```javascript
visibleStructureEvents.forEach(event=>{
 const index=rows.findIndex(row=>row[0]===event.trade_date);if(index<0||!Number.isFinite(Number(event.close)))return;
 const px=x(index),py=y(Number(event.close)),color=event.side==='long'?'#2563eb':event.side==='short'?'#b45309':'#64748b';
 svg.append(element('rect',{x:px-5,y:py-5,width:10,height:10,fill:'#fff',stroke:color,'stroke-width':1.8,transform:`rotate(45 ${px} ${py})`,'data-structure-event':''}));
 svg.append(element('text',{x:px,y:py-11,'text-anchor':'middle','class':'structure-event-label',fill:color},event.event?.startsWith('bos')?'BOS':event.event?.startsWith('choch')?'CH':'PA'));
});
```

In tooltip loop, add:

```javascript
for(const event of structureEventsByDate.get(row[0])||[]){
 const item=document.createElement('div'),l=document.createElement('span'),v=document.createElement('span');
 l.textContent='市场结构';v.textContent=structureEventLabel(event);item.append(l,v);tip.appendChild(item);
}
```

- [ ] **Step 4: Pass structure events from app chart input**

In `期货/frontend/app.mjs`, update `chartInput(row)`:

```javascript
return {candles:data.candles[codeOf(row)]||[],moving:data.moving?.[codeOf(row)]||{},signals:data.technical_signals?.[codeOf(row)]||[],levels:chartLevels(row),measuredMoves:data.measured_moves?.[codeOf(row)]?.moves||[],mlSignals:data.ml_price_action?.[codeOf(row)]||[],structureEvents:data.market_structure_events?.[codeOf(row)]||[]};
```

- [ ] **Step 5: Run chart tests**

Run:

```bash
node --test frontend/charts.test.mjs
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```bash
git add 期货/frontend/charts.mjs 期货/frontend/charts.test.mjs 期货/frontend/app.mjs
git commit -m "feat: annotate charts with market structure"
```

## Task 7: Full Verification And Local Service Check

**Files:**
- Verify only unless a test exposes a defect.

- [ ] **Step 1: Run backend unit tests for touched modules**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_market_structure.py'
python3 -m unittest discover -s tests -p 'test_futures_signals.py'
python3 -m unittest discover -s tests -p 'test_dashboard_data.py'
```

Expected: all PASS.

- [ ] **Step 2: Run frontend tests for touched modules**

Run:

```bash
node --test frontend/charts.test.mjs frontend/opportunity-workbench.test.mjs
```

Expected: all PASS.

- [ ] **Step 3: Verify schema versions reject old cache**

Run:

```bash
python3 - <<'PY'
from dashboard_data import CHART_SCHEMA_VERSION, PAYLOAD_SCHEMA_VERSION, chart_schema_current, payload_schema_current
print(CHART_SCHEMA_VERSION, PAYLOAD_SCHEMA_VERSION)
print(chart_schema_current({'chart_schema_version': CHART_SCHEMA_VERSION - 1}))
print(payload_schema_current({'payload_schema_version': PAYLOAD_SCHEMA_VERSION - 1}))
PY
```

Expected: first line prints current versions, then `False`, then `False`.

- [ ] **Step 4: Restart dashboard service**

Run:

```bash
./stop_mac.sh
./start_mac.sh
```

Expected: service starts at `http://127.0.0.1:8799/index.html`.

- [ ] **Step 5: Verify API exposes market structure fields**

Run:

```bash
curl --max-time 10 -fsS http://127.0.0.1:8799/api/data | rg -o 'market_structure_event_label|market_structure_events' | head
```

Expected: output contains `market_structure_event_label` or `market_structure_events`.

- [ ] **Step 6: Final commit if fixes were needed**

If verification required fixes, commit them:

```bash
git add 期货/market_structure.py 期货/dashboard_data.py 期货/futures_signals.py 期货/frontend/app.mjs 期货/frontend/charts.mjs 期货/frontend/opportunity-workbench.mjs 期货/tests/test_market_structure.py 期货/tests/test_futures_signals.py 期货/tests/test_dashboard_data.py 期货/frontend/charts.test.mjs 期货/frontend/opportunity-workbench.test.mjs
git commit -m "fix: verify market structure integration"
```

Expected: no commit is needed if all previous task commits already contain the final verified state.

## Spec Coverage Self-Review

- Market structure states HH/HL, LH/LL, and range are covered in Tasks 1 and 2.
- CHoCH, BOS, failed break, and pullback confirmation are covered in Task 2.
- Key levels and invalidation fields are covered in Tasks 2 and 3.
- BUY1/SELL1 reinterpretation is covered in Task 4.
- Dashboard/detail/chart display is covered in Tasks 5 and 6.
- Cache invalidation is covered in Task 3 and verified in Task 7.
- Option priority guardrail is covered by Task 5: CHoCH appears in reasons but does not automatically promote to focus.
