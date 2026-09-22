# Unified Commodity Factors

Goal: one commodity overview with independent price-trend and commodity-structure conclusions, explicit units, and reproducible historical evidence.

Main horizon: 5-20 trading days unless the user supplies another horizon. Daily snapshots are not real-time quotes. Scores are evidence indices, not probabilities.

Implementation:
1. Test daily return, RPS5, missing data, and invariant trend direction under OI/curve changes. Add a price-only direction model with explicit component contributions; compare with simple momentum/MA baselines and component ablations on chronological historical blocks. Use next-session open, nonoverlapping holding windows, and disclose current-basket bias. Do not optimize weights on the evaluation period.
2. Preserve independent structure long/short evidence. Combine spread and Carry as one curve group to avoid double weighting. OI is participation evidence, not proof of buyer/seller identity. Missing factors remain missing with coverage.
3. Wire the canonical decision into overview, scanner, structure review, lifecycle, and cached payload migration. Keep original directional scoring rows as factor inputs only.
4. Add snapshot daily change, RPS5/20, RPS20 five-session change, OI levels/change, pair spread/Carry, sector, score, stage, and underlying burst index. Separate option convexity scores from underlying burst.
5. Consolidate navigation into overview/detail/options/history, use overview filters for candidates. Remove fake position data, fake state transitions, and nonfunctional settings from navigation. Keep legacy pages accessible as tools.
6. Run focused calculation/integration tests, historical audit, and desktop/mobile browser acceptance. Deliver the report, formulas, limitations, and a running local URL.

Acceptance: LC may show price trend short and structure long, with identical conclusions on every page and an explicit divergence label. Raw RPS is never silently flipped. Spread changes use price units; Carry changes use percentage points. OI levels name their contract scope; trader long/short positions are marked unavailable when absent.
