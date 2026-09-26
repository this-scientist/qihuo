# 主力合约席位持仓展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在每日行情更新后采集主力真实月份合约的 Tushare 席位排名，将可审计汇总写入快照，并在商品详情页作中性展示和解释。

**Architecture:** 新增 `holding_data.py`，把交易所代码适配、响应校验、前二十汇总和逐合约持久化集中在一个领域模块中。研究服务的更新任务在主力合约确定后调用该模块；仪表盘构建器按逻辑主连代码关联汇总，快照层复制原始榜单、汇总和质量报告。前端使用独立纯函数模块渲染四种数据状态，席位字段不进入任何评分函数。

**Tech Stack:** Python 3.11、pandas、unittest、JavaScript ES modules、Node `node:test`、现有原子 CSV/JSON 与快照机制。

---

## 文件结构

- Create: `期货/holding_data.py` — 合约查询适配、响应校验、榜单汇总、逐合约采集与文件持久化。
- Create: `期货/tests/test_holding_data.py` — 席位领域逻辑与采集降级测试。
- Modify: `期货/research_server.py` — 在行情更新任务中触发非阻断式席位采集，校验 payload schema 缓存版本。
- Modify: `期货/dashboard_data.py` — 加载每日席位汇总并关联到 `trader_positions`，发布 payload schema 版本。
- Modify: `期货/snapshot_store.py` — 将席位原始分区、汇总和质量报告复制到不可变快照。
- Modify: `期货/tests/test_dashboard_data.py` — 验证席位汇总关联与 payload schema 判定。
- Modify: `期货/tests/test_persistence.py` — 验证席位文件随快照复制以及旧缓存失效。
- Create: `期货/frontend/holdings.mjs` — 纯函数生成席位解释和安全 HTML。
- Create: `期货/frontend/holdings.test.mjs` — 完整、仅数值、缺失、无效四种状态测试。
- Modify: `期货/frontend/app.mjs` — 商品详情页调用席位面板渲染函数。
- Modify: `期货/frontend/style.css` — 席位摘要、前五榜单和口径说明样式。
- Modify: `README.md` — 记录数据源、展示口径、降级行为和不参与评分的边界。

## Task 1: 席位查询适配、校验和汇总

**Files:**
- Create: `期货/holding_data.py`
- Create: `期货/tests/test_holding_data.py`

- [ ] **Step 1: 写合约查询适配的失败测试**

在 `test_holding_data.py` 中覆盖标准交易所、广期所小写、郑商所原生三位年份和 INE 经 SHFE 查询：

```python
class HoldingQueryTests(unittest.TestCase):
    def test_exchange_specific_symbols(self):
        self.assertEqual(holding_query('M2701.DCE', 'DCE'),
                         {'trade_date': None, 'symbol': 'M2701', 'exchange': 'DCE'})
        self.assertEqual(holding_query('SI2611.GFE', 'GFEX')['symbol'], 'si2611')
        self.assertEqual(holding_query('TA2701.ZCE', 'CZCE')['symbol'], 'TA701')
        self.assertEqual(holding_query('SC2611.INE', 'INE')['exchange'], 'SHFE')
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `python -m unittest tests.test_holding_data.HoldingQueryTests -v`

Expected: `ModuleNotFoundError: No module named 'holding_data'`。

- [ ] **Step 3: 实现查询适配和严格身份函数**

在 `holding_data.py` 中实现：

```python
HOLDING_FIELDS = ['trade_date','symbol','broker','vol','vol_chg',
                  'long_hld','long_chg','short_hld','short_chg','exchange']

def holding_query(ts_code, exchange, trade_date=None):
    contract = ts_code.split('.')[0]
    symbol = contract.lower() if exchange == 'GFEX' else contract
    if exchange == 'CZCE':
        standard = re.fullmatch(r'([A-Za-z]+)\d(\d{3})', contract)
        native = re.fullmatch(r'([A-Za-z]+)(\d{3})', contract)
        match = standard or native
        if match is None:
            raise DataError(f'Invalid CZCE holding contract: {ts_code}')
        symbol = f'{match.group(1).upper()}{match.group(2)}'
    return {'trade_date': trade_date, 'symbol': symbol,
            'exchange': 'SHFE' if exchange == 'INE' else exchange}

def symbol_matches(ts_code, exchange, response_symbol):
    expected = holding_query(ts_code, exchange)['symbol']
    return str(response_symbol).casefold() in {
        expected.casefold(), ts_code.split('.')[0].casefold()}
```

同时实现 `symbol_matches(ts_code, exchange, response_symbol)`：大小写归一；CZCE 同时识别标准四位年份和交易所原生三位年份；INE 只接受目标品种和月份完全相同的合约。

- [ ] **Step 4: 写校验、前二十和前五榜单失败测试**

测试数据必须包含 22 个会员、不同的多空排序、空变化字段和一个乱码名称。断言：

```python
summary = summarize_holding(frame, target, main_oi=10000)
self.assertEqual(summary['top20_long'], expected_long_sum)
self.assertEqual(summary['top20_short'], expected_short_sum)
self.assertEqual(summary['top20_net'], expected_long_sum - expected_short_sum)
self.assertEqual(len(summary['top_long_brokers']), 5)
self.assertEqual(summary['holding_status'], 'available')
```

另写独立用例验证：选入前 20 的任一变化为空时对应变化汇总为 `None`；乱码触发 `numeric_only` 并将两个会员榜置空；错误日期、合约、交易所、负持仓和 2000 行响应抛出 `DataError`；集中度大于 1 时状态为 `invalid`。

- [ ] **Step 5: 运行新增测试并确认汇总函数缺失**

Run: `python -m unittest tests.test_holding_data -v`

Expected: FAIL，提示 `summarize_holding` 或 `validate_holding` 尚未定义。

- [ ] **Step 6: 实现最小校验和汇总代码**

实现以下公开接口：

```python
def invalid_broker(value):
    text = '' if pd.isna(value) else str(value).strip()
    return not text or '\ufffd' in text or any(ord(char) < 32 for char in text)

def broker_rows(rows, side):
    holding_field, change_field = (f'{side}_hld', f'{side}_chg')
    return [dict(broker=str(row.broker), holding=float(getattr(row, holding_field)),
                 change=(float(getattr(row, change_field))
                         if pd.notna(getattr(row, change_field)) else None))
            for row in rows.head(5).itertuples()]

def validate_holding(frame, target):
    if frame.empty:
        raise DataError('Holding ranking unavailable')
    required(frame, HOLDING_FIELDS)
    if len(frame) >= LIMITS['fut_holding']:
        raise DataError('Holding ranking reached row limit')
    if not frame.trade_date.astype(str).eq(target['trade_date']).all():
        raise DataError('Wrong holding trade_date')
    if not frame.symbol.astype(str).map(
            lambda value: symbol_matches(target['contract'], target['exchange'], value)).all():
        raise DataError('Wrong holding contract')
    allowed = {'SHFE', 'INE'} if target['exchange'] == 'INE' else {target['exchange']}
    if not set(frame.exchange.dropna().astype(str)).issubset(allowed):
        raise DataError('Wrong holding exchange')
    clean = frame.copy()
    for field in ['vol','vol_chg','long_hld','long_chg','short_hld','short_chg']:
        clean[field] = pd.to_numeric(clean[field], errors='coerce')
    if any((clean[field].dropna() < 0).any() for field in ['vol','long_hld','short_hld']):
        raise DataError('Negative holding rank value')
    return clean

def unavailable_summary(target, status, reason):
    return dict(ts_code=target['ts_code'], holding_contract=target['contract'],
                holding_trade_date=target['trade_date'], holding_status=status,
                holding_reason=reason, top20_long=None, top20_short=None,
                top20_net=None, top20_long_change=None, top20_short_change=None,
                top20_net_change=None, top20_long_concentration=None,
                top20_short_concentration=None, top_long_brokers=[],
                top_short_brokers=[])

def summarize_holding(frame, target, main_oi):
    clean = validate_holding(frame, target)
    long_rows = clean.dropna(subset=['long_hld']).nlargest(20, 'long_hld')
    short_rows = clean.dropna(subset=['short_hld']).nlargest(20, 'short_hld')
    long_total = float(long_rows.long_hld.sum())
    short_total = float(short_rows.short_hld.sum())
    long_change = None if long_rows.long_chg.isna().any() else float(long_rows.long_chg.sum())
    short_change = None if short_rows.short_chg.isna().any() else float(short_rows.short_chg.sum())
    numeric_only = any(invalid_broker(value) for value in clean.broker)
    result = unavailable_summary(target, 'numeric_only' if numeric_only else 'available',
                                 '席位名称源数据异常' if numeric_only else None)
    result.update(top20_long=long_total, top20_short=short_total,
                  top20_net=long_total-short_total,
                  top20_long_change=long_change, top20_short_change=short_change,
                  top20_net_change=(long_change-short_change
                                    if long_change is not None and short_change is not None else None),
                  top20_long_concentration=long_total/main_oi if main_oi else None,
                  top20_short_concentration=short_total/main_oi if main_oi else None,
                  top_long_brokers=[] if numeric_only else broker_rows(long_rows, 'long'),
                  top_short_brokers=[] if numeric_only else broker_rows(short_rows, 'short'))
    if any(value is not None and not 0 <= value <= 1 for value in
           [result['top20_long_concentration'], result['top20_short_concentration']]):
        return unavailable_summary(target, 'invalid', '席位集中度超出合理范围')
    return result
```

`target` 统一使用：

```python
target = dict(ts_code='M.DCE', contract='M2701.DCE', exchange='DCE',
              trade_date='20260924', main_oi=10000)
```

实现规则：持仓和成交量非负，变化字段允许有符号；多仓和空仓独立降序截取前 20；只有被截取成员的变化均非空才求变化之和；名称含 `\ufffd`、为空或含控制字符则整份汇总降级为 `numeric_only`；集中度缺少分母时为 `None`，超出 `[0,1]` 时返回 `invalid` 并清空数值与榜单。

- [ ] **Step 7: 运行新增测试并确认通过**

Run: `python -m unittest tests.test_holding_data -v`

Expected: 全部 PASS。

- [ ] **Step 8: 提交领域逻辑**

```bash
git add 期货/holding_data.py 期货/tests/test_holding_data.py
git commit -m "feat: validate and summarize futures holdings"
```

## Task 2: 逐主力合约采集与更新任务接入

**Files:**
- Modify: `期货/holding_data.py`
- Modify: `期货/tests/test_holding_data.py`
- Modify: `期货/research_server.py`

- [ ] **Step 1: 写采集器失败测试**

构造只记录调用的假 collector，输入包含同一品种的 main 和 secondary。断言只请求 main，GFEX 使用小写 symbol，单个合约空响应写入 `unavailable`，其他合约仍成功：

```python
report = collect_main_holdings(fake, root, selected, '20260924')
self.assertEqual([call['symbol'] for call in fake.calls], ['M2701', 'si2611'])
self.assertEqual(report['counts']['available'], 1)
self.assertEqual(report['counts']['unavailable'], 1)
self.assertTrue((root/'processed/holding/20260924.json').exists())
```

验证成功合约产生 `raw/holding/DCE/20260924/M2701.csv` 和同名 JSON 完成凭据；失败合约不生成伪原始 CSV。

- [ ] **Step 2: 运行采集器测试并确认失败**

Run: `python -m unittest tests.test_holding_data.HoldingCollectionTests -v`

Expected: FAIL，`collect_main_holdings` 尚未定义。

- [ ] **Step 3: 实现非阻断式逐合约采集**

在 `holding_data.py` 增加：

```python
def collect_main_holdings(collector, root, selected, trade_date, force=False):
    """Collect exact real-main contracts; contract failures become status rows."""
```

仅遍历 `role == 'main'`。每个合约通过 `collector.call('fut_holding', **params)` 请求；缓存命中时重新校验文件哈希和查询参数。原始 CSV 与完成凭据分别使用现有 `atomic_csv()`、`atomic_json()`；汇总写入 `processed/holding/<date>.json`，质量报告写入 `quality/holding_<date>.json`。返回报告包含四种状态计数和逐合约原因，捕获单合约 `DataError`，不写入 `collector.failures`。

- [ ] **Step 4: 写研究服务更新顺序失败测试**

在 `test_holding_data.py` 中对新增小函数 `collect_update_holdings(collector, source, asof, force)` 做集成测试：它读取 `raw/selected/<asof>.csv` 并调用 `collect_main_holdings`。不存在 selected 文件时返回显式质量报告而不抛异常。

- [ ] **Step 5: 在更新任务中触发席位采集**

在 `research_server.py` 的 `run_focused()` 成功且确认 `asof` 已发布后、历史补齐前加入：

```python
self.progress('采集主力合约席位排名')
from holding_data import collect_update_holdings
collect_update_holdings(collector, source, asof, bool(request.get('force', False)))
```

席位覆盖失败不得改变行情任务的 `success/partial/failed` 状态；用户从席位质量报告和页面状态查看覆盖情况。

- [ ] **Step 6: 运行席位与研究服务相关测试**

Run: `python -m unittest tests.test_holding_data tests.test_persistence -v`

Expected: 全部 PASS。

- [ ] **Step 7: 提交采集接入**

```bash
git add 期货/holding_data.py 期货/tests/test_holding_data.py 期货/research_server.py
git commit -m "feat: collect holdings for real main contracts"
```

## Task 3: Payload、缓存和不可变快照

**Files:**
- Modify: `期货/dashboard_data.py`
- Modify: `期货/research_server.py`
- Modify: `期货/snapshot_store.py`
- Modify: `期货/tests/test_dashboard_data.py`
- Modify: `期货/tests/test_persistence.py`

- [ ] **Step 1: 写席位汇总读取与关联失败测试**

在 `test_dashboard_data.py` 中先测试纯函数：

```python
rows = load_holding_summaries(root, '20260924')
self.assertEqual(rows['M.DCE']['holding_contract'], 'M2701.DCE')
self.assertEqual(missing_holding('I.DCE')['holding_status'], 'unavailable')
```

文件不存在、JSON 损坏或日期不符时不得串用其他日期，返回空映射；记录按逻辑主连 `ts_code` 关联。

- [ ] **Step 2: 实现 payload schema 和席位关联**

在 `dashboard_data.py` 增加：

```python
PAYLOAD_SCHEMA_VERSION = 2

def payload_schema_current(payload):
    return payload.get('payload_schema_version') == PAYLOAD_SCHEMA_VERSION

def missing_holding(code):
    return dict(ts_code=code, holding_contract=None, holding_trade_date=None,
                holding_status='unavailable', holding_reason='该主力合约没有可用席位排名',
                top20_long=None, top20_short=None, top20_net=None,
                top20_long_change=None, top20_short_change=None, top20_net_change=None,
                top20_long_concentration=None, top20_short_concentration=None,
                top_long_brokers=[], top_short_brokers=[])

def load_holding_summaries(root, asof):
    path = Path(root)/f'processed/holding/{asof}.json'
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if value.get('asof') != asof or not isinstance(value.get('records'), list):
        return {}
    return {row['ts_code']: row for row in value['records']
            if isinstance(row, dict) and row.get('ts_code')}
```

`build_payload()` 预先加载映射，并将现有 `record['trader_positions'] = None` 替换为：

```python
record['trader_positions'] = holding_rows.get(
    record['ts_code'], missing_holding(record['ts_code']))
```

返回 payload 时写入 `payload_schema_version=PAYLOAD_SCHEMA_VERSION`。不要修改 `trend_model.MODEL_VERSION`，因为席位数据不改变趋势模型；用独立 payload schema 使旧缓存失效，语义更准确。

- [ ] **Step 3: 更新缓存有效性测试与实现**

在 `test_dashboard_data.py` 断言缺少或旧的 payload schema 返回 false。在 `research_server.py` 的 MySQL 缓存读取条件中同时要求：

```python
payload_schema_current(cached) and chart_schema_current(cached)
```

旧缓存仍可作为最后降级输入，但必须经过当前文件源重建优先路径，不能被当作完整新 payload。

- [ ] **Step 4: 写快照复制失败测试**

在 `test_persistence.py` 创建以下文件并调用 `publish_snapshot()`：

```text
raw/holding/DCE/20260924/M2701.csv
raw/holding/DCE/20260924/M2701.json
processed/holding/20260924.json
quality/holding_20260924.json
```

断言四个文件存在于 `snapshot_source(root, '20260924')` 的相同相对路径中，内容哈希一致。

- [ ] **Step 5: 实现快照席位文件复制**

在 `snapshot_store.publish_snapshot()` 中把存在的汇总和质量文件加入 `paths`，并使用：

```python
paths.extend(str(path.relative_to(source)).replace('\\', '/')
             for path in (source/'raw/holding').glob(f'*/{asof}/*') if path.is_file())
```

沿用现有逐文件 SHA-256 复制校验。不得复制其他日期或整个可变数据根目录。

- [ ] **Step 6: 运行 payload 和持久化测试**

Run: `python -m unittest tests.test_dashboard_data tests.test_persistence -v`

Expected: 全部 PASS。

- [ ] **Step 7: 提交数据发布链路**

```bash
git add 期货/dashboard_data.py 期货/research_server.py 期货/snapshot_store.py 期货/tests/test_dashboard_data.py 期货/tests/test_persistence.py
git commit -m "feat: publish holding summaries in dashboard snapshots"
```

## Task 4: 商品详情席位展示与中性解释

**Files:**
- Create: `期货/frontend/holdings.mjs`
- Create: `期货/frontend/holdings.test.mjs`
- Modify: `期货/frontend/app.mjs`
- Modify: `期货/frontend/style.css`

- [ ] **Step 1: 写四种状态和解释失败测试**

在 `holdings.test.mjs` 中导入 `holdingExplanation`、`renderHoldings`，覆盖：

```javascript
assert.match(holdingExplanation({top20_net:1200,top20_net_change:-300,
  top20_long_change:100,top20_short_change:400}), /净多.*减少/);
assert.match(renderHoldings({holding_status:'numeric_only',top20_long:5000,
  top20_short:4500,top_long_brokers:[]}), /席位名称源数据异常/);
assert.doesNotMatch(renderHoldings({holding_status:'unavailable',holding_reason:'未发布'}), />0</);
assert.match(renderHoldings({holding_status:'invalid',holding_reason:'集中度异常'}), /集中度异常/);
```

增加 HTML 转义用例，会员名称 `<script>` 必须渲染为文本。

- [ ] **Step 2: 运行前端新增测试并确认失败**

Run: `node frontend/holdings.test.mjs`

Expected: `ERR_MODULE_NOT_FOUND`。

- [ ] **Step 3: 实现纯前端渲染模块**

`holdings.mjs` 导出：

```javascript
const escapeHtml=value=>String(value??'').replaceAll('&','&amp;')
  .replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const number=value=>value==null?'—':Number(value).toLocaleString('zh-CN',{maximumFractionDigits:0});
const signed=value=>value==null?'—':`${value>=0?'+':''}${number(value)}`;

function renderBrokerLists(value){
  const list=(title,rows)=>`<div><h4>${title}</h4><ol>${(rows||[]).map(row=>
    `<li><span>${escapeHtml(row.broker)}</span><strong>${number(row.holding)} <small>${signed(row.change)}</small></strong></li>`).join('')}</ol></div>`;
  return `<div class="holding-brokers">${list('多头前五',value.top_long_brokers)}${list('空头前五',value.top_short_brokers)}</div>`;
}

export function holdingExplanation(value){
  if(!['available','numeric_only'].includes(value?.holding_status))return '';
  const side=value.top20_net>0?'净多':value.top20_net<0?'净空':'多空持平';
  if(value.top20_net_change==null)return `前20席位${side}，当日变化数据不完整。`;
  const movement=value.top20_net_change>0?'净多增加':value.top20_net_change<0?'净多减少':'净仓未变';
  return `前20席位${side}，当日${movement}。`;
}

export function renderHoldings(value){
  const status=value?.holding_status||'unavailable';
  const note='<p class="holding-note">交易所公开排名的局部口径；全市场多空总量相等；不参与系统评分。</p>';
  if(!['available','numeric_only'].includes(status)){
    return `<section class="holding-panel holding-${escapeHtml(status)}"><p>${escapeHtml(value?.holding_reason||'该主力合约没有可用席位排名')}</p>${note}</section>`;
  }
  const summary=[['前20多仓',number(value.top20_long)],['前20空仓',number(value.top20_short)],
    ['前20净仓',signed(value.top20_net)],['净仓变化',signed(value.top20_net_change)]];
  const metrics=summary.map(([label,item])=>`<div><span>${label}</span><strong>${item}</strong></div>`).join('');
  const warning=status==='numeric_only'?'<p class="holding-warning">席位名称源数据异常</p>':'';
  const brokers=status==='available'?renderBrokerLists(value):'';
  return `<section class="holding-panel"><h3>${escapeHtml(value.holding_contract)} · ${escapeHtml(value.holding_trade_date)}</h3><div class="holding-summary">${metrics}</div><p>${escapeHtml(holdingExplanation(value))}</p>${warning}${brokers}${note}</section>`;
}
```

完整状态显示合约、日期、前二十多仓/空仓/净仓、三项日变化、两项集中度、多空前五榜单和解释。`numeric_only` 保留数值但不渲染会员名称。`unavailable/invalid` 只显示状态与原因。每种非空状态都显示固定口径说明：“交易所公开排名的局部口径；全市场多空总量相等；不参与系统评分。”

- [ ] **Step 4: 接入商品详情并添加样式**

在 `app.mjs` 顶部导入：

```javascript
import {renderHoldings} from './holdings.mjs';
```

删除量仓九宫格中的固定 `['席位多空持仓','未接入']`，在量仓卡片的基础指标网格后追加 `${renderHoldings(row.trader_positions)}`。

在 `style.css` 增加 `.holding-panel`、`.holding-summary`、`.holding-brokers`、`.holding-note` 的两栏桌面布局和单栏移动端规则，沿用现有颜色变量，不引入新视觉体系。

- [ ] **Step 5: 运行全部前端测试**

Run: `Get-ChildItem frontend -Filter '*.test.mjs' | ForEach-Object { node $_.FullName }`

Expected: 全部 PASS。

- [ ] **Step 6: 提交前端展示**

```bash
git add 期货/frontend/holdings.mjs 期货/frontend/holdings.test.mjs 期货/frontend/app.mjs 期货/frontend/style.css
git commit -m "feat: explain main-contract holding rankings"
```

## Task 5: 文档、完整回归和真实小样本验证

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 更新使用和口径文档**

在 README 的数据源与限制部分补充：`fut_holding` 为收盘席位排名；只采集主力真实月份合约；前二十净仓是公开榜单局部口径；数据不参与评分；缺失不记零；当前自定义网关会员名称乱码时只展示数值。

- [ ] **Step 2: 运行 Python 全量回归**

Run:

```powershell
$env:OAR_TUSHARE_TOKEN='test-token'
$env:OAR_TUSHARE_HTTP_URL='https://example.invalid'
python -m unittest discover -s tests -p 'test_*.py'
```

Expected: 全部 PASS，无新增 warning 或 error。

- [ ] **Step 3: 运行前端全量回归**

Run: `Get-ChildItem frontend -Filter '*.test.mjs' | ForEach-Object { node $_.FullName }`

Expected: 全部 PASS。

- [ ] **Step 4: 用当前凭据做只读小样本验证**

使用父工作区 `.env` 的现有网关凭据，针对设计阶段已经验证存在数据的一个 DCE 主力合约调用领域模块。输出只包含状态、行数、汇总值和名称质量，不打印 token。确认原始文件、凭据、汇总和质量报告均生成在临时目录，随后由临时目录自动清理。

- [ ] **Step 5: 检查不改变评分和排序**

在相同测试 fixture 上分别用缺失席位和完整席位构建决策，断言 `decision_side`、`dir_score`、`state_v2`、`structure_score` 和排序键完全一致。

- [ ] **Step 6: 检查差异和工作区边界**

Run:

```bash
git diff --check
git status --short
git log --oneline --decorate -5
```

Expected: 无空白错误；只包含本功能与文档改动；父工作区的未提交文件不在本分支中。

- [ ] **Step 7: 提交文档与最终验证修正**

```bash
git add README.md
git commit -m "docs: document futures holding coverage"
```
