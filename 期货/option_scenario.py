"""Pure option target/stop scenarios derived from commodity price levels."""
import math

from option_analysis import black76


STAGE_HORIZONS = {'START': 5, 'PREPARE': 10, 'TREND': 10}
DEFAULT_STAGE_HORIZON = 10
IV_FACTORS = {'conservative': .90, 'base': 1.0, 'optimistic': 1.10}


def _finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def stage_horizon(state):
    return STAGE_HORIZONS.get(state, DEFAULT_STAGE_HORIZON)


def classify_rr(value):
    if not _finite(value) or float(value) < 1.2:
        return '不可做'
    if float(value) >= 3.0:
        return '强烈信号'
    if float(value) >= 2.0:
        return '可做'
    return '观察'


def scenario_levels(record, option, direction):
    current = option.get('underlying_close')
    close = record.get('close')
    if not (_finite(current) and float(current) > 0 and _finite(close) and float(close) > 0):
        return dict(status='blocked', reason='标的价位缺失')
    current = float(current)
    scale = current / float(close)
    levels = {}
    for key in ('support', 'resistance', 'breakout', 'reversal'):
        value = record.get(f'tomorrow_{key}')
        levels[key] = float(value) * scale if _finite(value) and float(value) > 0 else None
    if direction == 'long':
        targets = [levels[key] for key in ('resistance', 'breakout')
                   if _finite(levels[key]) and levels[key] > current]
        stops = [levels[key] for key in ('support', 'reversal')
                 if _finite(levels[key]) and levels[key] < current]
        target = min(targets) if targets else None
        stop = max(stops) if stops else None
    elif direction == 'short':
        targets = [levels[key] for key in ('support', 'reversal')
                   if _finite(levels[key]) and levels[key] < current]
        stops = [levels[key] for key in ('resistance', 'breakout')
                 if _finite(levels[key]) and levels[key] > current]
        target = max(targets) if targets else None
        stop = min(stops) if stops else None
    else:
        return dict(status='blocked', reason='商品方向缺失')
    if target is None:
        return dict(status='blocked', reason='目标价位缺失')
    if stop is None:
        return dict(status='blocked', reason='失效价位缺失')
    return dict(status='ok', current=round(current, 4), scale=round(scale, 8),
        target=round(target, 4), stop=round(stop, 4), levels=levels)


def option_scenario(record, option, direction):
    state = record.get('state_v2')
    trading_days = stage_horizon(state)
    dte = option.get('days_to_expiry')
    calendar_days = math.ceil(trading_days * 7 / 5)
    if not _finite(dte) or float(dte) <= calendar_days:
        return dict(status='blocked', reason='到期时间不足', trading_days=trading_days,
            calendar_days=calendar_days)
    values = [option.get(key) for key in
              ('premium', 'exercise_price', 'iv_reference', 'underlying_close')]
    if not all(_finite(value) and float(value) > 0 for value in values):
        return dict(status='blocked', reason='期权定价输入缺失')
    call_put = option.get('call_put')
    if call_put not in ('C', 'P'):
        return dict(status='blocked', reason='期权方向缺失')
    levels = scenario_levels(record, option, direction)
    if levels['status'] != 'ok':
        return levels | dict(trading_days=trading_days, calendar_days=calendar_days)
    premium, strike, iv = (float(option[key]) for key in
                           ('premium', 'exercise_price', 'iv_reference'))
    rate = float(option.get('rate', .02)) if _finite(option.get('rate', .02)) else .02
    remaining = (float(dte) - calendar_days) / 365
    target_prices, stop_prices = {}, {}
    for name, factor in IV_FACTORS.items():
        volatility = iv / 100 * factor
        target = black76(levels['target'], strike, remaining, rate, volatility, call_put)
        stop = black76(levels['stop'], strike, remaining, rate, volatility, call_put)
        if target is None or stop is None:
            return dict(status='blocked', reason='情景定价失败')
        target_prices[name] = round(target, 4)
        stop_prices[name] = round(stop, 4)
    expected_gain = max(target_prices['conservative'] - premium, 0.0)
    risk_floor = max(premium * .01, .0001)
    expected_risk = max(premium - stop_prices['conservative'], risk_floor)
    rr = expected_gain / expected_risk
    return dict(status='ok', state=state, trading_days=trading_days,
        calendar_days=calendar_days, remaining_days=round(float(dte)-calendar_days, 2),
        current_underlying=levels['current'], target_underlying=levels['target'],
        stop_underlying=levels['stop'], level_scale=levels['scale'],
        target_prices=target_prices, stop_prices=stop_prices,
        current_premium=round(premium, 4), expected_gain=round(expected_gain, 4),
        expected_risk=round(expected_risk, 4), conservative_rr=round(rr, 3),
        signal_level=classify_rr(rr),
        iv_factors=IV_FACTORS, note='日线Black-76模型研究值，非可成交报价')
