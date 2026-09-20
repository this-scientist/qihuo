# -*- coding: utf-8 -*-
"""商品期权每日扫描器：爆发指数 + 十条组合信号 + 合约挑选。

分层口径与 strategy.evaluate 一致：缺失模块不计入可用权重，按可用项归一化，
不虚构库存、IV历史分位或盘口数据。所有期权数值为日线参考值，不是可执行报价。
"""
import math

WEIGHTS = dict(rps_strength=15, rps_accel=10, adx_accel=10, breakout=10, oi=10,
    volume=5, inventory=10, term=10, iv=10, liquidity=10)
MAIN_DELTA = (0.20, 0.55)
LOTTO_DELTA = (0.08, 0.20)
PREFERRED_DTE = (20, 60)
FALLBACK_DTE = (10, 60)
OUTER_DTE = (7, 120)
TARGET_MAIN_DELTA = 0.35
TARGET_LOTTO_DELTA = 0.14
# 期限档位依次放宽：20–60 → 10–60 → 7–120；近月<7天直接排除（衰减过快）。
DTE_BANDS = ((PREFERRED_DTE, ''),
    (FALLBACK_DTE, '期限放宽至10–60天'),
    (OUTER_DTE, '期限放宽至7–120天（远月Gamma较低）'))
SIGNAL_KEYS = ['rps_top', 'rps_rise', 'adx_turn', 'breakout', 'oi_up', 'volume_up',
    'inventory', 'term', 'iv_not_hot', 'liquidity_ok']
EXTENSION_NOTE = '过度延伸=方向已确认但偏离MA20超过阈值（默认3ATR）：趋势仍强但追单风险高，重点观察回调介入或衰竭，不适合作为启动买点。'
RADAR_NOTE = '反转雷达在方向扫描之外单独识别"原趋势内部先恶化→新趋势扩散确认"的品种：警报优先排列，其余按|RPS五日变化|排序。观察池，不构成方向建议；基差/库存未接入，期限确认仅用期货Carry。'
STRUCTURE_NOTE = ('商品结构雷达：用商品市场独有的资金(OI)/现货(基差)/跨期(月差)/曲线(期限结构)/库存五维度'
    '回答"这波趋势背后有没有真实资金与真实供需支撑"，与技术面（RPS/ADX/ATR/突破/量能）互补。'
    '"多/空头酝酿"=结构占优方向与当前价格趋势相反且结构分≥55：供需结构先变、价格尚未确认，是提前观察区而非入场信号。'
    '缺失维度不计入可用分按可用分归一：现货/基差需导入fundamentals.csv，库存当前未接入，无真实月对品种的月差与Carry缺失。')

# 10倍期权模型：轻中度虚值(|Delta| 0.10–0.40) + 7–30天，甜区 |Delta| 0.15–0.30 / DTE 7–15。
TB_DELTA_BAND = (0.10, 0.40)
TB_DELTA_SWEET = (0.15, 0.30)
TB_DTE_BAND = (7, 30)
TB_DTE_SWEET = (7, 15)
TB_ENGINE_WEIGHTS = dict(startup=25, rps=15, adx=10, oi_volume=10, fundamentals=10, iv_state=10)
TB_CONTRACT_WEIGHTS = dict(gamma_delta=10, dte=5, liquidity=5)

NOTES = [
    '爆发指数按十项权重（RPS强度15/RPS加速度10/ADX加速度10/突破10/OI10/量能5/基本面10/期限结构10/IV10/期权流动性10）计算，缺失模块按可用权重归一。',
    '多空口径对称：方向RPS20=多头取原始RPS20、空头取100−原始RPS20，信号①对空头即原始RPS排全市场后10%；信号②对空头指原始RPS加速走弱；信号④对空头指跌破平台；信号⑧对空头指Contango同向。OI、量能、IV、流动性为多空共用中性条件。',
    '没有IV历史分位：用参考IV−HV20溢价替代IV Rank，溢价低或为负代表期权相对已实现波动不贵。',
    '库存/仓单未接入：仅当外部导入现货/基差且身份匹配时评估基本面方向，否则该模块缺失。',
    'OI为当前固定主力/次主力两合约口径，不是全品种持仓；外部导入的全品种OI单独判断。',
    '期限结构动量来自真实月合约（未复权）固定主次对的年化Carry序列：Carry>0为Backwardation、<0为Contango；五日变化与符号翻转即"期限结构拐点"。复权主连只用于趋势指标，两条数据线不混用。',
    '三档可交易曲线（主力/次主力/第三活跃，按OI）依赖当日全合约快照；旧快照无该文件时曲率与曲线表缺失，Carry动量不受影响。',
    '过度延伸观察单独列出阶段判定为"过度延伸"的品种（双向，按爆发指数排名）；主榜单仍以启动/持续候选为主，延伸品种在主榜"趋势·阶段"列同样标注。',
    '反转雷达为品种级观察（与方向扫描互补）：强势衰退=五日前RPS20≥90且五日下滑≥15（跌破70升级）；衰退排列=RPS20<RPS60<RPS120且RPS120≥80；扩散翻多/翻空=三周期RPS同步升降且形成对应阶梯；价涨仓减按趋势背景定性——下跌趋势中=回补反弹（空头平仓推动，勿当反转追多），多头趋势中=减仓上行（新资金未接力的资金背离警示，不是看空信号），无趋势背景才泛称疑似空头回补。基差与库存未接入，期限确认仅用期货Carry。',
    '期权全部为日线收盘参考值，无买卖盘口与价差；合约挑选不构成可执行买入清单。',
    '合约档位：主仓|Delta| 0.20–0.55、彩票仓|Delta| 0.08–0.20；期限优先20–60自然日，池内无合约时依次放宽到10–60、7–120天并在档位标注；不足7天的近月直接排除。',
    '10倍潜力模型=品种发动机80分（趋势启动25/RPS15/ADX10/OI+成交10/基本面10/IV状态10，缺失归一）＋合约层20分（Gamma-Delta10/DTE5/流动性5）。合约只选|Delta|0.10–0.40、DTE7–30的轻中度虚值：|Delta|0.15–0.30与DTE7–15为甜区（兼具便宜与Gamma爆发力，标的无需极端行情即可穿越执行价）。IV相对HV20溢价>30%判为"已透支"（方向对也可能被Vega反吃）；总分≥80为高潜力、60–80中、<60低。核心逻辑：大方向×行情够快×买得早×Gamma够大×IV未提前透支。',
]


def _finite(*values):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def _item(score, cap, ok=True):
    return dict(score=round(float(score), 2), max=cap, status='ok' if ok else 'missing')


def _pick(option, tier, note):
    return dict(ts_code=option['ts_code'], tier=tier, note=note, call_put=option.get('call_put'),
        underlying_code=option.get('underlying_code'), role=option.get('role'), exchange=option.get('exchange'),
        exercise_price=option.get('exercise_price'), maturity_date=option.get('maturity_date'),
        days_to_expiry=option.get('days_to_expiry'), moneyness_pct=option.get('moneyness_pct'),
        premium=option.get('premium'), premium_per_lot=option.get('premium_per_lot'),
        delta=option.get('delta'), gamma=option.get('gamma'), vega=option.get('vega'), theta=option.get('theta'),
        iv_reference=option.get('iv_reference'), hv20=option.get('hv20'), hv60=option.get('hv60'),
        vol=option.get('vol'), oi=option.get('oi'), model_approximation=option.get('model_approximation'))


def _delta_pool(candidates, low, high):
    for band, note in DTE_BANDS:
        pool = [r for r in candidates if low <= r['_abs_delta'] <= high
            and band[0] <= r['days_to_expiry'] <= band[1]]
        if pool:
            return pool, note
    return [], ''


def _best(pool_records, target_delta):
    if not pool_records:
        return None
    return sorted(pool_records, key=lambda r: (abs(r['_abs_delta'] - target_delta), -min(r['vol'], r['oi']), r['ts_code']))[0]


def pick_contracts(chain, direction):
    """主仓 |Delta| 0.20–0.55 + 彩票仓 |Delta| 0.08–0.20；期限优先20–60自然日，依次放宽10–60、7–120；要求量仓与参考IV有效。"""
    side = 'C' if direction == 'long' else 'P'
    candidates = []
    for row in chain:
        dte, vol, oi, delta, iv = row.get('days_to_expiry'), row.get('vol'), row.get('oi'), row.get('delta'), row.get('iv_reference')
        if row.get('call_put') != side or not _finite(dte, vol, oi, delta, iv):
            continue
        if not 7 <= dte <= 120 or vol <= 0 or oi <= 0:
            continue
        row['_abs_delta'] = abs(delta)
        candidates.append(row)
    main_pool, main_note = _delta_pool(candidates, *MAIN_DELTA)
    main = _best(main_pool, TARGET_MAIN_DELTA)
    lotto_pool, lotto_note = _delta_pool(candidates, *LOTTO_DELTA)
    lotto = _best([r for r in lotto_pool if main is None or r['ts_code'] != main['ts_code']], TARGET_LOTTO_DELTA)
    picks = []
    if main is not None:
        picks.append(_pick(main, '主仓 |Delta| 0.20–0.55', main_note))
    if lotto is not None:
        picks.append(_pick(lotto, '彩票仓 |Delta| 0.08–0.20', lotto_note))
    reference = main or lotto or (max(candidates, key=lambda r: (min(r['vol'], r['oi']), r['vol'])) if candidates else None)
    return picks, reference


def _tb_iv_label(premium_pct):
    if not _finite(premium_pct):
        return '缺失'
    if premium_pct <= 0:
        return '低于HV（便宜）'
    if premium_pct <= 15:
        return '中低位'
    if premium_pct <= 30:
        return '中位'
    return '已透支'


def _tb_pool(chain, direction):
    """10倍候选池：方向正确、轻中度虚值(|Delta|0.10–0.40)、DTE7–30、量仓为正。"""
    side = 'C' if direction == 'long' else 'P'
    pool = []
    for row in chain:
        if row.get('call_put') != side:
            continue
        dte, vol, oi, delta, iv, gamma = (row.get(k) for k in
            ['days_to_expiry', 'vol', 'oi', 'delta', 'iv_reference', 'gamma'])
        if not _finite(dte, vol, oi, delta, iv, gamma) or vol <= 0 or oi <= 0:
            continue
        ad = abs(delta)
        if TB_DELTA_BAND[0] <= ad <= TB_DELTA_BAND[1] and TB_DTE_BAND[0] <= dte <= TB_DTE_BAND[1]:
            pool.append(row)
    return pool


def _tb_contract_score(row, gamma_max):
    """合约层20分：Delta位置6 + Gamma相对强度4 + DTE5 + 流动性5。"""
    ad = abs(row['delta'])
    dte = row['days_to_expiry']
    delta_pts = 6 if TB_DELTA_SWEET[0] <= ad <= TB_DELTA_SWEET[1] else 4
    gamma_norm = (row['gamma'] * row['underlying_close'] / gamma_max) if gamma_max > 0 else 0
    gamma_pts = round(4 * min(1.0, gamma_norm), 2)
    if TB_DTE_SWEET[0] <= dte <= TB_DTE_SWEET[1]:
        dte_pts = 5
    elif dte <= 20:
        dte_pts = 4
    else:
        dte_pts = 2
    depth = min(row['vol'], row['oi'])
    liq_pts = 5 if depth >= 2000 else (4 if depth >= 1000 else (2 if depth >= 300 else 1))
    return dict(gamma_delta=round(delta_pts + gamma_pts, 2), delta_band=delta_pts,
        gamma_rel=round(gamma_pts, 2), dte=dte_pts, liquidity=liq_pts,
        total=round(delta_pts + gamma_pts + dte_pts + liq_pts, 2), depth=depth)


def tenbagger(record, direction, chain, items, signals, resonance):
    """品种发动机80分（缺失归一）＋最优合约20分；返回10倍潜力评估。每模块元组=(得分, 实际可用分母)。"""
    # 趋势启动25：平台突破10 + 启动信号命中10（≥8条满分）+ 四重共振5。
    br = items['breakout']
    hits = record.get('startup_hits')
    hit_pts = round(10 * min(1.0, (hits or 0) / 8), 2) if isinstance(hits, (int, float)) else 0
    startup_avail = (10 if br['status'] == 'ok' else 0) + (10 if isinstance(hits, (int, float)) else 0) + 5
    parts = {'startup': (round(br['score'] + hit_pts + (5 if resonance else 0), 2), startup_avail)}
    # RPS15：强度8 + 加速度7。
    rps_earn = items['rps_strength']['score'] / 15 * 8 + items['rps_accel']['score'] / 10 * 7
    rps_avail = (8 if items['rps_strength']['status'] == 'ok' else 0) + (7 if items['rps_accel']['status'] == 'ok' else 0)
    parts['rps'] = (round(rps_earn, 2), rps_avail)
    parts['adx'] = (items['adx_accel']['score'], 10 if items['adx_accel']['status'] == 'ok' else 0)
    # OI+成交10：OI 6 + 量能4。
    ov_earn = items['oi']['score'] / 10 * 6 + items['volume']['score'] / 5 * 4
    ov_avail = (6 if items['oi']['status'] == 'ok' else 0) + (4 if items['volume']['status'] == 'ok' else 0)
    parts['oi_volume'] = (round(ov_earn, 2), ov_avail)
    # 基本面10：期限6 + 库存基差4。
    f_earn = items['term']['score'] / 10 * 6 + (items['inventory']['score'] if items['inventory']['status'] == 'ok' else 0)
    f_avail = (6 if items['term']['status'] == 'ok' else 0) + (4 if items['inventory']['status'] == 'ok' else 0)
    parts['fundamentals'] = (round(f_earn, 2), f_avail)
    # IV状态10：期权便宜度6 + ATR压缩2 + 实际突破2（突破布尔始终可算）。
    atr_pct = record.get('atr_percentile')
    iv_earn = (items['iv']['score'] / 10 * 6 if items['iv']['status'] == 'ok' else 0)
    iv_earn += (2 if _finite(atr_pct) and atr_pct <= 50 else 0) + (2 if signals.get('breakout') is True else 0)
    iv_avail = (6 if items['iv']['status'] == 'ok' else 0) + (2 if _finite(atr_pct) else 0) + 2
    parts['iv_state'] = (round(iv_earn, 2), iv_avail)
    earned = sum(v[0] for v in parts.values())
    available = sum(v[1] for v in parts.values())

    pool = _tb_pool(chain, direction)
    contracts = []
    if pool:
        gamma_max = max(r['gamma'] * r['underlying_close'] for r in pool)
        scored = []
        for row in pool:
            breakdown = _tb_contract_score(row, gamma_max)
            premium_pct = (row['iv_reference'] - row['hv20']) / row['hv20'] * 100 if _finite(row.get('hv20')) and row['hv20'] > 0 else None
            scored.append((breakdown['total'], row, breakdown, premium_pct))
        scored.sort(key=lambda x: (-x[0], -min(x[1]['vol'], x[1]['oi']), x[1]['ts_code']))
        for total, row, breakdown, premium_pct in scored[:3]:
            contracts.append(dict(_pick(row, '10倍候选', ''), tb_score=total,
                tb_breakdown=breakdown, iv_premium_pct=round(premium_pct, 1) if _finite(premium_pct) else None,
                iv_state=_tb_iv_label(premium_pct),
                gamma_label='高' if breakdown['gamma_rel'] >= 3 else ('中' if breakdown['gamma_rel'] >= 2 else '低'),
                liq_label='充足' if breakdown['depth'] >= 2000 else ('合格' if breakdown['depth'] >= 1000 else '偏薄')))
        best = contracts[0]
        earned += best['tb_score']
        available += 20
        iv_state = best['iv_state']
    else:
        best = None
        iv_state = '无候选合约'
    score = round(earned / available * 100, 2) if available else None
    label = '高' if score is not None and score >= 80 else ('中' if score is not None and score >= 60 else '低')
    return dict(score=score, label=label, side='Call' if direction == 'long' else 'Put',
        engine={k: dict(score=round(v[0], 2), max=TB_ENGINE_WEIGHTS[k], avail=v[1],
            missing=v[1] < TB_ENGINE_WEIGHTS[k]) for k, v in parts.items()},
        iv_state=iv_state, atr_percentile=atr_pct if _finite(atr_pct) else None,
        delta_hint='|Delta| 0.15–0.30 甜区（可接受0.10–0.40）', dte_hint='DTE 7–15 甜区（可接受7–30）',
        best=best['ts_code'] if best else None, contracts=contracts)


def _signals(record, direction, metrics, reference):
    d = 1 if direction == 'long' else -1
    rps20, acc = metrics.get('rps20'), metrics.get('rps_accel')
    adx, slope = record.get('adx'), record.get('adx_slope')
    plus_di, minus_di = record.get('plus_di'), record.get('minus_di')
    o5, vr, sp = record.get('oi_change5'), record.get('volume_ratio'), record.get('spread_change5')
    carry, carry5 = record.get('carry_annualized'), record.get('carry_change5')
    spot, basis5 = record.get('spot_change5'), record.get('basis_change5')
    b20 = record.get('break20_up' if d == 1 else 'break20_down')
    b55 = record.get('break55_up' if d == 1 else 'break55_down')
    fresh = record.get('signal_base_breakout')
    iv, hv20 = (metrics.get('iv'), metrics.get('hv20')) if reference is not None else (None, None)
    liquidity = min(reference['vol'], reference['oi']) if reference is not None else None
    return {
        'rps_top': rps20 >= 90 if _finite(rps20) else None,
        'rps_rise': acc >= 10 if _finite(acc) else None,
        'adx_turn': bool(slope >= 3 and adx >= 20 and d * (plus_di - minus_di) > 0) if _finite(slope, adx, plus_di, minus_di) else None,
        'breakout': None if not all(isinstance(v, bool) for v in [fresh, b20, b55]) else bool(fresh or b20 or b55),
        'oi_up': o5 > 0 if _finite(o5) else None,
        'volume_up': vr >= 1.2 if _finite(vr) else None,
        'inventory': bool(d * spot > 0 and d * basis5 > 0) if _finite(spot, basis5) else None,
        'term': (bool(d * carry > 0 and d * carry5 >= 0) if _finite(carry5) else bool(d * carry > 0))
            if _finite(carry) else (d * sp > 0 if _finite(sp) else None),
        'iv_not_hot': bool(iv <= hv20 * 1.3 and iv <= 60) if _finite(iv, hv20) else None,
        'liquidity_ok': liquidity >= 1000 if _finite(liquidity) else None,
    }


def scan_one(record, direction, chain):
    d = 1 if direction == 'long' else -1
    picks, reference = pick_contracts(chain, direction)
    items = {}
    rps20 = record.get('directional_rps20')
    if _finite(rps20):
        items['rps_strength'] = _item(max(0.0, min(1.0, (rps20 - 50) / 45)) * 15, 15)
    else:
        items['rps_strength'] = _item(0, 15, False)
    raw, prev = record.get('rps20'), record.get('rps20_prev5')
    if _finite(raw, prev):
        accel = (raw - prev) if d == 1 else (prev - raw)
        items['rps_accel'] = _item(max(0.0, min(1.0, accel / 12)) * 10, 10)
    else:
        items['rps_accel'] = _item(0, 10, False)
    adx, slope = record.get('adx'), record.get('adx_slope')
    plus_di, minus_di = record.get('plus_di'), record.get('minus_di')
    if _finite(slope):
        base = max(0.0, min(1.0, slope / 5)) * 10
        if _finite(plus_di, minus_di) and d * (plus_di - minus_di) <= 0:
            base *= 0.5
        items['adx_accel'] = _item(base, 10)
    else:
        items['adx_accel'] = _item(0, 10, False)
    b20 = record.get('break20_up' if d == 1 else 'break20_down')
    b55 = record.get('break55_up' if d == 1 else 'break55_down')
    fresh = record.get('signal_base_breakout')
    if all(isinstance(v, bool) for v in [fresh, b20, b55]):
        items['breakout'] = _item(5 * fresh + 3 * b55 + 2 * b20, 10)
    else:
        items['breakout'] = _item(0, 10, False)
    o5, o20 = record.get('oi_change5'), record.get('oi_change20')
    if _finite(o5, o20):
        items['oi'] = _item(5 * (o5 > 0) + 5 * (o20 > 0), 10)
    else:
        items['oi'] = _item(0, 10, False)
    vr = record.get('volume_ratio')
    if _finite(vr):
        score = 5 if 1.2 <= vr <= 3 else (3 if 1.1 <= vr < 1.2 else (2 if vr > 3 else 0))
        items['volume'] = _item(score, 5)
    else:
        items['volume'] = _item(0, 5, False)
    spot, basis5 = record.get('spot_change5'), record.get('basis_change5')
    if _finite(spot, basis5):
        items['inventory'] = _item(10 if d * spot > 0 and d * basis5 > 0 else 0, 10)
    else:
        items['inventory'] = _item(0, 10, False)
    sp = record.get('spread_change5')
    carry, carry5 = record.get('carry_annualized'), record.get('carry_change5')
    if _finite(carry):
        # 期限项梯度：方向对齐6分 + 年化Carry有意义(≥2%)2分 + Carry动量同向2分。
        score = 6 * (d * carry > 0) + 2 * (d * carry >= 2.0) + (2 if _finite(carry5) and d * carry5 > 0 else 0)
        items['term'] = _item(score, 10)
    elif _finite(sp):
        items['term'] = _item(10 if d * sp > 0 else 0, 10)
    else:
        items['term'] = _item(0, 10, False)
    iv = reference.get('iv_reference') if reference is not None else None
    hv20 = reference.get('hv20') if reference is not None else None
    if _finite(iv, hv20):
        items['iv'] = _item(max(0.0, min(1.0, (5 - (iv - hv20)) / 10)) * 10, 10)
    else:
        items['iv'] = _item(0, 10, False)
    liquidity = min(reference['vol'], reference['oi']) if reference is not None else None
    if _finite(liquidity):
        items['liquidity'] = _item(max(0.0, min(1.0, liquidity / 2000)) * 10, 10)
    else:
        items['liquidity'] = _item(0, 10, False)
    earned = sum(i['score'] for i in items.values() if i['status'] == 'ok')
    available = sum(i['max'] for i in items.values() if i['status'] == 'ok')
    explosion = round(earned / available * 100, 2) if available > 0 else None
    metrics = dict(rps20=rps20, rps_accel=(raw - prev) if d == 1 and _finite(raw, prev) else ((prev - raw) if _finite(raw, prev) else None),
        adx=adx, adx_slope=slope, return5=record.get('return5'), oi_change5=o5, oi_change20=o20,
        volume_ratio=vr, spread_change5=sp, extension_atr=record.get('extension_atr'),
        atr_percentile=record.get('atr_percentile'), iv=iv, hv20=hv20,
        iv_premium=(iv - hv20) if _finite(iv, hv20) else None,
        carry_annualized=record.get('carry_annualized'), carry_change5=record.get('carry_change5'),
        carry_change20=record.get('carry_change20'), structure=record.get('structure'),
        structure_flip5=record.get('structure_flip5'), curvature=record.get('curvature'))
    signals = _signals(record, direction, metrics, reference)
    # 四重共振：RPS拐点 + ADX拐头 + OI增加 + 期限结构拐点 同向同时出现。
    parts = {'rps拐点': signals['rps_rise'] is True, 'ADX拐头': signals['adx_turn'] is True,
        'OI增加': signals['oi_up'] is True,
        '期限拐点': (_finite(carry5) and d * carry5 > 0) or record.get('structure_flip5') is True}
    resonance = all(parts.values())
    tb = tenbagger(record, direction, chain, items, signals, resonance)
    structure = structure_radar(record)
    return dict(ts_code=record.get('ts_code'), name=record.get('name'), sector=record.get('sector'),
        main_code=record.get('main_code'), phase=record.get('phase'), trend_direction=record.get('trend_direction'),
        phase_match=record.get('phase_match'), phase_age=record.get('phase_age'),
        phase_reason=record.get('phase_reason'), phase_extension_atr=record.get('phase_extension_atr'),
        trend_score=record.get('trend_score'), startup_score=record.get('startup_score'), startup_hits=record.get('startup_hits'),
        explosion_score=explosion, items=items, signals=signals,
        signals_met=sum(1 for v in signals.values() if v is True),
        signals_applicable=sum(1 for v in signals.values() if v is not None),
        resonance=resonance, resonance_parts=[key for key, value in parts.items() if value],
        metrics=metrics, contracts=picks, option_ready=reference is not None,
        structure=structure,
        structure_score=(structure['long_score'] if direction == 'long' else structure['short_score']),
        structure_quality=structure['quality'], structure_divergence=structure['divergence'],
        tenbagger=tb, curve=record.get('curve', []))


def radar_row(record):
    """品种级反转观察：RPS阶梯/衰退警报/扩散确认/价涨仓减，字段全部来自已有原始值。"""
    r20, r60, r120 = (record.get(k) for k in ['rps20', 'rps60', 'rps120'])
    p20, p60, p120 = (record.get(k) for k in ['rps20_prev5', 'rps60_prev5', 'rps120_prev5'])
    if not (_finite(r20, r60, r120) and _finite(p20, p60, p120)):
        return None
    slope5 = r20 - p20
    ladder = 'RPS20>60>120' if r20 > r60 > r120 else ('RPS20<60<120' if r20 < r60 < r120 else None)
    moves = [r20 - p20, r60 - p60, r120 - p120]
    diffusion = 'up' if all(x > 0 for x in moves) else ('down' if all(x < 0 for x in moves) else None)
    oi5, ret5 = record.get('oi_change5'), record.get('return5')
    weakening = p20 >= 90 and slope5 <= -15
    covering = bool(_finite(oi5, ret5) and ret5 >= 1 and oi5 <= -1)
    # 价涨仓减的定性取决于趋势背景：下跌中=空头回补反弹（勿追多）；多头趋势中=减仓上行（资金背离警示）。
    trend_dir = record.get('trend_direction')
    if covering and trend_dir == 'long':
        covering_alert = '减仓上行：多头趋势中5日价升≥1%而OI减≥1%，新资金未接力，警惕资金背离（盯能否重新增仓）'
        covering_state = '减仓上行'
    elif covering and trend_dir == 'short':
        covering_alert = '回补反弹：下跌趋势中5日价升≥1%而OI减≥1%，空头平仓推动的反弹，勿当反转追多'
        covering_state = '回补反弹'
    elif covering:
        covering_alert = '价涨仓减：5日价升≥1%而OI减≥1%，无明确趋势背景，疑似空头回补'
        covering_state = '价涨仓减'
    alerts = []
    if weakening:
        alerts.append('强势衰退警报' if r20 >= 70 else '强势衰退警报（已跌破70，升级）')
    if ladder == 'RPS20<60<120' and r120 >= 80:
        alerts.append('衰退排列：短周期率先转弱，长期趋势尚未反转')
    if diffusion == 'up' and ladder == 'RPS20>60>120':
        alerts.append('扩散翻多：三周期RPS同步上升且短>中>长')
    if diffusion == 'down' and ladder == 'RPS20<60<120':
        alerts.append('扩散翻空：三周期RPS同步下降且短<中<长')
    if covering:
        alerts.append(covering_alert)
    state = ('衰退升级' if weakening and r20 < 70 else '强势衰退' if weakening else
        '扩散翻多' if diffusion == 'up' and ladder == 'RPS20>60>120' else
        '扩散翻空' if diffusion == 'down' and ladder == 'RPS20<60<120' else
        '衰退排列' if ladder == 'RPS20<60<120' and r120 >= 80 else
        covering_state if covering else '常规')
    return dict(ts_code=record.get('ts_code'), name=record.get('name'), sector=record.get('sector'),
        main_code=record.get('main_code'), phase=record.get('phase'), trend_direction=record.get('trend_direction'),
        rps20=round(r20, 1), rps60=round(r60, 1), rps120=round(r120, 1), rps20_prev5=round(p20, 1), rps_slope5=round(slope5, 1),
        ladder=ladder, diffusion=diffusion, oi_change5=oi5 if _finite(oi5) else None,
        return5=ret5 if _finite(ret5) else None, volume_ratio=record.get('volume_ratio'),
        carry_annualized=record.get('carry_annualized'), carry_change5=record.get('carry_change5'),
        structure=record.get('structure'), structure_flip5=record.get('structure_flip5'),
        alerts=alerts, alert_count=len(alerts), state=state)


STRUCTURE_SYNERGY_MIN = 55


def _clamp(value, low=0.0, high=10.0):
    return max(low, min(high, value))


def _dim(state, direction, long_earned, short_earned, strength=None, change=None, ok=True):
    return dict(state=state, direction=direction, strength=strength, change=change,
        long=round(long_earned, 2) if ok else None, short=round(short_earned, 2) if ok else None,
        status='ok' if ok else 'missing')


def _structure_oi(record):
    """资金维度：价格方向×OI方向=资金性质；OI加速视为强化。"""
    ret5, oi5, oi20 = (record.get(k) for k in ['return5', 'oi_change5', 'oi_change20'])
    if not _finite(ret5, oi5):
        return _dim('无数据', None, 0, 0, ok=False)
    up, oi_up = ret5 > 0, oi5 > 0
    if up and oi_up:
        state, direction, base = '新多进入', 'long', 8
    elif up:
        state, direction, base = '空头平仓', 'long', 3
    elif oi_up:
        state, direction, base = '新空进入', 'short', 8
    else:
        state, direction, base = '多头撤退', 'short', 3
    change = None
    if _finite(oi20):
        pace5, pace20 = oi5 / 5, oi20 / 20
        if pace5 * pace20 < 0:
            change = '减弱'
        elif abs(pace5) > abs(pace20):
            change = '强化'
        else:
            change = '平稳'
    earned = _clamp(base + (2 if change == '强化' else -2 if change == '减弱' else 0))
    long_e, short_e = (earned, 0.0) if direction == 'long' else (0.0, earned)
    return _dim(state, direction, long_e, short_e, round(min(abs(oi5), 20) / 20 * 10, 1), change)


def _structure_basis(record):
    """现货维度：现货与基差同向=现货真实性确认；仅一项同向给半分。"""
    spot5, basis5 = record.get('spot_change5'), record.get('basis_change5')
    if not _finite(spot5, basis5):
        return _dim('无数据（未导入现货）', None, 0, 0, ok=False)
    if spot5 > 0 and basis5 > 0:
        state = '现货强·基差改善'
    elif spot5 < 0 and basis5 < 0:
        state = '现货弱·基差走弱'
    elif spot5 > 0:
        state = '现货强·基差转弱'
    elif spot5 < 0:
        state = '现货弱·基差转强'
    else:
        state = '现货平稳'
    direction = 'long' if spot5 > 0 else ('short' if spot5 < 0 else None)
    long_hits, short_hits = int(spot5 > 0) + int(basis5 > 0), int(spot5 < 0) + int(basis5 < 0)
    change = '强化' if (long_hits == 2 or short_hits == 2) else ('减弱' if spot5 * basis5 < 0 else '平稳')
    return _dim(state, direction, 10 if long_hits == 2 else 5 if long_hits == 1 else 0,
        10 if short_hits == 2 else 5 if short_hits == 1 else 0, round(min(abs(spot5), 3) / 3 * 10, 1), change)


def _structure_spread(record):
    """跨期维度：月差变化答"近端供需正在变紧还是变松"，当前月差符号给方向加成。"""
    spread5, spread = record.get('spread_change5'), record.get('spread')
    if not _finite(spread5):
        return _dim('无数据', None, 0, 0, ok=False)
    if spread5 > 0:
        state, direction = '近端转紧', 'long'
    elif spread5 < 0:
        state, direction = '近端转松', 'short'
    else:
        state, direction = '近端平稳', None
    long_e = 8 * (spread5 > 0) + 2 * (spread5 > 0 and _finite(spread) and spread > 0)
    short_e = 8 * (spread5 < 0) + 2 * (spread5 < 0 and _finite(spread) and spread < 0)
    change = '强化' if _finite(spread) and spread5 * spread > 0 else ('减弱' if _finite(spread) and spread != 0 else None)
    return _dim(state, direction, long_e, short_e, round(min(abs(spread5), 20) / 20 * 10, 1), change)


def _structure_term(record):
    """曲线维度：整条曲线定价的短缺/过剩，Carry动量同向与五日拐点各加成2分。"""
    carry, carry5, flip5 = (record.get(k) for k in ['carry_annualized', 'carry_change5', 'structure_flip5'])
    if not _finite(carry):
        return _dim('无数据', None, 0, 0, ok=False)
    label = record.get('structure')
    if label not in ('Backwardation', 'Contango', '平坦'):
        label = 'Backwardation' if carry > 0 else ('Contango' if carry < 0 else '平坦')
    state = {'Backwardation': 'Back（近强远弱）', 'Contango': 'Contango（近弱远强）', '平坦': '平坦'}[label]
    direction = 'long' if label == 'Backwardation' else ('short' if label == 'Contango' else None)
    earned = 0.0
    if direction:
        earned = 6 + (2 if _finite(carry5) and carry5 * carry > 0 else 0) + (2 if flip5 is True else 0)
    long_e, short_e = (earned, 0.0) if direction == 'long' else ((0.0, earned) if direction == 'short' else (0.0, 0.0))
    change = None
    if direction and _finite(carry5):
        change = '强化' if carry5 * carry > 0 else ('减弱' if carry5 * carry < 0 else '平稳')
    return _dim(state, direction, long_e, short_e, round(min(abs(carry), 20) / 20 * 10, 1), change)


def _structure_inventory(record):
    """库存维度：当前外部导入仅含现货与全品种OI，库存/仓单未接入，占位缺失。"""
    inv = record.get('inventory_change5')
    if not _finite(inv):
        return _dim('无数据（库存未接入）', None, 0, 0, ok=False)
    direction = 'short' if inv > 0 else ('long' if inv < 0 else None)
    earned = 8 if direction else 0
    long_e, short_e = (0.0, earned) if direction == 'short' else ((earned, 0.0) if direction == 'long' else (0.0, 0.0))
    return _dim('累库' if inv > 0 else ('去库' if inv < 0 else '库存平稳'), direction, long_e, short_e,
        round(min(abs(inv), 10) / 10 * 10, 1), None)


def structure_radar(record):
    """商品结构雷达：资金(OI)/现货(基差)/跨期(月差)/曲线(期限结构)/库存 五维度，方向无关。

    技术面回答"价格有没有开始动"，结构面回答"为什么动、能不能继续动"。
    结构占优方向与价格趋势相反且结构分≥55时标"多/空头酝酿"——对应"结构先变、价格后动"。
    缺失维度不计入可用分，按可用维度归一，不虚构库存或现货数值。
    """
    dims = dict(oi=_structure_oi(record), basis=_structure_basis(record), spread=_structure_spread(record),
        term=_structure_term(record), inventory=_structure_inventory(record))
    coverage = sum(1 for d in dims.values() if d['status'] == 'ok')
    available = coverage * 10
    long_score = round(sum(d['long'] for d in dims.values() if d['status'] == 'ok') / available * 100, 1) if available else None
    short_score = round(sum(d['short'] for d in dims.values() if d['status'] == 'ok') / available * 100, 1) if available else None
    dominant = None
    if long_score is not None:
        if long_score - short_score >= 10:
            dominant = 'long'
        elif short_score - long_score >= 10:
            dominant = 'short'
    trend = record.get('trend_direction')
    divergence, quality = None, None
    if trend in ('long', 'short') and long_score is not None:
        aligned = long_score if trend == 'long' else short_score
        quality = '强' if aligned >= 65 else ('中' if aligned >= 50 else '弱')
        if dominant and dominant != trend and max(long_score, short_score) >= STRUCTURE_SYNERGY_MIN:
            divergence = '多头酝酿' if dominant == 'long' else '空头酝酿'
    return dict(ts_code=record.get('ts_code'), name=record.get('name'), sector=record.get('sector'),
        main_code=record.get('main_code'), phase=record.get('phase'), trend_direction=trend,
        oi=dims['oi'], basis=dims['basis'], spread=dims['spread'], term=dims['term'], inventory=dims['inventory'],
        long_score=long_score, short_score=short_score, dominant=dominant,
        long_bias=dominant == 'long', short_bias=dominant == 'short',
        divergence=divergence, quality=quality, coverage=coverage)


def annotate_options(payload, option_payload):
    """期权观察页：给每张期权附加可做性评分（标的特征×期权爆发结构×时间成本）。就地写入 records。"""
    rows = option_payload.get('records', [])
    chain_by_main = {}
    for row in rows:
        chain_by_main.setdefault(row.get('main_code'), []).append(row)
    records_by_code = {r.get('ts_code'): r for r in payload.get('records', [])}
    for main_code, chain in chain_by_main.items():
        underlying = records_by_code.get(main_code)
        scans = {}
        if underlying is not None:
            for direction in ('long', 'short'):
                try:
                    scans[direction] = scan_one(underlying, direction, chain)
                except Exception:
                    scans[direction] = None
        # 同组（同到期同方向）Gamma×F 最大值，用于 Gamma 相对归一。
        gamma_max = {}
        for row in chain:
            g, f = row.get('gamma'), row.get('underlying_close')
            if _finite(g, f) and f > 0:
                key = (row.get('maturity_date'), row.get('call_put'))
                gamma_max[key] = max(gamma_max.get(key, 0.0), g * f)
        for row in chain:
            try:
                row['tradability'] = option_tradability(row, scans, gamma_max)
            except Exception:
                row['tradability'] = None
    return option_payload


def option_tradability(row, scans, gamma_max):
    """单张期权的快速上涨潜力评分（0–100）。
    标的发动机55（爆发指数归一+共振/突破标签）＋期权爆发结构30（Gamma甜区15/IV未透支10/流动性5）
    ＋时间成本15（DTE适配，末日轮高Gamma但行情必须快；Theta日损耗>8%权利金扣分）。"""
    direction = 'long' if row.get('call_put') == 'C' else 'short'
    scan = scans.get(direction)
    dte, adelta = row.get('days_to_expiry'), row.get('delta')
    gamma, fprice = row.get('gamma'), row.get('underlying_close')
    iv, hv20, vol, oi, prem, theta = (row.get(k) for k in
        ['iv_reference', 'hv20', 'vol', 'oi', 'premium', 'theta'])
    tags = []
    if not (_finite(dte, adelta, gamma, fprice, vol, oi) and fprice > 0):
        return dict(score=None, grade='缺数据', tags=['Greeks缺失'], direction=direction,
            underlying_name=None, trend_direction=None, phase=None, explosion=None,
            breakdown=None, depth=None, iv_premium_pct=None, aligned=None, counter_trend=None)
    ad = abs(adelta)
    # —— A 标的发动机 55 ——
    a_avail = 55
    if scan is None:
        a_earn = 0.0
        tags.append('无标的评分')
        trend_dir, phase, explosion = None, None, None
    else:
        a_earn = round(min(55.0, (scan.get('explosion_score') or 0) * 0.65), 2)
        sig = scan.get('signals', {})
        if scan.get('resonance'):
            tags.append('四重共振')
        for key, label in [('breakout', '标的突破'), ('adx_turn', 'ADX拐头'),
                           ('rps_rise', 'RPS加速'), ('oi_up', '增仓')]:
            if sig.get(key) is True:
                tags.append(label)
        trend_dir = scan.get('trend_direction')
        phase = scan.get('phase')
        explosion = scan.get('explosion_score')
    # 方向闸门：标的已有明确趋势而期权方向相反时，发动机证据只承认一半
    # （增仓/放量/期限/IV等无方向分项可能给错误方向凑分），且总分硬封顶55，
    # 逆趋势期权永远不进"良/优"——抄底摸顶必须人工显式打开。
    counter_trend = trend_dir in ('long', 'short') and trend_dir != direction
    aligned = None if trend_dir is None else (not counter_trend if trend_dir != 'neutral' else None)
    if counter_trend:
        a_earn = round(a_earn * 0.5, 2)
        tags.append('逆趋势')
    # —— B1 Gamma 甜区 15（同组相对Gamma 10 + Delta位置 5）——
    gmax = gamma_max.get((row.get('maturity_date'), row.get('call_put')), 0.0)
    gnorm = (gamma * fprice / gmax) if gmax > 0 else 0.0
    gamma_pts = round(10 * min(1.0, gnorm), 2)
    if 0.25 <= ad <= 0.50:
        delta_pts = 5
    elif 0.15 <= ad < 0.25 or 0.50 < ad <= 0.60:
        delta_pts = 3
    elif ad >= 0.10:
        delta_pts = 1
    else:
        delta_pts = 0
    if ad < 0.10:
        tags.append('深虚值')
    if 0.20 <= ad <= 0.60 and gnorm >= 0.66:
        tags.append('Gamma甜区')
    # —— B2 IV 未透支 10 ——
    iv_earn, iv_avail, premium_pct = 0.0, 0, None
    if _finite(iv) and iv > 0:
        iv_avail = 10
        if _finite(hv20) and hv20 > 0:
            premium_pct = round((iv - hv20) / hv20 * 100, 1)
            if premium_pct <= 0:
                iv_earn, tag = 10.0, 'IV便宜'
            elif premium_pct <= 15:
                iv_earn, tag = 8.0, None
            elif premium_pct <= 30:
                iv_earn, tag = 5.0, None
            else:
                iv_earn, tag = 0.0, 'IV透支'
            if tag:
                tags.append(tag)
        else:
            iv_earn = 5.0
    # —— B3 流动性 5 ——
    depth = int(min(vol, oi))
    liq_pts = 5 if depth >= 2000 else (4 if depth >= 1000 else (2 if depth >= 300 else 1))
    if depth < 300:
        tags.append('流动性偏薄')
    # —— C 时间/成本 15 ——
    if dte <= 2:
        dte_pts = 6
        tags.append('末日轮')
        tags.append('最后两天')
    elif dte <= 7:
        dte_pts = 12
        tags.append('末日轮')
    elif dte <= 15:
        dte_pts = 15
    elif dte <= 30:
        dte_pts = 9
    elif dte <= 60:
        dte_pts = 5
    else:
        dte_pts = 2
    # Theta 日损耗 >8% 权利金：末日轮的 DTE 档已折让（12/6 分），只警示不二次扣分；其余档位扣分。
    if _finite(prem, theta) and prem > 0:
        theta_drag = abs(theta) / prem * 100
        if theta_drag > 8:
            tags.append('Theta损耗重')
            if dte > 7:
                dte_pts = max(0, dte_pts - 3)
    earned = a_earn + gamma_pts + delta_pts + iv_earn + liq_pts + dte_pts
    available = a_avail + 10 + 5 + iv_avail + 5 + 15
    score = round(earned / available * 100, 1)
    if counter_trend:
        score = round(min(score, 55.0), 1)  # 硬封顶：逆趋势最高"可关注"，不进良/优
    grade = '优' if score >= 80 else ('良' if score >= 65 else ('可关注' if score >= 50 else '弱'))
    return dict(score=score, grade=grade, tags=tags, direction=direction, aligned=aligned,
        counter_trend=counter_trend,
        underlying_name=(scan.get('name') if scan else None), trend_direction=trend_dir,
        phase=phase, explosion=explosion,
        breakdown=dict(underlying=round(a_earn, 1), underlying_max=a_avail,
            gamma=gamma_pts, delta=delta_pts,
            iv=iv_earn if iv_avail else None, iv_max=iv_avail,
            liquidity=liq_pts, dte=dte_pts),
        depth=depth, iv_premium_pct=premium_pct)


def build_scanner(payload, options, top=5):
    chains = {}
    for row in options.get('records', []):
        chains.setdefault(row.get('main_code'), []).append(row)
    result = dict(asof=payload.get('asof'), weights=WEIGHTS, signal_keys=SIGNAL_KEYS, notes=NOTES,
        top=int(top), long=[], short=[], extended=[], extension_note=EXTENSION_NOTE)

    def scan_all(direction):
        rows = []
        for record in payload.get('records', []):
            if record.get('direction') != direction:
                continue
            scanned = scan_one(record, direction, chains.get(record.get('ts_code'), []))
            if scanned['explosion_score'] is not None:
                rows.append(scanned)
        # 期权扫描以“可操作”为前提：没有任何可评估期权合约的品种沉到有合约品种之后。
        rows.sort(key=lambda r: (-int(r['option_ready']), -r['explosion_score'], -r['signals_met'], r['ts_code']))
        return rows[:max(1, int(top))]

    for direction in ['long', 'short']:
        result[direction] = scan_all(direction)
    # 过度延伸观察：阶段判定为"过度延伸"且阶段方向与扫描方向一致（phase_match）的品种，双向独立列出。
    extended = []
    for record in payload.get('records', []):
        if record.get('phase') != '过度延伸' or record.get('phase_match') is not True:
            continue
        direction = record.get('direction')
        if direction not in ['long', 'short']:
            continue
        scanned = scan_one(record, direction, chains.get(record.get('ts_code'), []))
        if scanned['explosion_score'] is None:
            continue
        scanned['direction'] = direction
        extended.append(scanned)
    extended.sort(key=lambda r: (-int(r['option_ready']), -r['explosion_score'], -r['signals_met'], r['ts_code']))
    result['extended'] = extended
    # 反转雷达：品种级去重（两个方向行的原始字段相同），与方向扫描互补、不改变原榜单。
    seen, radar = set(), []
    for record in payload.get('records', []):
        code = record.get('ts_code')
        if code in seen:
            continue
        seen.add(code)
        row = radar_row(record)
        if row is not None:
            radar.append(row)
    radar.sort(key=lambda r: (-r['alert_count'], -abs(r['rps_slope5']), r['ts_code']))
    result['radar'] = radar
    result['radar_note'] = RADAR_NOTE
    # 商品结构雷达：品种级（去重），覆盖 5 维度中至少 1 项数据的品种；背离品种优先，其次按结构分。
    seen, structure = set(), []
    for record in payload.get('records', []):
        code = record.get('ts_code')
        if code in seen:
            continue
        seen.add(code)
        row = structure_radar(record)
        if row['coverage'] == 0:
            continue
        row['best_score'] = max(row['long_score'] or 0, row['short_score'] or 0)
        structure.append(row)
    structure.sort(key=lambda r: (0 if r['divergence'] else 1, -r['best_score'], -r['coverage'], r['ts_code']))
    result['structure'] = structure
    result['structure_note'] = STRUCTURE_NOTE
    return result
