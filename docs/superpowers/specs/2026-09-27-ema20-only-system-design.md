# EMA20-Only System Design

## Goal

The system uses EMA20 as its only moving average. No other moving-average calculation, field, label, chart line, rule, score, database column, API payload field, test fixture, or user-facing explanation remains in the active system.

EMA20 is not merely a chart overlay. Its direction, strength, and the current price's ATR-normalized distance from it are primary evidence for whether a directional opportunity is actionable.

## Scope

This change covers the indicator pipeline, legacy strategy score, unified trend model, trend phases, decision payloads, scanner factors, chart payloads, futures and option-underlying charts, MySQL persistence/import, cache validation, tests, and current user documentation.

Historical design records under `docs/superpowers/` remain historical records and are not rewritten. The temporary untracked research probe is unrelated and remains untouched.

## Canonical EMA20 Fields

The canonical price indicator is calculated causally with pandas:

```python
ema20 = close.ewm(span=20, adjust=False).mean()
```

The active system uses these names and meanings:

- `ema20`: 20-session exponential moving average.
- `ema20_slope5_atr`: `(ema20[t] - ema20[t-5]) / atr14[t]`; positive is rising and negative is falling.
- `ema20_distance_atr`: `(close[t] - ema20[t]) / atr14[t]`; positive is above EMA20 and negative is below it.
- `directional_ema20_slope5_atr`: the slope multiplied by the evaluated direction (`+1` for long, `-1` for short).
- `directional_ema20_distance_atr`: the distance multiplied by the evaluated direction.

Invalid or zero ATR produces a missing value, never zero and never an automatic pass.

## Strength and Distance Classification

EMA20 strength uses the absolute five-session slope in ATR units:

- Strong: at least `0.75 ATR`.
- Medium: at least `0.25 ATR` and below `0.75 ATR`.
- Weak: below `0.25 ATR`.

For a proposed long or short direction, actionability uses directional values:

- `actionable`: price is on the correct side of EMA20, EMA20 slope is in the same direction and at least medium, distance is from `0` through `2 ATR`, and the existing mandatory ADX/DI, RPS, breakout, liquidity, and coverage gates pass.
- `wait_pullback`: direction and quality gates pass, but distance is above `2 ATR` through `3 ATR`.
- `do_not_chase`: direction and quality gates pass, but distance is above `3 ATR`.
- `not_actionable`: price is on the wrong side, EMA20 is flat/weak or points the wrong way, required data is missing, or another mandatory quality gate fails.

Boundary comparisons are inclusive at `0.25`, `0.75`, `2`, and `3` as described above. Thresholds live in the existing settings/configuration boundary rather than being duplicated across modules.

The conclusion includes a stable machine value, a Chinese display label, and explicit reasons. EMA20 failures are listed before secondary-factor failures so the primary reason is immediately visible.

## Strategy and Trend Model Changes

All simple moving averages and all multi-average relationships are removed. This includes MA20/MA60/MA120 values, their slopes, moving-average spreads, moving-average spread expansion, and MA20/MA60 crossings.

The price/trend component keeps its existing group budget but is rebuilt from two equally weighted EMA20 inputs:

1. Price distance from EMA20, normalized by ATR14.
2. EMA20 five-session slope, normalized by ATR14.

The old moving-average score is similarly rebuilt from price position versus EMA20 and EMA20 directional strength. Its total score budget remains unchanged so unrelated ranking thresholds do not shift solely because fields were removed.

The startup moving-average crossing signal becomes a price/EMA20 crossing signal: within the configured recent window, price must cross EMA20 in the evaluated direction. The field and label are renamed to describe a price crossing rather than a moving-average crossing.

Trend confirmation no longer checks medium- or long-term moving-average ordering. It requires price and EMA20 alignment plus the existing ADX/DI and RPS quality gates. Phase classification no longer distinguishes phases using long-term moving-average ordering. Its rationale instead names EMA20 direction/strength, price distance, trend quality, and breakout state.

## UI and API

Candlestick and option-underlying charts draw one overlay only: EMA20. Titles and legends explicitly say `EMA20`, not the generic term “moving averages.”

The opportunity and detail views prominently show:

- EMA20 direction: rising, falling, or flat.
- EMA20 strength: strong, medium, weak, or unavailable.
- EMA20 five-session change in ATR units.
- Current directional distance from EMA20 in ATR units.
- Actionability: 可做、等待回踩、不可追、不可做.
- A concise reason, with EMA20 evidence first.

Scanner factors and rule editors expose EMA20 and its new derived fields. Removed moving averages and their derived fields are absent from selectable factors and public payloads.

The payload and chart schema versions are incremented. Cached payloads from the previous moving-average schema are rejected and rebuilt.

## Persistence and Migration

The active MySQL schema and import code store `ema20` and the new EMA20-derived values needed for audit. MA20, MA60, MA120, and their moving-average-only derivatives are removed from active schema declarations, insert statements, and reads.

Existing installations receive an explicit idempotent schema migration that adds the EMA20 columns and removes the obsolete moving-average columns after the new columns are available. Historical EMA20 values are regenerated from source price history; simple-moving-average values are not copied or relabeled as EMA20.

The migration must identify exact table and column names before alteration, run inside the existing schema-management boundary, and be safe to rerun. If source history is unavailable, EMA20 stays missing and the actionability result is `not_actionable` with a missing-data reason.

## Compatibility

There is no public compatibility alias from `ma20` to `ema20`, because an alias would preserve misleading terminology and violate the EMA20-only requirement. Consumers in this repository migrate atomically with the payload schema bump.

Unrelated indicators whose periods contain 20, 60, or 120—such as returns, RPS, breakout windows, and volume lookbacks—remain unchanged. They are not moving averages.

Existing unrelated option-contract selection changes in the working tree are preserved. Edits to shared frontend files must be applied around those changes without overwriting them.

## Testing

Implementation follows test-driven development. Tests first demonstrate failure for:

- EMA20 uses exponential weighting and differs from an SMA20 on non-linear data.
- No MA60/MA120 or old MA-derived fields appear in indicator output, public factors, moving/chart payloads, or persistence mappings.
- EMA20 slope and distance use ATR normalization and propagate missing ATR.
- Strength thresholds classify values correctly at and around `0.25` and `0.75`.
- Actionability classifies correct-side tradable distance, pullback waiting, overextension, wrong-side price, weak/opposite slope, missing values, and failed secondary gates.
- Long and short behavior is exactly mirrored.
- Recent price/EMA20 crossing replaces moving-average crossing.
- Trend scoring and phase classification require no removed moving-average fields.
- Charts render only EMA20.
- Old payload/chart schema versions are rejected.
- MySQL schema migration and imports use EMA20-only columns and remain idempotent.

After focused tests pass, run the complete Python and frontend test suites and scan active code and current documentation for forbidden moving-average identifiers and labels.

## Success Criteria

- Active system code, schemas, payloads, UI, tests, and current documentation contain no MA20, MA60, MA120, or generic multi-moving-average behavior.
- EMA20 is computed once with the canonical formula and used consistently.
- Every evaluated opportunity exposes EMA20 strength, price distance, actionability, and a reason.
- Old caches cannot leak obsolete moving-average data.
- Existing non-moving-average behavior and unrelated working-tree changes remain intact.
