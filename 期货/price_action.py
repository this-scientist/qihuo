"""Minimal price-action engine for the simplified option-buyer system."""
import math

import pandas as pd


def _finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _clean_history(history):
    required = ['trade_date', 'open', 'high', 'low', 'close']
    if history is None or not set(required).issubset(history.columns):
        return pd.DataFrame(columns=required)
    fields = required + [field for field in ['vol', 'oi'] if field in history.columns]
    data = history.loc[:, fields].copy()
    for field in ['open', 'high', 'low', 'close', 'vol', 'oi']:
        if field in data.columns:
            data[field] = pd.to_numeric(data[field], errors='coerce')
    data['trade_date'] = data['trade_date'].astype(str)
    return data.dropna(subset=['open', 'high', 'low', 'close']).sort_values('trade_date')


def _atr14(data):
    if data.empty:
        return None
    previous_close = data['close'].shift(1)
    ranges = pd.concat([
        data['high'] - data['low'],
        (data['high'] - previous_close).abs(),
        (data['low'] - previous_close).abs(),
    ], axis=1).max(axis=1)
    value = ranges.tail(14).mean()
    return float(value) if pd.notna(value) and math.isfinite(float(value)) else None


def _close_location(row):
    high, low, close = float(row['high']), float(row['low']), float(row['close'])
    span = high - low
    if span <= 0:
        return None
    return (close - low) / span


def _er20(data):
    if len(data) < 21:
        return None
    closes = data['close'].astype(float).tail(21).tolist()
    numerator = abs(closes[-1] - closes[0])
    denominator = sum(abs(closes[index] - closes[index - 1]) for index in range(1, len(closes)))
    return round(numerator / denominator, 4) if denominator else None


def structure_rr(target_price, entry_price, invalidation_price):
    if not all(_finite(value) for value in [target_price, entry_price, invalidation_price]):
        return None
    risk = abs(float(entry_price) - float(invalidation_price))
    if risk <= 0:
        return None
    reward = abs(float(target_price) - float(entry_price))
    return round(reward / risk, 4)


def _base_summary(data):
    close = float(data.iloc[-1]['close']) if not data.empty else None
    return dict(
        structure_side='range',
        lifecycle='base',
        event_type='none',
        trade_model=None,
        key_level=None,
        entry_reference=close,
        target_price=None,
        invalidation_price=None,
        structure_rr=None,
        breakout_quality=None,
        pullback_quality=None,
        er20=_er20(data),
        eligible_for_option_eval=False,
    )


def _breakout_summary(data, direction, key_level, atr):
    latest = data.iloc[-1]
    close = float(latest['close'])
    low = float(latest['low'])
    high = float(latest['high'])
    location = _close_location(latest)
    if direction == 'long':
        target = close + (key_level - float(data.iloc[:-1]['low'].tail(60).min()))
        invalidation = min(low, key_level)
        side = 'bullish'
    else:
        target = close - (float(data.iloc[:-1]['high'].tail(60).max()) - key_level)
        invalidation = max(high, key_level)
        side = 'bearish'
    rr = structure_rr(target, close, invalidation)
    return dict(
        structure_side=side,
        lifecycle='start',
        event_type='breakout',
        trade_model='A',
        key_level=round(float(key_level), 6),
        entry_reference=round(close, 6),
        target_price=round(float(target), 6),
        invalidation_price=round(float(invalidation), 6),
        structure_rr=rr,
        breakout_quality=dict(
            breakout_atr_multiple=round(abs(close - float(key_level)) / atr, 4) if atr and atr > 0 else None,
            close_location_pct=round(location, 4) if location is not None else None,
            close_in_top_quarter=location is not None and location >= 0.75 if direction == 'long' else None,
            close_in_bottom_quarter=location is not None and location <= 0.25 if direction == 'short' else None,
        ),
        pullback_quality=None,
        er20=_er20(data),
        eligible_for_option_eval=True,
    )


def price_action_summary(history):
    data = _clean_history(history)
    if data.empty:
        return _base_summary(data)
    summary = _base_summary(data)
    if len(data) < 61:
        return summary
    previous = data.iloc[:-1]
    latest = data.iloc[-1]
    close = float(latest['close'])
    atr = _atr14(data)
    high60 = float(previous['high'].tail(60).max())
    low60 = float(previous['low'].tail(60).min())
    location = _close_location(latest)
    if atr and atr > 0 and close > high60 and (close - high60) > 0.3 * atr and location is not None and location >= 0.75:
        return _breakout_summary(data, 'long', high60, atr)
    if atr and atr > 0 and close < low60 and (low60 - close) > 0.3 * atr and location is not None and location <= 0.25:
        return _breakout_summary(data, 'short', low60, atr)
    return summary
