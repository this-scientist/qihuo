"""Validated main-contract holding rankings for display-only dashboard context."""
import math
import re

import pandas as pd

from collector import DataError, LIMITS, required


HOLDING_FIELDS = [
    'trade_date', 'symbol', 'broker', 'vol', 'vol_chg',
    'long_hld', 'long_chg', 'short_hld', 'short_chg', 'exchange',
]
HOLDING_VALUE_FIELDS = ['vol', 'long_hld', 'short_hld']
HOLDING_CHANGE_FIELDS = ['vol_chg', 'long_chg', 'short_chg']


def holding_query(ts_code, exchange, trade_date=None):
    contract = str(ts_code).split('.')[0]
    symbol = contract.lower() if exchange == 'GFEX' else contract.upper()
    if exchange == 'CZCE':
        standard = re.fullmatch(r'([A-Za-z]+)\d(\d{3})', contract)
        native = re.fullmatch(r'([A-Za-z]+)(\d{3})', contract)
        match = standard or native
        if match is None:
            raise DataError(f'Invalid CZCE holding contract: {ts_code}')
        symbol = f'{match.group(1).upper()}{match.group(2)}'
    return {
        'trade_date': trade_date,
        'symbol': symbol,
        'exchange': 'SHFE' if exchange == 'INE' else exchange,
    }


def symbol_matches(ts_code, exchange, response_symbol):
    expected = holding_query(ts_code, exchange)['symbol']
    standard = str(ts_code).split('.')[0]
    return str(response_symbol).casefold() in {expected.casefold(), standard.casefold()}


def invalid_broker(value):
    text = '' if pd.isna(value) else str(value).strip()
    return not text or '\ufffd' in text or any(ord(char) < 32 for char in text)


def _broker_rows(rows, side):
    holding_field, change_field = f'{side}_hld', f'{side}_chg'
    output = []
    for row in rows.head(5).itertuples():
        change = getattr(row, change_field)
        output.append({
            'broker': str(row.broker),
            'holding': float(getattr(row, holding_field)),
            'change': float(change) if pd.notna(change) else None,
        })
    return output


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
    for field in HOLDING_VALUE_FIELDS + HOLDING_CHANGE_FIELDS:
        raw = clean[field]
        clean[field] = pd.to_numeric(raw, errors='coerce')
        if (raw.notna() & clean[field].isna()).any():
            raise DataError(f'Invalid holding numeric value: {field}')
        if not clean[field].dropna().map(lambda value: math.isfinite(float(value))).all():
            raise DataError(f'Non-finite holding numeric value: {field}')
    if any((clean[field].dropna() < 0).any() for field in HOLDING_VALUE_FIELDS):
        raise DataError('Negative holding rank value')
    return clean


def unavailable_summary(target, status, reason):
    return {
        'ts_code': target['ts_code'],
        'holding_contract': target['contract'],
        'holding_trade_date': target['trade_date'],
        'holding_status': status,
        'holding_reason': reason,
        'top20_long': None,
        'top20_short': None,
        'top20_net': None,
        'top20_long_change': None,
        'top20_short_change': None,
        'top20_net_change': None,
        'top20_long_concentration': None,
        'top20_short_concentration': None,
        'top_long_brokers': [],
        'top_short_brokers': [],
    }


def _rank_change(rows, field):
    return None if rows[field].isna().any() else float(rows[field].sum())


def summarize_holding(frame, target, main_oi):
    clean = validate_holding(frame, target)
    long_rows = clean.dropna(subset=['long_hld']).nlargest(20, 'long_hld')
    short_rows = clean.dropna(subset=['short_hld']).nlargest(20, 'short_hld')
    if long_rows.empty or short_rows.empty:
        return unavailable_summary(target, 'invalid', '席位多仓或空仓榜单缺失')

    long_total = float(long_rows.long_hld.sum())
    short_total = float(short_rows.short_hld.sum())
    long_change = _rank_change(long_rows, 'long_chg')
    short_change = _rank_change(short_rows, 'short_chg')
    numeric_only = any(invalid_broker(value) for value in clean.broker)
    result = unavailable_summary(
        target,
        'numeric_only' if numeric_only else 'available',
        '席位名称源数据异常' if numeric_only else None,
    )
    denominator = (float(main_oi) if main_oi is not None
                   and math.isfinite(float(main_oi)) and float(main_oi) > 0 else None)
    result.update(
        top20_long=long_total,
        top20_short=short_total,
        top20_net=long_total - short_total,
        top20_long_change=long_change,
        top20_short_change=short_change,
        top20_net_change=(long_change - short_change
                          if long_change is not None and short_change is not None else None),
        top20_long_concentration=long_total / denominator if denominator else None,
        top20_short_concentration=short_total / denominator if denominator else None,
        top_long_brokers=[] if numeric_only else _broker_rows(long_rows, 'long'),
        top_short_brokers=[] if numeric_only else _broker_rows(short_rows, 'short'),
    )
    concentrations = [result['top20_long_concentration'], result['top20_short_concentration']]
    if any(value is not None and not 0 <= value <= 1 for value in concentrations):
        return unavailable_summary(target, 'invalid', '席位集中度超出合理范围')
    return result
