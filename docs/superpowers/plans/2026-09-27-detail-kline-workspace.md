# Commodity Detail K-Line Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the commodity detail page into a K-line-first workspace with a left commodity navigator, scoped wheel/keyboard switching, Ctrl+wheel chart zoom, and all decision/holding/structure information below the chart.

**Architecture:** Add one pure navigation module for ordering, filtering, boundary movement, and shortcut guards. Extend the chart renderer with an explicit wheel policy so it reports commodity navigation without knowing about application state. Keep DOM rendering and selection state in `app.mjs`, with CSS scoped under the new detail-workspace classes so existing option-page edits remain untouched.

**Tech Stack:** Browser-native ES modules, SVG chart renderer, Node 20 built-in test runner/assertions, plain HTML/CSS, Playwright CLI for browser acceptance.

---

## File map

- Create `期货/frontend/detail-navigation.mjs`: pure ordering, filtering, boundary navigation, wheel-step, and key-target guard functions.
- Create `期货/frontend/detail-navigation.test.mjs`: unit tests for all navigation behavior.
- Modify `期货/frontend/charts.mjs`: add a testable wheel-intent helper and a `navigate` wheel policy.
- Modify `期货/frontend/charts.test.mjs`: verify plain-wheel navigation and Ctrl+wheel zoom intent.
- Modify `期货/frontend/app.mjs`: render the workspace, bind the sidebar/chart/keyboard interactions, and keep the selected item visible.
- Modify `期货/frontend/style.css`: add the 220px rail, 60vh chart stage, below-chart analysis layout, and responsive rules.

The existing dirty changes in `app.mjs`, `style.css`, and option-page files belong to the user. Stage and commit only the files named by each task, and inspect their diffs before every commit.

### Task 1: Pure commodity navigation model

**Files:**
- Create: `期货/frontend/detail-navigation.mjs`
- Create: `期货/frontend/detail-navigation.test.mjs`

- [ ] **Step 1: Write the failing navigation tests**

Create `detail-navigation.test.mjs` with real records covering priority, strength, stable naming, search, and clamped boundaries:

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  orderedDetailRows,
  adjacentDetailRow,
  wheelStep,
  ignoresDetailShortcut,
} from './detail-navigation.mjs';

const row=(ts_code,name,status,slope,extra={})=>({
  ts_code,name,main_code:`${ts_code}-MAIN`,
  ema20_actionability:status,
  ema20_slope5_atr:slope,
  ...extra,
});

test('orders by actionability then absolute EMA20 strength and name',()=>{
  const rows=[
    row('D','丁','not_actionable',2),
    row('B','乙','actionable',.4),
    row('A','甲','actionable',.9),
    row('C','丙','wait_pullback',1.2),
    row('E','戊','do_not_chase',1.5),
  ];
  assert.deepEqual(orderedDetailRows(rows).map(item=>item.ts_code),['A','B','C','E','D']);
});

test('deduplicates products and filters name, product code, or contract code',()=>{
  const rows=[row('LC.GFE','碳酸锂','actionable',.8),row('LC.GFE','重复','not_actionable',0),row('CU.SHF','铜','actionable',.5,{main_code:'CU2611.SHF'})];
  assert.deepEqual(orderedDetailRows(rows).map(item=>item.ts_code),['LC.GFE','CU.SHF']);
  assert.deepEqual(orderedDetailRows(rows,'2611').map(item=>item.ts_code),['CU.SHF']);
  assert.deepEqual(orderedDetailRows(rows,'碳酸').map(item=>item.ts_code),['LC.GFE']);
});

test('moves one item and clamps at both ends without wrapping',()=>{
  const rows=[row('A','甲','actionable',.9),row('B','乙','actionable',.5)];
  assert.equal(adjacentDetailRow(rows,'A',1).ts_code,'B');
  assert.equal(adjacentDetailRow(rows,'B',1).ts_code,'B');
  assert.equal(adjacentDetailRow(rows,'A',-1).ts_code,'A');
});

test('wheel threshold produces a single direction',()=>{
  assert.equal(wheelStep(4),0);
  assert.equal(wheelStep(16),1);
  assert.equal(wheelStep(-16),-1);
});

test('shortcut guard ignores editing controls and open dialogs',()=>{
  assert.equal(ignoresDetailShortcut({tagName:'INPUT'}),true);
  assert.equal(ignoresDetailShortcut({tagName:'DIV',isContentEditable:true}),true);
  assert.equal(ignoresDetailShortcut({tagName:'DIV'},true),true);
  assert.equal(ignoresDetailShortcut({tagName:'DIV'}),false);
});
```

- [ ] **Step 2: Run the test and verify the red state**

Run:

```powershell
node 期货/frontend/detail-navigation.test.mjs
```

Expected: failure because `detail-navigation.mjs` does not exist.

- [ ] **Step 3: Implement the pure navigation module**

Create `detail-navigation.mjs`:

```js
const ACTION_RANK={actionable:0,wait_pullback:1,do_not_chase:2,not_actionable:3};
const text=value=>String(value??'').toLocaleLowerCase('zh-CN');

export function orderedDetailRows(records=[],query=''){
  const seen=new Set(),needle=text(query).trim();
  return records.filter(row=>{
    if(!row?.ts_code||seen.has(row.ts_code))return false;
    seen.add(row.ts_code);
    return !needle||text(`${row.name} ${row.ts_code} ${row.main_code}`).includes(needle);
  }).sort((a,b)=>
    (ACTION_RANK[a.ema20_actionability]??9)-(ACTION_RANK[b.ema20_actionability]??9)||
    Math.abs(Number(b.ema20_slope5_atr)||0)-Math.abs(Number(a.ema20_slope5_atr)||0)||
    String(a.name??a.ts_code).localeCompare(String(b.name??b.ts_code),'zh-CN')
  );
}

export function adjacentDetailRow(records,currentCode,step){
  if(!records.length)return null;
  const index=Math.max(0,records.findIndex(row=>row.ts_code===currentCode));
  const next=Math.max(0,Math.min(records.length-1,index+Math.sign(step)));
  return records[next];
}

export const wheelStep=(deltaY,threshold=8)=>Math.abs(deltaY)<threshold?0:deltaY>0?1:-1;

export function ignoresDetailShortcut(target,dialogOpen=false){
  const tag=String(target?.tagName||'').toUpperCase();
  return dialogOpen||Boolean(target?.isContentEditable)||['INPUT','TEXTAREA','SELECT','BUTTON'].includes(tag);
}
```

- [ ] **Step 4: Run the new tests and all current frontend tests**

Run:

```powershell
node 期货/frontend/detail-navigation.test.mjs
Get-ChildItem 期货/frontend -Filter '*.test.mjs' | Sort-Object Name | ForEach-Object { node $_.FullName; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
```

Expected: all tests exit 0.

- [ ] **Step 5: Commit the isolated navigation model**

```powershell
git add 期货/frontend/detail-navigation.mjs 期货/frontend/detail-navigation.test.mjs
git commit -m "feat: add commodity detail navigation model"
```

### Task 2: Explicit K-line wheel policy

**Files:**
- Modify: `期货/frontend/charts.mjs:108-230`
- Modify: `期货/frontend/charts.test.mjs:1-35`

- [ ] **Step 1: Add failing wheel-intent tests**

Import `klineWheelIntent` and add:

```js
test('K-line wheel navigates normally and zooms only with Control',()=>{
  assert.equal(klineWheelIntent({deltaY:40,ctrlKey:false},'navigate'),'next');
  assert.equal(klineWheelIntent({deltaY:-40,ctrlKey:false},'navigate'),'previous');
  assert.equal(klineWheelIntent({deltaY:40,ctrlKey:true},'navigate'),'zoom-out');
  assert.equal(klineWheelIntent({deltaY:-40,ctrlKey:true},'navigate'),'zoom-in');
  assert.equal(klineWheelIntent({deltaY:4,ctrlKey:false},'navigate'),'none');
  assert.equal(klineWheelIntent({deltaY:40,ctrlKey:false},'zoom'),'zoom-out');
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run `node 期货/frontend/charts.test.mjs`.

Expected: import error because `klineWheelIntent` is not exported.

- [ ] **Step 3: Implement the helper and renderer option**

Add this pure helper near `zoomRange`:

```js
export function klineWheelIntent({deltaY=0,ctrlKey=false},mode='zoom'){
  if(Math.abs(deltaY)<8)return 'none';
  if(mode==='navigate'&&!ctrlKey)return deltaY>0?'next':'previous';
  return deltaY>0?'zoom-out':'zoom-in';
}
```

Extend the renderer signature:

```js
export function renderCandlestickChart(
  container,
  {candles=[],moving={},signals=[],levels=[]},
  {window=80,title='K线图',interactive=false,activity=true,onLevelChange,wheelMode='zoom',onNavigate}={}
){
```

Replace the current interactive wheel listener with:

```js
overlay.addEventListener('wheel',event=>{
  const action=klineWheelIntent(event,wheelMode);
  if(action==='none')return;
  event.preventDefault();
  if(action==='next'||action==='previous'){
    onNavigate?.(action==='next'?1:-1);
    return;
  }
  const index=pointerIndex(event),factor=action==='zoom-in'?.75:1.34;
  range=zoomRange({...range,total:allRows.length},index,factor);
  draw();
},{passive:false});
```

- [ ] **Step 4: Run focused and full frontend tests**

Run `node 期货/frontend/charts.test.mjs`, then run every `*.test.mjs` as in Task 1.

Expected: all tests exit 0, including the legacy EMA20 reconstruction regression.

- [ ] **Step 5: Commit the chart behavior**

```powershell
git add 期货/frontend/charts.mjs 期货/frontend/charts.test.mjs
git commit -m "feat: add scoped K-line wheel controls"
```

### Task 3: Render and wire the detail workspace

**Files:**
- Modify: `期货/frontend/app.mjs:1-10,120-145,220-265,370-460,510-540`

- [ ] **Step 1: Import navigation functions and add detail state**

Add:

```js
import {orderedDetailRows,adjacentDetailRow,wheelStep,ignoresDetailShortcut} from './detail-navigation.mjs';
```

Extend state with `detailSearch:''` and add module-level `let detailWheelAt=0;`.

- [ ] **Step 2: Add the sidebar and navigation functions**

Add complete helpers before `renderDetail`:

```js
const detailRows=()=>orderedDetailRows(rows(),state.detailSearch);
const detailStatusLabel=row=>({actionable:'可做',wait_pullback:'等回踩',do_not_chase:'不可追',not_actionable:'不可做'}[row.ema20_actionability]||'不可做');

function detailSidebar(selected){
  const list=detailRows();let previous=null;
  const body=list.map(row=>{
    const label=detailStatusLabel(row),heading=label!==previous?`<div class="detail-group-label">${label}</div>`:'';
    previous=label;
    const ema=ema20Summary(row);
    return `${heading}<button class="detail-symbol ${codeOf(row)===codeOf(selected)?'active':''}" data-detail-code="${codeOf(row)}" aria-current="${codeOf(row)===codeOf(selected)?'true':'false'}"><span><strong>${escapeHtml(row.name)}</strong><small>${escapeHtml(codeOf(row))} · ${ema.direction}${ema.strength}</small></span><em>${label}</em></button>`;
  }).join('');
  return `<aside class="detail-sidebar" aria-label="商品列表"><div class="detail-sidebar-head"><strong>全部商品</strong><small>${list.length} 个 · 按交易机会排序</small></div><input id="detail-search" value="${escapeHtml(state.detailSearch)}" placeholder="搜索品种 / 代码" aria-label="搜索商品"><div class="detail-symbols">${body||'<p class="empty mini">没有匹配商品</p>'}</div><p class="detail-shortcut-help">列表或K线滚轮切换 · ↑↓切换 · K线Ctrl+滚轮缩放</p></aside>`;
}

function navigateDetail(step){
  const list=detailRows(),current=selectedRow(),next=adjacentDetailRow(list,codeOf(current),step);
  if(!next||codeOf(next)===codeOf(current))return;
  state.selected=codeOf(next);render();
  requestAnimationFrame(()=>document.querySelector('[aria-current="true"]')?.scrollIntoView({block:'nearest'}));
}

function navigateDetailByWheel(event){
  const step=wheelStep(event.deltaY),now=performance.now();
  if(!step)return;
  event.preventDefault();
  if(now-detailWheelAt<180)return;
  detailWheelAt=now;navigateDetail(step);
}
```

- [ ] **Step 3: Replace the two-column detail render with chart-first markup**

Extract the current holding, structure, and dialog markup into complete helpers without changing their fields:

```js
function holdingPanel(row){
  const items=[['主力OI（手）',count(row.main_oi)],['次主力OI（手）',count(row.secondary_oi)],['主次合计OI（手）',count(row.pair_oi)],['固定月对OI 5日',pct(row.oi_change5)],['固定月对OI 20日',pct(row.oi_change20)],['成交量比',fmt(row.volume_ratio)],['量价表现',row.structure_evidence?.oi?.state],['移仓迹象',row.rollover_transfer?'有':row.rollover_transfer===false?'无':'缺失']];
  return `<article class="decision-panel detail-holdings"><h2>量仓</h2><div class="structure-grid">${items.map(([label,value])=>`<div><span>${label}</span><strong>${value||'—'}</strong></div>`).join('')}</div>${renderHoldings(row.trader_positions)}</article>`;
}

function structurePanel(row){
  const items=[['结构得分',signed(row.structure_score)],['趋势 / 结构',structureText(row.structure_confirm)],['期限形态',structureText(row.structure)],['年化Carry',pct(row.carry_annualized)],['近月 / 远月',`${row.near_code||'—'} / ${row.far_code||'—'}`],['跨期价差',signed(row.spread)],['价差5日变化（价格单位）',signed(row.spread_change5)],['Carry 5日变化（百分点）',signed(row.carry_change5)],['有效因子组',`${row.structure_evidence?.effective_groups??0} / 4`],['现货 / 库存',`${row.structure_evidence?.basis?.status==='ok'?'有现货':'现货缺失'} / ${row.structure_evidence?.inventory?.status==='ok'?'有库存':'库存缺失'}`];
  return `<article class="decision-panel detail-structure"><h2>商品结构 · ${directionText(row.structure_direction)}</h2><div class="structure-grid">${items.map(([label,value])=>`<div><span>${label}</span><strong>${value}</strong></div>`).join('')}</div></article>`;
}

function klineDialog(row){
  return `<dialog id="kline-modal" class="kline-modal" aria-labelledby="kline-modal-title"><div class="kline-modal-shell"><header class="kline-modal-header"><div><span class="eyebrow">INTERACTIVE CHART</span><h2 id="kline-modal-title">${row.name} · 日线结构</h2><p>滚轮缩放 · 横向拖动 · 双击复位 · 拖动红绿虚线校正价位</p></div><div class="kline-modal-actions"><button type="button" data-chart-zoom-out aria-label="缩小时间范围">−</button><button type="button" data-chart-reset>重置视图</button><button type="button" data-chart-zoom-in aria-label="放大时间范围">＋</button><button type="button" data-reset-levels>恢复系统价位</button><button type="button" class="modal-close" data-close-kline aria-label="关闭">×</button></div></header><div id="kline-modal-chart"></div><footer class="kline-modal-footer"><span><i class="support-key"></i>支撑位：可上下拖动</span><span><i class="resistance-key"></i>压力位：可上下拖动</span><span>成交量为柱，持仓量为棕色线</span></footer></div></dialog>`;
}
```

Then make `renderDetail` emit the approved hierarchy:

```js
app.innerHTML=header()+`<section class="detail-workspace">
  ${detailSidebar(row)}
  <div class="detail-main">
    <header class="detail-instrument"><div><h2>${row.name}</h2><span>${codeOf(row)} · ${row.main_code||'—'}</span></div><div><strong>${detailStatusLabel(row)}</strong><span>${ema20Summary(row).direction} · ${ema20Summary(row).strength}</span></div><button data-jump-options="${codeOf(row)}">查看T型报价</button></header>
    <article class="detail-chart-stage"><div class="section-heading"><div><h2>日线 K 线 / EMA20</h2><div class="muted small">普通滚轮切换品种 · Ctrl + 滚轮缩放 · 红色压力 · 绿色支撑</div></div><button type="button" data-open-kline>全屏查看</button></div><div id="single-chart" class="detail-primary-chart" tabindex="0" aria-label="可缩放EMA20日线K线图"></div></article>
    ${ema20Assessment(row)}
    <section class="detail-analysis-grid">
      <article class="decision-panel detail-actionability"><h2>可做性与价格位置</h2>${metricBlocks(row)}<p class="phase-rationale">${row.trend_state_reason||'暂无阶段说明。'}</p><div class="factor-contributions">${Object.entries(row.trend_components||{}).map(([key,value])=>`<span>${{price:'价格 / EMA20',momentum:'绝对动量',di:'DI / ADX'}[key]} <strong class="${tone(value)}">${signed(value)}</strong></span>`).join('')}</div></article>
      ${holdingPanel(row)}
      ${structurePanel(row)}
    </section>
  </div>
</section>${klineDialog(row)}`;
```

- [ ] **Step 4: Make the main chart interactive with the new wheel policy**

Replace `renderSingleChart` with:

```js
function renderSingleChart(row){
  if(!data.candles?.[codeOf(row)])return;
  renderCandlestickChart($('single-chart'),chartInput(row),{
    window:Number($('window')?.value||60),
    title:`${row.name}日线K线、成交量与持仓量`,
    interactive:true,
    wheelMode:'navigate',
    onNavigate:navigateDetail,
    onLevelChange:levels=>saveManualLevels(row,levels),
  });
}
```

Leave the modal call on the default `wheelMode:'zoom'` so its existing plain-wheel zoom behavior remains self-contained.

- [ ] **Step 5: Bind sidebar search, click, wheel, and global arrows**

Inside the detail branch in `wireView`, add:

```js
$('detail-search')?.addEventListener('input',event=>{
  state.detailSearch=event.target.value;
  render();
  requestAnimationFrame(()=>{const input=$('detail-search');input?.focus();input?.setSelectionRange(input.value.length,input.value.length)});
});
document.querySelector('.detail-symbols')?.addEventListener('wheel',navigateDetailByWheel,{passive:false});
document.querySelectorAll('[data-detail-code]').forEach(button=>button.addEventListener('click',()=>{
  const row=rows().find(item=>codeOf(item)===button.dataset.detailCode);
  if(row){state.selected=codeOf(row);render()}
}));
```

Add one global handler and bind it once in `init`:

```js
function handleDetailKey(event){
  if(state.view!=='detail'||!['ArrowDown','ArrowUp'].includes(event.key))return;
  if(ignoresDetailShortcut(event.target,Boolean(document.querySelector('dialog[open]'))))return;
  event.preventDefault();navigateDetail(event.key==='ArrowDown'?1:-1);
}
```

```js
document.addEventListener('keydown',handleDetailKey);
```

- [ ] **Step 6: Run syntax and frontend tests**

Run:

```powershell
node --check 期货/frontend/app.mjs
node --check 期货/frontend/charts.mjs
Get-ChildItem 期货/frontend -Filter '*.test.mjs' | Sort-Object Name | ForEach-Object { node $_.FullName; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
```

Expected: every command exits 0.

- [ ] **Step 7: Review only the intended app diff and commit**

Run `git diff -- 期货/frontend/app.mjs`, verify the user's existing unrelated option changes remain present, then:

```powershell
git add 期货/frontend/app.mjs
git commit -m "feat: build K-line-first commodity detail workspace"
```

### Task 4: Apply the approved layout and responsive hierarchy

**Files:**
- Modify: `期货/frontend/style.css`

- [ ] **Step 1: Add scoped desktop layout styles**

Append a dedicated block, without altering existing option selectors:

```css
.detail-workspace{display:grid;grid-template-columns:220px minmax(0,1fr);gap:18px;align-items:start}
.detail-sidebar{position:sticky;top:12px;height:calc(100vh - 112px);min-height:520px;background:#fff;border-right:1px solid var(--line);display:flex;flex-direction:column;min-width:0}
.detail-sidebar-head{padding:14px 12px 8px}.detail-sidebar-head strong,.detail-sidebar-head small{display:block}.detail-sidebar-head small,.detail-shortcut-help{color:var(--muted);font-size:10px;line-height:1.6}
.detail-sidebar input{margin:8px 12px;padding:8px;width:calc(100% - 24px)}
.detail-symbols{min-height:0;overflow:hidden;overscroll-behavior:contain}
.detail-group-label{padding:10px 12px 5px;color:var(--muted);font-size:10px;letter-spacing:.6px}
.detail-symbol{width:100%;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;text-align:left;border:0;border-top:1px solid #edf0f4;border-radius:0;padding:9px 12px}
.detail-symbol span,.detail-symbol strong,.detail-symbol small{display:block;min-width:0}.detail-symbol small{color:var(--muted);font-size:10px;margin-top:3px}.detail-symbol em{font-style:normal;font-size:10px;color:var(--muted)}
.detail-symbol.active{background:#eaf2ff;box-shadow:inset 3px 0 var(--blue)}
.detail-shortcut-help{margin:auto 12px 0;padding:12px 0;border-top:1px solid var(--line)}
.detail-main{min-width:0}.detail-instrument{display:flex;align-items:center;gap:16px;margin-bottom:12px}.detail-instrument>div:first-child{margin-right:auto}.detail-instrument h2{font-size:21px}.detail-instrument span{display:block;color:var(--muted);font-size:11px;margin-top:4px}
.detail-chart-stage{background:#fff;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:14px 0 8px}
.detail-primary-chart{min-width:0}.detail-primary-chart .chart-svg{height:clamp(460px,60vh,720px)}
.detail-primary-chart .chart-surface{overscroll-behavior:contain}.detail-primary-chart .kline-chart-surface{touch-action:none;user-select:none}
.detail-main>.ema20-assessment{margin:0 0 22px}
.detail-analysis-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.detail-analysis-grid .detail-actionability{grid-column:1/-1}
```

- [ ] **Step 2: Add responsive rules**

```css
@media(max-width:1050px){
  .detail-workspace{grid-template-columns:170px minmax(0,1fr);gap:12px}
  .detail-primary-chart .chart-svg{height:clamp(430px,56vh,620px)}
}
@media(max-width:700px){
  .detail-workspace{display:block}.detail-sidebar{position:static;height:auto;min-height:0;border-right:0;border-bottom:1px solid var(--line);margin-bottom:14px}
  .detail-symbols{display:flex;overflow-x:auto}.detail-group-label,.detail-shortcut-help{display:none}.detail-symbol{min-width:150px;border-left:1px solid var(--line)}
  .detail-instrument{align-items:flex-start;flex-wrap:wrap}.detail-instrument>div:first-child{flex:1 1 60%}
  .detail-primary-chart .chart-svg{height:430px}.detail-analysis-grid{grid-template-columns:1fr}
}
@media(prefers-reduced-motion:reduce){.detail-symbol{transition:none}}
```

- [ ] **Step 3: Check style diff for overlap with the user's dirty work**

Run:

```powershell
git diff -- 期货/frontend/style.css
git diff --check
```

Expected: the new detail block is present and existing option-page edits are unchanged.

- [ ] **Step 4: Run the entire frontend test suite and syntax checks**

Use the same commands as Task 3, Step 6.

Expected: all exit 0.

- [ ] **Step 5: Commit only the detail styles**

```powershell
git add 期货/frontend/style.css
git commit -m "style: make K-line the primary detail view"
```

### Task 5: Browser acceptance and full regression

**Files:**
- Verify only; modify earlier files only if an acceptance check reveals a reproducible defect, using a new failing unit test first.

- [ ] **Step 1: Restart the local dashboard service on port 8799**

Identify the exact listener with `netstat -ano | Select-String '127.0.0.1:8799'`, stop only that verified process tree, and start hidden:

```powershell
Start-Process -FilePath 'D:\project\期货\.venv\Scripts\python.exe' -ArgumentList @('research_server.py','--asof','20260924','--port','8799') -WorkingDirectory 'D:\project\期货\期货' -WindowStyle Hidden
```

- [ ] **Step 2: Verify the desktop layout in Playwright CLI**

Open `http://127.0.0.1:8799/`, enter 商品详情, and verify:

- `.detail-workspace` has a left rail and one main column;
- `.detail-primary-chart .chart-svg` occupies approximately 60% of viewport height;
- the EMA20 legend is present and no other moving-average legend exists;
- EMA20 assessment appears directly below the chart;
- 可做性、量仓、商品结构 appear below the assessment;
- browser console contains zero errors.

- [ ] **Step 3: Verify all navigation scopes**

With a fresh snapshot and stable refs:

- press `ArrowDown` and verify the selected commodity changes once;
- press `ArrowUp` and verify it returns once;
- wheel on the sidebar and verify one commodity change per cooldown interval;
- wheel normally over the chart and verify the commodity changes;
- hold Control and wheel over the chart, then verify `data-visible-start` or `data-visible-end` changes while the commodity code remains unchanged;
- wheel over the below-chart analysis area and verify the page scroll position changes while the commodity remains unchanged;
- navigate to first/last item and verify further movement does not wrap.

- [ ] **Step 4: Verify the narrow layout**

Resize to 700px width and confirm the commodity navigator becomes horizontal above the chart, chart remains readable, and all three analysis groups stack below it.

- [ ] **Step 5: Run fresh full verification**

Run:

```powershell
Get-ChildItem 期货/frontend -Filter '*.test.mjs' | Sort-Object Name | ForEach-Object { node $_.FullName; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
node --check 期货/frontend/app.mjs
node --check 期货/frontend/charts.mjs
$line = Get-Content 'D:\project\期货\.env' | Where-Object { $_ -match '^OAR_TUSHARE_TOKEN=' } | Select-Object -First 1
if ($line) { $env:OAR_TUSHARE_TOKEN = $line.Substring($line.IndexOf('=') + 1).Trim() }
& 'D:\project\期货\.venv\Scripts\python.exe' -m unittest discover -s 期货/tests -p 'test_*.py'
git diff --check
```

Expected: every frontend test passes, all syntax checks exit 0, all Python tests pass, and `git diff --check` reports no errors.

- [ ] **Step 6: Final focused review**

Run `git status --short` and confirm the only remaining uncommitted paths are the user's pre-existing option-page files and `期货/tests/_tmp_wedge_probe.py`. Confirm no old moving-average field is added to any runtime or chart path.
