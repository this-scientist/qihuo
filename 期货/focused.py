"""Main continuous trend and two liquid month contracts per commodity."""
import hashlib
import json
import re
from datetime import datetime

import pandas as pd

from collector import (DataError, SUFFIX, FIELDS, LIMITS, required, unique,
                       real_contracts, validate_daily, atomic_csv, atomic_json, read_csv)


def select_contracts(snapshot, mapping, exchange, date):
    required(snapshot, ['ts_code', 'trade_date', 'vol', 'oi'])
    required(mapping, ['ts_code', 'trade_date', 'mapping_ts_code'])
    snapshot = unique(snapshot, ['ts_code', 'trade_date'])
    if not snapshot.trade_date.astype(str).eq(date).all():
        raise DataError('Wrong snapshot date')
    suffix = SUFFIX[exchange]
    if not snapshot.ts_code.str.endswith('.' + suffix).all():
        raise DataError('Wrong snapshot exchange')
    months = real_contracts(snapshot)
    months['vol'] = pd.to_numeric(months.vol, errors='coerce')
    if months.vol.isna().any() or (months.vol < 0).any():
        raise DataError('Invalid snapshot vol')
    inactive_contracts = set(months.loc[months.vol.eq(0), 'ts_code'])
    months = months[months.vol > 0].copy()
    for field in ['vol', 'oi']:
        months[field] = pd.to_numeric(months[field], errors='coerce')
        if months[field].isna().any() or (~months[field].map(lambda x: 0 <= x < float('inf'))).any():
            raise DataError(f'Invalid snapshot {field}')
    months['fut_code'] = months.ts_code.str.extract(r'^([A-Za-z]+)\d', expand=False)
    maps = mapping[mapping.ts_code.str.match(r'^[A-Za-z]+\.' + suffix + '$')].copy()
    target_products = maps.mapping_ts_code.astype(str).str.extract(r'^([A-Za-z]+)\d{3,4}\.' + suffix + '$', expand=False)
    codes = maps.ts_code.str.split('.').str[0]
    is_secondary_continuous = codes.str.endswith('L') & codes.str[:-1].eq(target_products)
    maps = maps[~is_secondary_continuous].copy()
    maps = unique(maps, ['ts_code', 'trade_date'])
    if not maps.trade_date.astype(str).eq(date).all():
        raise DataError('Wrong mapping date')
    mapped_codes = set(maps.ts_code.str.split('.').str[0])
    active_codes = set(months.loc[months.vol > 0, 'fut_code'])
    if active_codes - mapped_codes:
        raise DataError(f'Active commodities without main mapping: {sorted(active_codes-mapped_codes)}')
    selected, skipped = [], []
    for row in maps.itertuples():
        code = row.ts_code.split('.')[0]
        if not re.fullmatch(re.escape(code) + r'\d{3,4}\.' + suffix, str(row.mapping_ts_code)):
            raise DataError(f'Main mapping targets wrong commodity: {row.ts_code}')
        candidates = months[(months.fut_code == code) & (months.vol > 0)]
        if candidates.empty:
            skipped.append(dict(exchange=exchange, trade_date=date, fut_code=code, reason='no_volume'))
            continue
        main = candidates[candidates.ts_code.eq(row.mapping_ts_code)]
        if main.empty:
            if row.mapping_ts_code in inactive_contracts:
                skipped.append(dict(exchange=exchange, trade_date=date, fut_code=code, reason='mapped_main_no_volume'))
                continue
            raise DataError(f'Active commodity missing liquid mapped main: {row.ts_code} -> {row.mapping_ts_code}')
        main = main.copy()
        main['role'], main['main_code'] = 'main', row.ts_code
        selected.append(main)
        secondary = candidates[~candidates.ts_code.eq(row.mapping_ts_code)].sort_values(
            ['oi', 'vol', 'ts_code'], ascending=[False, False, True]).head(1).copy()
        if not secondary.empty:
            secondary['role'], secondary['main_code'] = 'secondary', row.ts_code
            selected.append(secondary)
        else:
            skipped.append(dict(exchange=exchange, trade_date=date, fut_code=code, reason='no_liquid_secondary'))
    columns = list(months.columns) + ['role', 'main_code']
    return (pd.concat(selected, ignore_index=True) if selected else pd.DataFrame(columns=columns)), skipped


def run_focused(collector, start, end, force=False):
    datetime.strptime(start, '%Y%m%d')
    datetime.strptime(end, '%Y%m%d')
    if start > end:
        raise ValueError('start_date must be <= end_date')
    collector.failures = []
    calendars, outputs, skipped = {}, {}, []
    for exchange in collector.exchanges:
        try:
            calendars[exchange] = collector.calendar(exchange, start, end)
        except DataError as exc:
            collector.record_failure('calendar', exchange, '', exc)
            continue
        for date in calendars[exchange]:
            try:
                path = collector.root / f'raw/selected/{exchange}/{date}.csv'
                params = dict(trade_date=date, exchange=exchange, scope='main_secondary_curve_v2')
                cached = None if force else collector.cached(path, 'focused', params)
                main_path = collector.root / f'raw/main_continuous/{exchange}/{date}.csv'
                cached_main = None if force else collector.cached(main_path, 'focused_main', params)
                if cached is not None and cached_main is not None:
                    curve_path = collector.root / f'raw/curve/{exchange}/{date}.csv'
                    cached_curve = None if force else collector.cached(curve_path, 'curve', params)
                    outputs.setdefault(date, {})[exchange] = (cached, cached_main, cached_curve)
                    receipt = main_path.with_suffix('.json')
                    skipped.extend(json.loads(receipt.read_text(encoding='utf-8')).get('skipped', []))
                    continue
                # One daily market snapshot feeds both the main/secondary ranking
                # and the persisted all-month real curve (unadjusted).
                snapshot = collector.call('fut_daily', trade_date=date, exchange=exchange, fields=FIELDS)
                mapping = collector.call('fut_mapping', trade_date=date)
                if snapshot.empty or mapping.empty:
                    raise DataError('Empty snapshot or main mapping')
                if len(snapshot) >= LIMITS['fut_daily'] or len(mapping) >= LIMITS['fut_mapping']:
                    raise DataError('Snapshot/mapping row cap: cannot establish reliable ranking')
                selected, excluded = select_contracts(snapshot, mapping, exchange, date)
                skipped.extend(excluded)
                # 期限结构数据线：保存全部有成交的真实月合约快照（未复权），与复权主连分离。
                curve = real_contracts(snapshot).copy()
                for field in ['vol', 'oi']:
                    curve[field] = pd.to_numeric(curve[field], errors='coerce')
                curve = curve[curve.vol.gt(0) & curve.oi.ge(0)].copy()
                curve_path = collector.root / f'raw/curve/{exchange}/{date}.csv'
                atomic_csv(curve, curve_path)
                atomic_json(dict(version=1, api='curve', params=params, rows=len(curve),
                    sha256=hashlib.sha256(curve_path.read_bytes()).hexdigest(),
                    validated_at=datetime.now().isoformat()), curve_path.with_suffix('.json'))
                if not selected.empty:
                    selected = validate_daily(selected, date, exchange)
                    if not selected.price_valid.all():
                        raise DataError('Selected main/secondary has invalid OHLC')
                selected['exchange'] = exchange
                main = selected[selected.role.eq('main')].copy()
                main['mapping_ts_code'] = main.ts_code
                main['ts_code'] = main.main_code
                main['adjustment'] = 'none'
                main['series_source'] = 'mapped_real_main'
                main['roll_changed'] = pd.NA
                previous_files = sorted(main_path.parent.glob('????????.csv')) if main_path.parent.exists() else []
                previous_files = [p for p in previous_files if p.stem < date]
                if previous_files:
                    previous = read_csv(previous_files[-1])
                    if 'mapping_ts_code' in previous:
                        previous_codes = previous.set_index('ts_code').mapping_ts_code.to_dict()
                        main['roll_changed'] = main.apply(lambda row: row.mapping_ts_code != previous_codes[row.ts_code]
                            if row.ts_code in previous_codes else pd.NA, axis=1)
                for frame, destination, api in [(selected,path,'focused'), (main,main_path,'focused_main'), (curve,curve_path,'curve')]:
                    atomic_csv(frame, destination)
                    atomic_json(dict(version=1, api=api, params=params, rows=len(frame), skipped=excluded,
                        sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                        validated_at=datetime.now().isoformat()), destination.with_suffix('.json'))
                outputs.setdefault(date, {})[exchange] = (selected, main, curve)
            except DataError as exc:
                collector.record_failure('focused', exchange, date, exc)
    published = []
    if len(calendars) == len(collector.exchanges):
        for date, parts in sorted(outputs.items()):
            expected = {ex for ex, dates in calendars.items() if date in dates}
            if set(parts) != expected:
                continue
            for index, folder in [(0,'selected'), (1,'main_continuous'), (2,'curve')]:
                frames = [pair[index] for pair in parts.values() if pair[index] is not None]
                if len(frames) != len(parts):
                    continue  # 旧缓存日期没有曲线文件：该日不发布curve，避免部分合并
                atomic_csv(pd.concat(frames, ignore_index=True), collector.root / f'raw/{folder}/{date}.csv')
            published.append(date)
    report = dict(mode='focused', start_date=start, end_date=end, exchanges=collector.exchanges,
        success=not collector.failures, failures=collector.failures, skipped=skipped,
        published_days=published, secondary_rule='largest OI among liquid non-main month contracts; ties volume then code',
        adjustment='none: main switch may cause price gap',
        oi_scope='individual main and secondary; not commodity total OI', finished_at=datetime.now().isoformat())
    atomic_json(report, collector.root / 'quality/latest_run.json')
    return report
