"""Documented Tushare queries, fail-closed validation and auditable partitions."""
import hashlib
import json
import logging
import math
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

LOG = logging.getLogger(__name__)
SUFFIX = {'DCE': 'DCE', 'CZCE': 'ZCE', 'SHFE': 'SHF', 'INE': 'INE', 'GFEX': 'GFE'}
LIMITS = {'fut_basic': 10000, 'fut_daily': 2000, 'fut_daily_adj': 3000,
          'fut_mapping': 2000, 'fut_holding': 2000, 'fut_wsr': 1000,
          'fut_settle': 1600, 'opt_daily': 15000}
FIELDS = 'ts_code,trade_date,pre_close,pre_settle,open,high,low,close,settle,vol,amount,oi,oi_chg'


class DataError(RuntimeError):
    pass


def required(df, columns):
    missing = set(columns) - set(df.columns)
    if missing:
        raise DataError(f'Missing fields: {sorted(missing)}')


def unique(df, keys):
    required(df, keys)
    df = df.drop_duplicates().copy()
    if df.duplicated(keys).any():
        raise DataError(f'Conflicting duplicates: {keys}')
    return df


def validate_daily(df, date, exchange):
    if df.empty:
        raise DataError(f'Empty daily data: {date} {exchange}')
    df = unique(df, ['ts_code', 'trade_date'])
    required(df, ['open', 'high', 'low', 'close', 'settle', 'vol', 'amount', 'oi'])
    if not df.trade_date.astype(str).eq(date).all():
        raise DataError('Wrong trade_date in response')
    if not df.ts_code.astype(str).str.endswith('.' + SUFFIX[exchange]).all():
        raise DataError('Wrong exchange in response')
    if 'exchange' in df and not df.exchange.eq(exchange).all():
        raise DataError('Conflicting exchange field')
    for col in ['open', 'high', 'low', 'close', 'settle', 'vol', 'amount', 'oi']:
        raw = df[col]
        df[col] = pd.to_numeric(df[col], errors='coerce')
        allow_missing = col in ['open', 'high', 'low', 'close', 'settle']
        valid = df[col].map(lambda x: (allow_missing and pd.isna(x)) or (pd.notna(x) and math.isfinite(x) and x >= 0))
        if not valid.all() or (raw.notna() & df[col].isna()).any():
            raise DataError(f'Invalid numeric data: {col}')
    # Zero prices occur on some dormant contracts; keep them for OI, but never
    # use them to construct a tradable price curve or calculate indicators.
    priced = df[['open', 'high', 'low', 'close']].gt(0).all(axis=1)
    if ((df.vol > 0) & (df.close.le(0) | df.close.isna())).any():
        raise DataError('Zero close with positive trading volume')
    rows = df.loc[priced]
    if (rows.high < rows[['open', 'low', 'close']].max(axis=1)).any() or (rows.low > rows[['open', 'high', 'close']].min(axis=1)).any():
        raise DataError('Invalid OHLC relationship')
    df['exchange'] = exchange
    df['price_valid'] = priced
    return df.sort_values(['trade_date', 'ts_code']).reset_index(drop=True)


def atomic_csv(df, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.csv.tmp')
    df.to_csv(temp, index=False, encoding='utf-8-sig')
    temp.replace(path)


def atomic_json(value, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def read_csv(path):
    return pd.read_csv(path, dtype={'ts_code': str, 'trade_date': str,
        'cal_date': str, 'list_date': str, 'delist_date': str, 'd_month': str,
        'maturity_date': str, 'mapping_ts_code': str})


def real_contracts(df):
    return df[df.ts_code.astype(str).str.match(r'^[A-Za-z]+\d{3,4}\.[A-Z]+$')].copy()


def active_contracts(basic, date):
    required(basic, ['list_date', 'delist_date'])
    # Unknown life dates must not silently remove contracts from coverage checks.
    listed = basic.list_date.fillna('').astype(str)
    ended = basic.delist_date.fillna('').astype(str)
    return basic[(listed.eq('') | listed.le(date)) & (ended.eq('') | ended.ge(date))]


def commodity_totals(daily, basic):
    daily = unique(real_contracts(daily), ['ts_code', 'trade_date'])
    for field in ['oi', 'vol', 'amount']:
        daily[field] = pd.to_numeric(daily[field], errors='coerce')
        if not daily[field].map(lambda x: pd.notna(x) and math.isfinite(x) and x >= 0).all():
            raise DataError(f'Invalid total input: {field}')
    basic = unique(basic, ['ts_code'])
    joined = daily.merge(basic[['ts_code', 'fut_code', 'exchange']], on='ts_code', how='left', validate='many_to_one', suffixes=('', '_basic'))
    if joined.fut_code.isna().any():
        raise DataError('Ordinary contract missing from fut_basic')
    exchange = 'exchange_basic' if 'exchange_basic' in joined else 'exchange'
    result = joined.groupby(['trade_date', exchange, 'fut_code'], as_index=False).agg(
        total_oi=('oi', 'sum'), total_vol=('vol', 'sum'), total_amount=('amount', 'sum'), contract_count=('ts_code', 'nunique'))
    return result.rename(columns={exchange: 'exchange'})


class Collector:
    def __init__(self, api, root, exchanges=None, interval=0.8, retries=3):
        self.api, self.root = api, Path(root)
        self.exchanges = exchanges or list(SUFFIX)
        self.interval, self.retries, self.last_call = interval, retries, 0
        self.failures = []

    def call(self, name, **params):
        for attempt in range(self.retries):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            try:
                df = self.api.query(name, **params)
                if not isinstance(df, pd.DataFrame):
                    raise DataError('API did not return a DataFrame')
                return df
            except Exception as exc:
                # Do not log exceptions from a gateway: they can contain tokens.
                LOG.warning('%s attempt %s failed (%s)', name, attempt + 1, type(exc).__name__)
                if attempt + 1 == self.retries:
                    detail = str(exc) if isinstance(exc, DataError) else type(exc).__name__
                    raise DataError(f'{name} failed after {self.retries} attempts ({detail})') from None
                time.sleep(min(2 ** attempt, 8))

    def calendar(self, exchange, start, end):
        first, last = datetime.strptime(start, '%Y%m%d'), datetime.strptime(end, '%Y%m%d')
        if first > last:
            raise ValueError('start_date must be <= end_date')
        dates = []
        while first <= last:
            stop = min(first + timedelta(days=90), last)
            df = self.call('fut_trade_cal', exchange=exchange, start_date=first.strftime('%Y%m%d'), end_date=stop.strftime('%Y%m%d'))
            required(df, ['cal_date', 'is_open', 'exchange'])
            if df.empty or not df.exchange.eq(exchange).all():
                raise DataError(f'Calendar unavailable for {exchange}; no SSE fallback')
            actual = set(df.cal_date.astype(str))
            expected = set((first + timedelta(days=i)).strftime('%Y%m%d') for i in range((stop-first).days+1))
            if actual != expected:
                raise DataError(f'Calendar has missing/out-of-range dates: {exchange}')
            dates += df.loc[pd.to_numeric(df.is_open).eq(1), 'cal_date'].astype(str).tolist()
            first = stop + timedelta(days=1)
        return sorted(set(dates))

    def basic(self, exchange):
        ordinary = self.call('fut_basic', exchange=exchange, fut_type='1')
        synthetic = self.call('fut_basic', exchange=exchange, fut_type='2')
        for df in [ordinary, synthetic]:
            required(df, ['ts_code', 'fut_code', 'exchange', 'list_date', 'delist_date'])
            if df.empty or len(df) >= LIMITS['fut_basic'] or not df.exchange.eq(exchange).all():
                raise DataError(f'Incomplete fut_basic for {exchange}; empty/wrong exchange/row limit')
        ordinary = unique(ordinary, ['ts_code'])
        atomic_csv(ordinary, self.root / f'raw/basic/fut_basic_source_{exchange}.csv')
        excluded = ordinary[~ordinary.ts_code.isin(real_contracts(ordinary).ts_code)].copy()
        if not excluded.empty:
            special = excluded.ts_code.str.match(r'^[A-Za-z]+\d{3,4}F\.' + SUFFIX[exchange] + '$') & excluded.fut_code.str.endswith('_F')
            if not special.all():
                raise DataError('Unknown nonstandard contract in ordinary fut_basic')
            excluded['exclusion_reason'] = 'nonstandard F contract; outside standard-month trend universe'
            atomic_csv(excluded, self.root / f'raw/basic/fut_excluded_{exchange}.csv')
        ordinary = real_contracts(ordinary)
        if ordinary.fut_code.isna().any():
            raise DataError('Missing fut_code')
        synthetic = unique(synthetic, ['ts_code'])
        atomic_csv(ordinary, self.root / f'raw/basic/fut_basic_{exchange}.csv')
        atomic_csv(synthetic, self.root / f'raw/basic/fut_synthetic_{exchange}.csv')
        return ordinary, synthetic

    def cached(self, path, name, params):
        receipt = path.with_suffix('.json')
        if not path.exists() or not receipt.exists():
            return None
        try:
            info = json.loads(receipt.read_text(encoding='utf-8'))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if info.get('version') == 1 and info.get('sha256') == digest and info.get('api') == name and info.get('params') == params:
                return read_csv(path)
        except (ValueError, OSError):
            pass
        return None

    def partition(self, name, folder, exchange, date, expected=None, force=False):
        path = self.root / f'raw/{folder}/{exchange}/{date}.csv'
        params = {'trade_date': date}
        if name != 'fut_mapping':
            params['exchange'] = 'SHFE' if name == 'fut_holding' and exchange == 'INE' else exchange
        if name in ['fut_daily', 'fut_daily_adj']:
            params['fields'] = FIELDS
        cache = None if force else self.cached(path, name, params)
        if cache is not None:
            try:
                self.validate(name, cache, date, exchange, expected)
                return cache
            except DataError:
                pass
        df = self.call(name, **params)
        atomic_csv(df, self.root / f'raw/source/{name}/{exchange}/{date}.csv')
        if name == 'fut_mapping' and not df.empty:
            df = df[df.ts_code.astype(str).str.endswith('.' + SUFFIX[exchange])].copy()
        cap = len(df) >= LIMITS.get(name, 10000)
        if name in ['fut_holding', 'fut_wsr'] and cap:
            # These APIs accept bare product/contract symbols, not ts_code.
            basics = read_csv(self.root / f'raw/basic/fut_basic_{exchange}.csv')
            symbols = set(basics.fut_code)
            if name == 'fut_holding':
                symbols |= set(active_contracts(basics, date).ts_code.str.split('.').str[0])
            chunks = []
            for symbol in sorted(symbols):
                part = self.call(name, **dict(params, symbol=symbol))
                if len(part) >= LIMITS[name]:
                    raise DataError(f'{name} row limit for {symbol}')
                chunks.append(part)
            df = pd.concat(chunks, ignore_index=True).drop_duplicates()
            cap = False
        if expected is not None:
            key = 'ts_code'
            existing = set(df[key].astype(str)) if key in df else set()
            missing = set(expected) if cap else set(expected) - existing
            chunks = [] if cap else [df]
            for code in sorted(missing):
                part = self.call(name, **dict(params, ts_code=code))
                if len(part) >= LIMITS.get(name, 10000):
                    raise DataError(f'Row limit even for {code}')
                if not part.empty and (not part.ts_code.eq(code).all()):
                    raise DataError(f'Wrong contract returned for {code}')
                chunks.append(part)
            df = pd.concat(chunks, ignore_index=True) if chunks else df
        elif cap:
            raise DataError(f'{name} reached row limit; partition further by symbol/contract')
        if name == 'fut_daily':
            df = real_contracts(df)
            basic_path = self.root / f'raw/basic/fut_basic_{exchange}.csv'
            if basic_path.exists():
                ordinary = read_csv(basic_path)
                unknown = set(df.ts_code) - set(ordinary.ts_code)
                if unknown:
                    raise DataError(f'Unknown ordinary contracts: {sorted(unknown)[:8]}; fut_basic refresh required')
        if name == 'fut_mapping' and expected is not None:
            df = df[df.ts_code.isin(expected)].copy()
        df = self.validate(name, df, date, exchange, expected)
        atomic_csv(df, path)
        atomic_json({'version': 1, 'api': name, 'params': params, 'rows': len(df),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'validated_at': datetime.now().isoformat()}, path.with_suffix('.json'))
        return df

    def validate(self, name, df, date, exchange, expected):
        if name in ['fut_daily', 'fut_daily_adj', 'opt_daily']:
            df = validate_daily(df, date, exchange)
            if name == 'fut_daily':
                basic_path = self.root / f'raw/basic/fut_basic_{exchange}.csv'
                if basic_path.exists():
                    known = set(read_csv(basic_path).ts_code)
                    unknown = set(df.ts_code) - known
                    if unknown:
                        raise DataError(f'Unknown ordinary contracts: {sorted(unknown)[:8]}; fut_basic refresh required')
        else:
            if df.empty:
                raise DataError(f'Empty response: {name} {exchange} {date}')
            required(df, ['trade_date'])
            if not df.trade_date.astype(str).eq(date).all():
                raise DataError('Wrong trade_date')
            if name in ['fut_holding', 'fut_wsr']:
                required(df, ['symbol'])
                basic_path = self.root / f'raw/basic/fut_basic_{exchange}.csv'
                if basic_path.exists():
                    basic = read_csv(basic_path)
                    symbols = set(basic.fut_code) | set(basic.ts_code.str.split('.').str[0])
                    # SHFE holdings contain INE too; distribute by the target
                    # exchange's ordinary contract/product universe.
                    df = df[df.symbol.isin(symbols)].drop_duplicates().copy()
                    if df.empty:
                        raise DataError(f'No {name} rows for target exchange')
                df['exchange'] = exchange
            if name == 'fut_mapping':
                df = unique(df, ['ts_code', 'trade_date'])
                required(df, ['mapping_ts_code'])
                if not df.mapping_ts_code.astype(str).str.match(r'^[A-Za-z]+\d{3,4}\.' + SUFFIX[exchange] + '$').all():
                    raise DataError('Mapping target is not a real contract')
        if expected is not None:
            missing = set(expected) - set(df.ts_code.astype(str))
            if missing:
                raise DataError(f'{name} missing {len(missing)} contracts: {sorted(missing)[:8]}')
        return df

    def options_basic(self, exchange, ordinary):
        chunks = []
        for code in ordinary.ts_code:
            df = self.call('opt_basic', exchange=exchange, opt_code='OP' + code)
            if df.empty:
                continue
            required(df, ['ts_code', 'exchange', 'opt_code', 'exercise_price', 'call_put', 'list_date', 'delist_date', 'maturity_date'])
            if not df.exchange.eq(exchange).all() or not df.opt_code.eq('OP' + code).all():
                raise DataError('Wrong option underlying/exchange')
            # No published opt_basic cap; a large single-underlying result is
            # treated as suspicious rather than silently assuming completeness.
            if len(df) >= 10000:
                raise DataError('opt_basic suspicious row count')
            chunks.append(df)
        if not chunks:
            raise DataError(f'No option metadata returned for {exchange}')
        df = unique(pd.concat(chunks, ignore_index=True), ['ts_code'])
        atomic_csv(df, self.root / f'raw/option/opt_basic_{exchange}.csv')
        return df

    def record_failure(self, name, exchange, date, exc):
        self.failures.append(dict(api=name, exchange=exchange, trade_date=date, error=str(exc)))
        LOG.error('%s %s %s: %s', name, exchange, date, exc)

    def run(self, start, end, datasets=('daily', 'continuous', 'mapping'), force=False):
        datetime.strptime(start, '%Y%m%d')
        datetime.strptime(end, '%Y%m%d')
        self.failures = []
        basics, calendars = {}, {}
        names = {'daily': 'fut_daily', 'continuous': 'fut_daily_adj', 'mapping': 'fut_mapping',
            'holding': 'fut_holding', 'warehouse': 'fut_wsr', 'settle': 'fut_settle', 'option': 'opt_daily'}
        outputs = {folder: {} for folder in datasets}
        for exchange in self.exchanges:
            try:
                ordinary, synthetic = self.basic(exchange)
                basics[exchange] = ordinary
                calendars[exchange] = self.calendar(exchange, start, end)
            except DataError as exc:
                self.record_failure('basic/calendar', exchange, '', exc)
                continue
            option_basic = None
            if 'option' in datasets:
                try:
                    # Fetch all historical underlyings intersecting the requested
                    # interval, not only today's active contracts.
                    relevant = ordinary[(ordinary.list_date.fillna('').le(end)) & (ordinary.delist_date.fillna('99999999').ge(start))]
                    option_basic = self.options_basic(exchange, relevant)
                except DataError as exc:
                    self.record_failure('opt_basic', exchange, '', exc)
            for date in calendars[exchange]:
                active = active_contracts(ordinary, date)
                if active.empty:
                    continue
                for folder in datasets:
                    name = names[folder]
                    try:
                        expected = None
                        if folder in ['daily', 'settle']:
                            expected = active.ts_code.tolist()
                        if folder in ['continuous', 'mapping']:
                            # One standard main code per commodity; secondary
                            # continuous codes never enter the RPS universe.
                            expected = [f'{code}.{SUFFIX[exchange]}' for code in active.fut_code.unique()]
                        if folder == 'option':
                            if option_basic is None:
                                raise DataError('Option metadata unavailable')
                            expected = active_contracts(option_basic, date).ts_code.tolist()
                            if not expected:
                                continue
                        df = self.partition(name, 'option/daily' if folder == 'option' else folder, exchange, date, expected, force)
                        if folder == 'daily':
                            df = real_contracts(df)
                            unknown = set(df.ts_code) - set(ordinary.ts_code)
                            if unknown:
                                raise DataError(f'Unknown ordinary contracts: {sorted(unknown)[:8]}')
                        if folder in ['continuous', 'mapping', 'option']:
                            df = df[df.ts_code.isin(expected)].copy()
                        if folder == 'continuous' and not df.price_valid.all():
                            raise DataError('Main continuous series has invalid OHLC; not eligible for trend indicators')
                        outputs[folder].setdefault(date, {})[exchange] = df
                    except DataError as exc:
                        self.record_failure(name, exchange, date, exc)
        # Publish merged days only when every exchange calendar is known and
        # every active exchange partition passed; never mix old/new partial days.
        if len(calendars) == len(self.exchanges):
            all_dates = sorted(set().union(*map(set, calendars.values())))
            for folder, by_date in outputs.items():
                for date in all_dates:
                    expected_exchanges = {ex for ex in self.exchanges if date in calendars[ex] and not active_contracts(basics[ex], date).empty}
                    parts = by_date.get(date, {})
                    if set(parts) != expected_exchanges or not parts:
                        continue
                    merged = pd.concat(parts.values(), ignore_index=True)
                    destination = 'option/daily' if folder == 'option' else folder
                    atomic_csv(merged, self.root / f'raw/{destination}/{date}.csv')
                    if folder == 'daily':
                        try:
                            atomic_csv(commodity_totals(merged, pd.concat(basics.values(), ignore_index=True)), self.root / f'processed/commodity/{date}.csv')
                            self.term_structure(date, merged, pd.concat(basics.values(), ignore_index=True))
                        except DataError as exc:
                            self.record_failure('processed', 'ALL', date, exc)
        if len(basics) == len(self.exchanges):
            atomic_csv(pd.concat(basics.values(), ignore_index=True), self.root / 'raw/basic/fut_basic_all.csv')
        report = {'start_date': start, 'end_date': end, 'exchanges': self.exchanges,
            'datasets': list(datasets), 'success': not self.failures, 'failures': self.failures,
            'spot_basis': 'missing: separate comparable spot source required',
            'finished_at': datetime.now().isoformat()}
        report['published_days'] = {folder: [date for date, parts in by_date.items()
            if len(calendars) == len(self.exchanges) and set(parts) == {ex for ex in self.exchanges
                if date in calendars[ex] and not active_contracts(basics[ex], date).empty}]
            for folder, by_date in outputs.items()}
        atomic_json(report, self.root / 'quality/latest_run.json')
        return report

    def term_structure(self, date, daily, basic):
        curve = daily.merge(basic[['ts_code', 'fut_code', 'd_month', 'delist_date']], on='ts_code', validate='many_to_one')
        curve = curve[(curve.vol > 0) & (curve.oi > 0) & (curve.settle > 0)]
        if not curve.d_month.astype(str).str.match(r'^\d{6}$').all():
            raise DataError('Invalid delivery month in curve metadata')
        curve = curve.sort_values(['exchange', 'fut_code', 'd_month', 'ts_code'])
        atomic_csv(curve, self.root / f'processed/curves/{date}.csv')
        spreads = []
        for (exchange, code), group in curve.groupby(['exchange', 'fut_code']):
            if len(group) < 2:
                continue
            near, far = group.iloc[0], group.iloc[1]
            spreads.append(dict(trade_date=date, exchange=exchange, fut_code=code,
                near_code=near.ts_code, far_code=far.ts_code, near_month=near.d_month,
                far_month=far.d_month, near_settle=near.settle, far_settle=far.settle,
                spread=near.settle-far.settle, basis=None))
        atomic_csv(pd.DataFrame(spreads, columns=['trade_date','exchange','fut_code','near_code','far_code','near_month','far_month','near_settle','far_settle','spread','basis']), self.root / f'processed/spreads/{date}.csv')
