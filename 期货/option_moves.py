"""Observed chronological close-to-close option moves, never a forecast or IV."""
import csv
import math
from pathlib import Path


def positive(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (ValueError, TypeError):
        return None


def summarize_moves(contracts, dates, quotes):
    result = {}
    for contract in contracts:
        dte = contract.get('days_to_expiry')
        if not isinstance(dte, (int, float)) or not 0 < dte <= 15:
            continue
        side, code, main = contract.get('call_put'), contract.get('ts_code'), contract.get('main_code')
        if side not in ('C', 'P') or not code or not main:
            continue
        group = result.setdefault(main, {}).setdefault(side, dict(status='complete', matches=[], contracts=0))
        group['contracts'] += 1
        prices = [(date, positive(quotes.get(date, {}).get(code))) for date in dates]
        if len(dates) != 5 or any(price is None for _, price in prices):
            group['status'] = 'incomplete'
        valid = [(date, price) for date, price in prices if price is not None]
        if len(valid) < 2:
            continue
        low_date, low = valid[0]
        best = None
        for date, price in valid[1:]:
            multiple = price / low
            if multiple >= 5 and (best is None or multiple > best['multiple']):
                best = dict(ts_code=code, days_to_expiry=dte, multiple=multiple,
                            start_date=low_date, end_date=date, start_close=low, end_close=price)
            if price < low:
                low_date, low = date, price
        if best:
            group['matches'].append(best)
    for sides in result.values():
        for group in sides.values():
            group['matches'].sort(key=lambda item: (-item['multiple'], item['ts_code']))
    return result


def build_option_moves(root, payload, option_payload):
    """Read only cached exchange daily files; use the dashboard trading dates."""
    asof = payload['asof']
    dates = sorted({bar[0] for bars in payload.get('candles', {}).values() for bar in bars if bar[0] <= asof})[-5:]
    quotes = {}
    errors = []
    for date in dates:
        daily = quotes.setdefault(date, {})
        for path in sorted((Path(root)/'raw/options/daily').glob(f'*_{date}.csv')):
            try:
                with path.open(encoding='utf-8-sig', newline='') as source:
                    for row in csv.DictReader(source):
                        if row.get('trade_date') == date:
                            daily[row.get('ts_code')] = row.get('close')
            except (OSError, UnicodeError, csv.Error):
                errors.append(path.name)
    return dict(asof=asof, dates=dates, groups=summarize_moves(option_payload.get('records', []), dates, quotes),
                coverage=option_payload.get('coverage', []), failures=option_payload.get('failures', []), errors=errors,
                status=option_payload.get('status'))
