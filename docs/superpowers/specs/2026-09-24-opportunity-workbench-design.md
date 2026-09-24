# Opportunity Workbench Page Design

## Goal

Make the dashboard easier to use for finding researchable futures targets without changing the existing factor collection, data pipeline, payload fields, MySQL schema, or historical snapshot format.

The change is a page-level presentation layer over the existing `/api/data`, `/api/options`, and `/api/execution` payloads. Existing factor tables, scanner pages, option pages, and full market matrix remain available for detailed review.

## Non-Goals

- Do not delete, rename, or stop computing existing factors.
- Do not change collection logic, database tables, snapshot structure, or cache keys.
- Do not change Tushare, Sina, option-chain, or historical validation data flows.
- Do not reinterpret historical records by writing new fields into persisted payloads.
- Do not remove the current full indicator table; move it behind a clearer "full market matrix" section or mode.

## User Experience

The default home view becomes a research-oriented opportunity workbench. It groups commodities into four queues:

1. **重点研究**: Direction is clear and not structurally conflicted. The symbol is in `START` or `TREND`, or a high-quality `PREPARE`, and at least one expression path is plausible.
2. **等待位置**: Directional logic exists, but current position is unattractive, the trend is overextended, or intraday executability is weak.
3. **启动观察**: The symbol is in `PREPARE` or has partial evidence from RPS, ADX, OI, breakout, or structure, but is not yet actionable.
4. **风险回避**: `EXHAUST`, structural conflict, severe data gaps, counter-trend option expression, overheated IV, very short DTE, or thin option liquidity.

Each card shows only the decision layer:

- Commodity name, main contract, sector
- Direction and state
- Suggested status: research, wait, observe, avoid
- Three concise reasons from existing fields
- Main risk or missing evidence
- Next step: open detail, open T-chain, open full matrix, or wait

The full indicator table remains available as "全市场矩阵" for advanced screening and audit.

## Option Review Rules

This design does not change raw option metrics. It only changes how option readiness affects page grouping.

The page-level option review applies these display gates:

- No option chain: do not present the symbol as option-actionable; it may still appear as futures research.
- Counter-trend option: default to risk/avoid for option expression, matching the existing score cap behavior.
- Thin liquidity: if `tradability.depth` is below the current weak-liquidity threshold, do not count the contract as actionable.
- IV overheated: if tradability tags include `IV透支`, degrade option expression to observe/avoid.
- Very short DTE: if DTE is less than or equal to two days, classify as high-risk末日轮 and keep it out of normal action queues.
- Normal DTE bands remain visible in option detail pages; the workbench only decides whether the symbol has a plausible option expression.

## Frontend Architecture

Add a small front-end derivation layer in `frontend/app.mjs`:

- `buildOpportunityRows(data, execution, options)` derives queue membership from existing records.
- `optionExpressionStatus(record, optionRows)` summarizes whether options are usable, watch-only, missing, or avoid.
- `reasonList(record, optionStatus, executionItem)` extracts up to three plain-language reasons.
- `riskList(record, optionStatus, executionItem)` extracts the most important warning.

These functions are pure and testable with existing front-end test patterns.

No backend API is required for the first implementation. If performance becomes an issue later, the same logic can move behind a read-only API without changing schemas.

## Testing

Add front-end unit tests for the pure derivation functions:

- START/TREND with aligned structure enters `重点研究`.
- PREPARE with partial evidence enters `启动观察`.
- Overextended or poor execution enters `等待位置`.
- Structure conflict or EXHAUST enters `风险回避`.
- Missing option chain does not block futures research but prevents option-actionable labeling.
- Counter-trend, thin liquidity, IV overheated, and DTE <= 2 downgrade option expression.

Run existing Python and front-end tests touched by this work.

## Rollout

Keep the current navigation labels, but make the default `market` view render the opportunity workbench first. Place the full market matrix below it or behind a visible mode switch. Existing "候选池", "商品详情", "T型报价", "期权机会", scanner, and research pages stay accessible.
