"""Futures-friendly version of the pasted stock B/S indicator."""
import math

import pandas as pd


def _finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _pivot(row):
    e = (float(row['high']) + float(row['low']) + float(row['open']) + 2 * float(row['close'])) / 5
    return dict(
        tomorrow_resistance=2 * e - float(row['low']),
        tomorrow_support=2 * e - float(row['high']),
        tomorrow_breakout=e + (float(row['high']) - float(row['low'])),
        tomorrow_reversal=e - (float(row['high']) - float(row['low'])),
    )


def _clean_history(history):
    required = ['trade_date', 'open', 'high', 'low', 'close']
    if history is None or not set(required).issubset(history.columns):
        return pd.DataFrame(columns=required)
    data = history.loc[:, required].copy()
    for field in ['open', 'high', 'low', 'close']:
        data[field] = pd.to_numeric(data[field], errors='coerce')
    data['trade_date'] = data['trade_date'].astype(str)
    return data.dropna(subset=['open', 'high', 'low', 'close']).sort_values('trade_date')


def signal_series(history):
    """Return per-bar futures signals from the source indicator's trend-state chain.

    The source formula treats the bullish chain as "red holding stock" and the
    bearish chain as "cyan watching". Futures can express both sides, so bullish
    reversal becomes buy/open-long and bearish reversal becomes sell/open-short.
    """
    data = _clean_history(history)
    if data.empty:
        return []
    rows = data.to_dict('records')
    output, previous_state = [], None
    for index, row in enumerate(rows):
        close = float(row['close'])
        if index < 2:
            state = None
        else:
            prev1 = float(rows[index - 1]['close'])
            prev2 = float(rows[index - 2]['close'])
            if close > prev1 and close > prev2:
                state = 'long'
            elif close < prev1 and close < prev2:
                state = 'short'
            else:
                state = previous_state
        previous_effective = previous_state
        previous_state = state or previous_state
        previous_code = output[-1]['signal_code'] if output else None
        if state == 'long' and previous_code == 'BUY1':
            code, label, side = 'BUY2', '二买', 'long'
        elif state == 'short' and previous_code == 'SELL1':
            code, label, side = 'SELL2', '二卖', 'short'
        elif state == 'long' and previous_effective == 'short':
            code, label, side = 'BUY1', '一买', 'long'
        elif state == 'short' and previous_effective == 'long':
            code, label, side = 'SELL1', '一卖', 'short'
        elif state == 'long':
            code, label, side = 'HOLD_LONG', '持多', 'long'
        elif state == 'short':
            code, label, side = 'HOLD_SHORT', '持空', 'short'
        else:
            code, label, side = 'WAIT', '等待', 'neutral'
        output.append(dict(
            trade_date=row['trade_date'],
            signal_code=code,
            signal_label=label,
            signal_side=side,
            close=close,
        ))
    return output


def signal_for_history(history):
    data = _clean_history(history)
    if data.empty:
        return dict(signal_code='WAIT', signal_label='等待', signal_side='neutral')
    signals = signal_series(data)
    latest = dict(signals[-1])
    if len(data) >= 2:
        latest.update({f'today_{key.removeprefix("tomorrow_")}': value
                       for key, value in _pivot(data.iloc[-2]).items()
                       if key in {'tomorrow_resistance', 'tomorrow_support'}})
    latest.update(_pivot(data.iloc[-1]))
    for key, value in list(latest.items()):
        if isinstance(value, float) and not _finite(value):
            latest[key] = None
    return latest


def chart_signals(history):
    return [dict(trade_date=row['trade_date'], code=row['signal_code'], label=row['signal_label'],
                 side=row['signal_side'], close=row['close'])
            for row in signal_series(history)
            if row['signal_code'] in {'BUY1', 'BUY2', 'SELL1', 'SELL2'}]
