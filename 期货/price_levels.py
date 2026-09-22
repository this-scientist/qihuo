# -*- coding: utf-8 -*-
"""真实月合约的支撑/压力位：只用未复权真实月份 OHLC + 成交/持仓，全部因果（shift(1)），可复现。

复权主连不能用于绝对价位，输入必须是真实合约历史（data/processed/pair_history）。
输出只是"事实基准"，不构成方向判断或交易指令；缺失项一律标注而不是补零。
"""
import math

WINDOWS = (20, 55, 250)
DENSITY_LOOKBACK = 120
DENSITY_KEEP = 2
ATR_BANDS = (1.0, 2.0)
MERGE_PCT = 0.003
TOUCH_PCT = 0.005
MIN_ROWS = 30


def _finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _num(value):
    return float(value) if _finite(value) else None


def normalize_rows(history):
    """接受 DataFrame 或 list[dict]，输出按 trade_date 升序、字段均为有限正数的干净行。"""
    if history is None:
        return []
    records = None
    if hasattr(history, 'to_dict') and hasattr(history, 'columns'):
        try:
            frame = history
            if 'trade_date' in frame.columns:
                frame = frame.sort_values('trade_date')
            records = frame.to_dict('records')
        except Exception:
            return []
    elif isinstance(history, (list, tuple)):
        records = list(history)
    if not records:
        return []
    rows = []
    for row in records:
        if not all(_finite(row.get(key)) and float(row[key]) > 0 for key in ('high', 'low', 'close')):
            continue
        rows.append(dict(high=float(row['high']), low=float(row['low']), close=float(row['close']),
            vol=_num(row.get('vol')) or 0.0, oi=_num(row.get('oi')),
            trade_date=str(row.get('trade_date', '')), main_code=row.get('main_code')))
    rows.sort(key=lambda r: r['trade_date'])
    return rows


def wilder_atr(rows, period=14):
    """Wilder ATR：不足 period+1 根返回 None。"""
    if len(rows) < period + 1:
        return None
    trs, prev_close = [], rows[0]['close']
    for row in rows[1:]:
        tr = max(row['high'] - row['low'], abs(row['high'] - prev_close), abs(row['low'] - prev_close))
        trs.append(tr)
        prev_close = row['close']
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def _round_step(price):
    """按价位量级取一个"好看"的关口步长（约 1%）。"""
    raw = max(price * 0.01, 1e-8)
    magnitude = 10 ** math.floor(math.log10(raw))
    for multiple in (1, 2, 5, 10):
        if raw <= magnitude * multiple:
            return magnitude * multiple
    return magnitude * 10


def _window_extremes(rows):
    """因果窗口极值：用除最后一根之外的样本（等价于 shift(1)）。"""
    history = rows[:-1]
    out = []
    for window in WINDOWS:
        if len(history) < window:
            continue
        sample = history[-window:]
        out.append(dict(window=window, high=max(r['high'] for r in sample), low=min(r['low'] for r in sample)))
    return out


def _density_levels(rows, atr, last):
    """成交量密集区：近 DENSITY_LOOKBACK 根按 0.5×ATR 分箱，取当前价下方/上方各 DENSITY_KEEP 个最密集箱中值。"""
    sample = rows[:-1][-DENSITY_LOOKBACK:]
    if len(sample) < 20 or not _finite(atr) or atr <= 0:
        return []
    width = max(atr * 0.5, last * 0.002)
    bins = {}
    for row in sample:
        low_index = int((row['low'] - 0) // width)
        high_index = int((row['high'] - 0) // width)
        span = max(1, high_index - low_index + 1)
        for index in range(low_index, high_index + 1):
            bins[index] = bins.get(index, 0.0) + row['vol'] / span
    ranked = sorted(bins.items(), key=lambda item: (-item[1], item[0]))
    below, above = [], []
    for index, volume in ranked:
        if volume <= 0:
            continue
        price = (index + 0.5) * width
        target = below if price < last else above
        if len(target) < DENSITY_KEEP:
            target.append(dict(price=price, volume=volume))
        if len(below) >= DENSITY_KEEP and len(above) >= DENSITY_KEEP:
            break
    return below + above


def _touches(rows, price, window=120):
    """统计近 window 根中价格区间覆盖该位的次数（触及强度）。"""
    sample = rows[:-1][-window:]
    return sum(1 for row in sample
               if row['low'] <= price * (1 + TOUCH_PCT) and row['high'] >= price * (1 - TOUCH_PCT))


def compute_levels(history, last=None, atr14=None, main_code=None):
    """输出支撑/压力位。history 为真实月合约历史（未复权），last/atr14 可外部传入以便与盘面一致。"""
    rows = normalize_rows(history)
    notes = []
    if len(rows) < MIN_ROWS:
        return dict(last=_num(last), atr14=_num(atr14), main_code=main_code,
            support=[], resistance=[], coverage=0,
            notes=['有效历史不足 %d 根，无法计算支撑压力位' % MIN_ROWS])
    if last is None:
        last = rows[-1]['close']
    last = float(last)
    if not _finite(atr14) or atr14 <= 0:
        atr14 = wilder_atr(rows)
    main_codes = {r['main_code'] for r in rows[-min(len(rows), max(WINDOWS)):] if r.get('main_code')}
    if len(main_codes) > 1:
        notes.append('近 %d 根K线内主力合约发生切换（%s），长周期价位可能跨换月'
                     % (max(WINDOWS), '/'.join(sorted(main_codes))))

    candidates = []  # (price, source, weight)

    def add(price, source, weight):
        if _finite(price) and price > 0:
            candidates.append(dict(price=float(price), source=source, weight=weight))

    extremes = _window_extremes(rows)
    missing_windows = [w for w in WINDOWS if w not in {item['window'] for item in extremes}]
    if missing_windows:
        notes.append('历史仅 %d 根，缺少 %s 日窗口（长周期支撑压力不完整）'
                     % (len(rows), '/'.join(str(w) for w in missing_windows)))
    for item in extremes:
        add(item['low'], '近%d日低点' % item['window'], 2 if item['window'] >= 55 else 1)
        add(item['high'], '近%d日高点' % item['window'], 2 if item['window'] >= 55 else 1)

    if _finite(atr14) and atr14 > 0:
        for multiple in ATR_BANDS:
            add(last - multiple * atr14, 'ATR通道 -%.0f倍' % multiple, 1)
            add(last + multiple * atr14, 'ATR通道 +%.0f倍' % multiple, 1)

    step = _round_step(last)
    step_note = '整数关口（步长%s）' % _format_step(step)
    add(math.floor((last * (1 - 0.0005)) / step) * step, step_note, 1)
    add(math.ceil((last * (1 + 0.0005)) / step) * step, step_note, 1)

    for item in _density_levels(rows, atr14, last):
        add(item['price'], '成交密集区', 2 if item['volume'] > 0 else 1)

    support, resistance = [], []
    for item in candidates:
        price, source, weight = item['price'], item['source'], item['weight']
        bucket = support if price < last else resistance
        for entry in bucket:
            if abs(entry['price'] - price) <= last * MERGE_PCT:
                entry['sources'].append(source)
                entry['weight'] += weight
                entry['sum'] += price * weight
                entry['price'] = entry['sum'] / max(entry['weight'], 1)
                break
        else:
            bucket.append(dict(price=price, sources=[source], weight=weight, sum=price * weight))

    def finalize(bucket, keep):
        out = []
        for entry in bucket:
            sources = list(dict.fromkeys(entry['sources']))
            touches = _touches(rows, entry['price'])
            strength = '强' if entry['weight'] >= 4 and touches >= 3 else '中' if entry['weight'] >= 2 else '弱'
            out.append(dict(price=round(entry['price'], 4), sources=sources,
                distance_pct=round((entry['price'] / last - 1) * 100, 3), strength=strength,
                touches=touches))
        out.sort(key=lambda item: abs(item['price'] - last))
        return out[:keep]

    keep = 6
    result = dict(last=round(last, 4), atr14=round(atr14, 4) if _finite(atr14) else None,
        main_code=main_code, support=finalize(support, keep), resistance=finalize(resistance, keep),
        coverage=len(candidates), notes=notes)
    if not result['support']:
        notes.append('当前价下方没有可确认的支撑位（数据窗口不足或价格处于区间低位）')
    if not result['resistance']:
        notes.append('当前价上方没有可确认的压力位（数据窗口不足或价格处于区间高位）')
    return result


def _format_step(step):
    if step >= 1:
        return str(int(round(step)))
    return ('%g' % step)
