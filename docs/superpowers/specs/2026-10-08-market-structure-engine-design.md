# Market Structure Engine Design

## Goal

Add a price-action-first market structure engine so the system can explain whether a `一买` is only a rebound inside a downtrend, an early CHoCH warning, a BOS structure break, or a confirmed reversal after pullback.

The design uses a lenient detection and strict ranking approach:

- Detect early structural changes as soon as they appear.
- Keep early changes in observation states instead of treating them as confirmed reversals.
- Promote option priority only after BOS or pullback confirmation.
- Keep EMA20, ADX, RPS, OI, volume, term structure, and option Greeks as validation layers, not the primary structure decision.

## Non-Goals

- Do not add another composite technical indicator score as the main decision driver.
- Do not replace option liquidity, IV, scenario RR, or execution checks.
- Do not claim CHoCH is a bottom. CHoCH is only a warning that the previous structure has been damaged.
- Do not use future bars. Every structure label must be available as of the signal date.

## Current Gap

The current system can emit `BUY1 / 一买` and can label it using EMA20 context, but that still treats the market mostly through indicator state. A weak rebound and a genuine structure reversal can share similar EMA20 slope, ADX, RPS, and recent returns.

The missing layer is explicit market structure:

- Are swing highs and lows still forming LH/LL or HH/HL?
- Did price break the most recent lower high or higher low?
- Was the break a CHoCH, a BOS, or a failed break?
- Did price retest the broken level and hold?
- Where is the nearest invalidation swing?

## Data Inputs

Use only existing daily OHLCV/OI history at first:

- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `vol`
- `oi`
- optional existing `atr14` if available, otherwise compute locally

The first implementation can reuse the existing swing-point style in `measured_move.find_swings`, but the market structure engine should live in its own backend module, for example `market_structure.py`, because measured move and structure classification have different outputs and consumers.

## Swing Point Rules

The first version should use lenient but deterministic swing detection:

- Default `pivot_strength = 2`.
- A swing high is a bar whose high is greater than the highs on both sides within the pivot window.
- A swing low is symmetric.
- Consecutive same-kind pivots are merged by keeping the more extreme point.
- Optional ATR filtering may be added after the basic version, but should not block the first implementation.

The latest unconfirmed bars cannot create confirmed swing points because right-side bars are not available yet. However, they may create provisional events when the current close breaks a previously confirmed swing level.

## Structure State

Each symbol should receive a latest market structure summary:

- `market_structure_state`
  - `uptrend`: recent confirmed swings show HH/HL behavior.
  - `downtrend`: recent confirmed swings show LH/LL behavior.
  - `range`: alternating or unclear swings.
  - `potential_reversal`: a CHoCH has appeared but BOS or pullback confirmation is not complete.

- `market_structure_side`
  - `long`
  - `short`
  - `neutral`

- `market_structure_label`
  - Examples: `下跌结构`, `上涨结构`, `震荡结构`, `潜在多头转向`, `潜在空头转向`.

The structure state should be displayed separately from EMA20 state. EMA20 may validate or conflict with structure, but should not overwrite it.

## Structure Events

The engine should emit the latest important event:

- `none`: no active structure event.
- `choch_up`: price closes above the most recent meaningful lower high while prior structure is down or range.
- `choch_down`: price closes below the most recent meaningful higher low while prior structure is up or range.
- `bos_up`: price closes above a major prior swing high after CHoCH or inside an uptrend continuation.
- `bos_down`: price closes below a major prior swing low after CHoCH or inside a downtrend continuation.
- `pullback_confirmed_up`: after `bos_up`, price pulls back without closing below the broken structure level or invalidation swing, then closes back upward.
- `pullback_confirmed_down`: mirrored short case.
- `failed_break_up`: price trades above a structure level but closes back below it.
- `failed_break_down`: mirrored short case.

The event label should be human-readable:

- `下跌结构反弹`
- `CHoCH 潜在多头转向`
- `BOS 多头结构突破`
- `BOS 后回踩确认`
- `上破失败`

## Lenient Detection, Strict Ranking

The user-selected direction is:

> Detect early, rank conservatively.

That means:

- CHoCH should appear early in the UI and in candidate explanations.
- CHoCH alone should not make a buy-side option candidate high priority.
- BOS may move a symbol into research focus if validation is not poor.
- BOS plus pullback confirmation is the first structure state that may materially raise buy-side option priority.

Suggested priority scale:

- `0-20`: structure unclear or opposite.
- `25-40`: rebound against existing structure.
- `45-60`: CHoCH warning.
- `65-80`: BOS structure break.
- `85-100`: BOS plus pullback confirmation.

These values should affect sorting and explanations, not override hard option filters.

## Reinterpreting BUY1

`BUY1 / 一买` should no longer be interpreted from EMA20 context alone.

For long signals:

- If market structure remains LH/LL and no CHoCH exists:
  - `signal_context = downtrend_rebound`
  - label: `下跌结构反弹一买`
  - option priority: low.

- If price closes above the most recent lower high:
  - `signal_context = choch_reversal`
  - label: `CHoCH 一买`
  - option priority: observation.

- If price closes above a major prior swing high:
  - `signal_context = bos_reversal`
  - label: `BOS 一买`
  - option priority: research focus if validation is acceptable.

- If BOS has occurred and pullback holds:
  - `signal_context = confirmed_reversal`
  - label: `回踩确认一买`
  - option priority: eligible for higher ranking.

Short signals use mirrored rules.

## Breakout Quality

Breakout quality should be a separate output, not mixed into event detection:

- `breakout_quality`
  - `clean`
  - `weak`
  - `failed`
  - `unknown`

Initial quality inputs:

- Close position within the bar.
- Body size relative to range or ATR.
- Close beyond the broken swing level.
- Volume ratio.
- OI change.

For example, a close barely above the swing high with low volume and falling OI can still be `choch_up`, but quality should be `weak`. This lets the UI say: structure changed, but participation is poor.

## Invalidation Levels

Every active event should publish an invalidation level:

- For long CHoCH or BOS: nearest relevant swing low.
- For short CHoCH or BOS: nearest relevant swing high.
- For pullback confirmation: the pullback low/high becomes the more precise invalidation level.

Fields:

- `market_structure_break_level`
- `market_structure_invalid_level`
- `market_structure_last_swing_high`
- `market_structure_last_swing_low`

These levels can later feed option scenario stop prices, but the first implementation should only publish and display them.

## Decision Flow

The revised decision order should be:

1. Market structure:
   - uptrend, downtrend, range, potential reversal.
   - CHoCH, BOS, pullback confirmation, failed break.

2. Trend and participation validation:
   - EMA20 direction and distance.
   - ADX / DI.
   - RPS.
   - volume ratio.
   - OI change.

3. Key location and trigger:
   - broken swing level.
   - pullback level.
   - invalidation level.
   - support/resistance from existing local levels.

4. Option execution:
   - liquidity.
   - Delta / Gamma / Theta.
   - IV and scenario RR.
   - DTE and spread limitations.

## Backend Integration

Add a backend structure module that exposes:

```python
structure_for_history(history) -> dict
structure_series(history) -> list[dict]
```

`structure_for_history` should be merged into each dashboard `record` and `decision` inside `dashboard_data.build_payload`.

`structure_series` should feed chart annotations, similar to existing `chart_signals`, so the K-line can show CHoCH, BOS, and pullback confirmation markers.

The payload schema version must be bumped when these fields are added, so old cached bundles do not hide the new structure fields.

## Frontend Integration

The first UI pass should be modest:

- Add market structure fields to the detail metrics area.
- Show structure label in the market table near `技术信号`.
- Add chart markers for CHoCH, BOS, and pullback confirmation.
- In tooltips, show event label, break level, invalidation level, and quality.
- In option/opportunity explanations, say whether a buy signal is a rebound, CHoCH, BOS, or confirmed reversal.

The UI should not make a landing page or a new separate analysis page for this first pass. The structure engine should strengthen the existing dashboard.

## Tests

Backend tests:

- Detect downtrend from LH/LL swings.
- Detect uptrend from HH/HL swings.
- Detect range when swings alternate without clear progression.
- Detect `choch_up` when price closes above the latest lower high.
- Detect `bos_up` after a CHoCH or continuation break.
- Detect `pullback_confirmed_up` after BOS and a held retest.
- Mirror all important short cases.
- Verify no future bars are used for historical event labels.
- Verify old payload schema versions are rejected.

Frontend tests:

- Dashboard table renders the structure label when present.
- Detail metrics show break and invalidation levels.
- Chart tooltip shows CHoCH/BOS/pullback labels.
- Existing EMA20 and technical signal displays remain compatible when structure fields are missing.

## Risks And Guardrails

- Swing rules can be too sensitive in noisy commodities. Keep the first version lenient but expose quality and priority instead of hard promotion.
- CHoCH is not a bottom. UI copy must call it `潜在转向`, not `反转确认`.
- Low ADX and low volume/OI participation should not suppress CHoCH detection, but should reduce quality and priority.
- Cache invalidation is required; otherwise the frontend may keep showing old payloads.
- Option recommendations must continue to respect existing liquidity and scenario RR filters.

## Acceptance Criteria

- A `BUY1` in a still-valid downtrend is labeled as `下跌结构反弹一买`.
- A `BUY1` that breaks the most recent lower high is labeled as `CHoCH 一买`.
- A `BUY1` that breaks a major structure high is labeled as `BOS 一买`.
- A `BUY1` after BOS and held pullback is labeled as `回踩确认一买`.
- The detail page shows market structure state, latest event, break level, invalidation level, and breakout quality.
- The system can detect early structural warnings without promoting them to high-priority buy-side option trades until confirmation improves.
