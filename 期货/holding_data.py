"""Validated main-contract holding rankings for display-only dashboard context."""
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from collector import (DataError, LIMITS, atomic_csv, atomic_json, read_csv,
                       required)


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


def _holding_target(row, trade_date):
    return {
        'ts_code': str(row.main_code),
        'contract': str(row.ts_code),
        'exchange': str(row.exchange),
        'trade_date': trade_date,
        'main_oi': (float(row.oi) if pd.notna(row.oi) else None),
    }


def _cached_holding(path, params, target):
    receipt = path.with_suffix('.json')
    if not path.exists() or not receipt.exists():
        return None
    try:
        metadata = json.loads(receipt.read_text(encoding='utf-8'))
        if (metadata.get('version') != 1 or metadata.get('api') != 'fut_holding'
                or metadata.get('params') != params
                or metadata.get('sha256') != hashlib.sha256(path.read_bytes()).hexdigest()):
            return None
        return validate_holding(read_csv(path), target)
    except (DataError, OSError, ValueError):
        return None


def _save_holding(frame, path, params):
    atomic_csv(frame, path)
    atomic_json({
        'version': 1,
        'api': 'fut_holding',
        'params': params,
        'rows': len(frame),
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'validated_at': datetime.now().isoformat(),
    }, path.with_suffix('.json'))


def _status_counts(records):
    statuses = ['available', 'numeric_only', 'unavailable', 'invalid']
    return {status: sum(row['holding_status'] == status for row in records)
            for status in statuses}


def collect_main_holdings(collector, root, selected, trade_date, force=False):
    """Collect exact real-main contracts; contract failures become status rows."""
    root = Path(root)
    required(selected, ['ts_code', 'main_code', 'role', 'exchange', 'oi'])
    mains = selected[selected.role.eq('main')].copy()
    if mains.main_code.duplicated().any():
        raise DataError('Duplicate main contract in holding inputs')
    records = []
    for row in mains.itertuples(index=False):
        target = _holding_target(row, trade_date)
        params = holding_query(target['contract'], target['exchange'], trade_date)
        contract = target['contract'].split('.')[0]
        path = root/f'raw/holding/{target["exchange"]}/{trade_date}/{contract}.csv'
        frame = None if force else _cached_holding(path, params, target)
        try:
            if frame is None:
                frame = collector.call('fut_holding', **params)
                frame = validate_holding(frame, target)
                _save_holding(frame, path, params)
            records.append(summarize_holding(frame, target, target['main_oi']))
        except DataError as exc:
            records.append(unavailable_summary(target, 'unavailable', str(exc)))

    counts = _status_counts(records)
    usable = counts['available'] + counts['numeric_only']
    status = ('success' if usable == len(records) else
              'partial' if usable else 'unavailable')
    report = {
        'asof': trade_date,
        'status': status,
        'counts': counts,
        'records': records,
        'finished_at': datetime.now().isoformat(),
    }
    atomic_json({'asof': trade_date, 'records': records},
                root/f'processed/holding/{trade_date}.json')
    atomic_json(report, root/f'quality/holding_{trade_date}.json')
    return report


def collect_update_holdings(collector, root, trade_date, force=False):
    root = Path(root)
    selected_path = root/f'raw/selected/{trade_date}.csv'
    if selected_path.exists():
        return collect_main_holdings(
            collector, root, read_csv(selected_path), trade_date, force=force)
    report = {
        'asof': trade_date,
        'status': 'unavailable',
        'reason': f'selected contract snapshot unavailable: {selected_path}',
        'counts': _status_counts([]),
        'records': [],
        'finished_at': datetime.now().isoformat(),
    }
    atomic_json(report, root/f'quality/holding_{trade_date}.json')
    return report
