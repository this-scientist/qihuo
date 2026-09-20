# Option Pages Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the option scanner and option watch pages so they support the main Market Radar -> Commodity Detail -> T-chain -> Option Detail workflow without losing option scores or key Greeks/IV/liquidity metrics.

**Architecture:** Keep existing API and scoring code. Refactor only the two legacy option pages' presentation: scanner becomes a candidate validation page with advanced radars folded away, and options becomes a single-symbol option detail page with core filters visible and advanced controls collapsed.

**Tech Stack:** Static HTML, ES modules, existing local API, Playwright browser checks, Node test runner, Python unittest.

---

### Task 1: Browser Contract

**Files:**
- Modify: `tests/check_options_expiry_browser.py`

- [ ] Add assertions that `/scanner.html` shows the simplified "期权候选验证" page, hides advanced radars by default, and still renders candidate details with score breakdown and contracts.
- [ ] Add assertions that `/options.html` shows the simplified "期权明细" page, keeps core filters, hides advanced filters by default, and still renders tradability, Greeks/IV/liquidity, underlying chart, and payoff detail.
- [ ] Run the browser check and confirm it fails against the current verbose pages.

### Task 2: Simplify Scanner Page

**Files:**
- Modify: `frontend/scanner.html`
- Modify: `frontend/scanner.mjs`
- Modify: `frontend/style.css`

- [ ] Rename the page to "期权候选验证".
- [ ] Keep only direction tabs that support the main decision flow by default: 做多候选, 做空候选, 结构复核.
- [ ] Move 过度延伸, 反转雷达, and detailed structure radar behind one collapsed "高级雷达" section.
- [ ] Keep the candidate table, ten-signal breakdown, structure breakdown, 10x potential, and candidate contract tables.
- [ ] Keep links into the option detail page.

### Task 3: Simplify Options Page

**Files:**
- Modify: `frontend/options.html`
- Modify: `frontend/options.mjs`
- Modify: `frontend/style.css`

- [ ] Rename the page to "期权明细".
- [ ] Show only the core controls by default: 品种, 方向, 剩余天数, 可做性, 排序.
- [ ] Move month identity, alignment, liquidity, moneyness, rate, and date shortcut buttons into collapsed advanced controls.
- [ ] Keep the option score table and selected option detail area with tradability breakdown, underlying chart, payoff chart, scenarios, Greeks, IV, volume, and OI.
- [ ] Shorten long explanatory copy into compact "评分口径" and "数据限制" disclosures.

### Task 4: Verification

**Files:**
- Test: `tests/check_options_expiry_browser.py`
- Test: `tests/check_dashboard_browser.py`

- [ ] Run `node --check frontend/options.mjs frontend/scanner.mjs`.
- [ ] Run `..\ .venv\Scripts\python.exe tests\check_options_expiry_browser.py`.
- [ ] Run `..\ .venv\Scripts\python.exe tests\check_dashboard_browser.py`.
- [ ] Run `..\ .venv\Scripts\python.exe -m unittest discover -s tests -v`.
- [ ] Run `node --test frontend/options-filter.test.mjs frontend/rules.test.mjs frontend/sortable.test.mjs`.
