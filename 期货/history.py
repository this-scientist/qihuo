"""Only historical main contracts and the current secondary, with roll audit."""
import hashlib
import math
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from collector import DataError, LIMITS, FIELDS, required, unique, atomic_csv, atomic_json, read_csv


def adjust_rolls(raw, overlaps):
    data = raw.sort_values('trade_date').reset_index(drop=True).copy()
    required(data, ['mapping_ts_code','open','high','low','close'])
    factor = 1.0
    factors = []
    for i, row in data.iterrows():
        if i and row.mapping_ts_code != data.mapping_ts_code.iloc[i-1]:
            key = (data.trade_date.iloc[i-1], data.mapping_ts_code.iloc[i-1], row.mapping_ts_code)
            if key not in overlaps:
                raise DataError(f'Missing roll overlap: {key}')
            old, new = overlaps[key]
            if not all(pd.notna(x) and math.isfinite(x) and x > 0 for x in [old,new]):
                raise DataError(f'Invalid roll overlap: {key}')
            factor *= old / new
        factors.append(factor)
    data['raw_close'] = data.close
    data['adj_factor'] = factors
    for field in ['open','high','low','close','settle']:
        if field in data:
            data[field] = pd.to_numeric(data[field], errors='coerce') * data.adj_factor
    data['adjustment'] = 'forward_ratio_same_day_overlap'
    return data


def query_history(collector, api, code, start, end, force=False):
    safe = code.replace('.','_')
    path = collector.root / f'raw/history/{api}/{safe}_{start}_{end}.csv'
    params = dict(ts_code=code, start_date=start, end_date=end)
    if api == 'fut_daily':
        params['fields'] = FIELDS
    cached = None if force else collector.cached(path, api, params)
    if cached is not None:
        return cached
    result = collector.call(api, **params)
    if result.empty:
        raise DataError(f'Empty {api} history for {code}')
    result = unique(result, ['ts_code','trade_date'])
    if len(result) >= LIMITS[api]:
        raise DataError(f'{api} history reached cap for {code}')
    if not result.ts_code.eq(code).all() or not result.trade_date.astype(str).between(start,end).all():
        raise DataError(f'Wrong history contract/date for {code}')
    result = result.sort_values('trade_date').reset_index(drop=True)
    atomic_csv(result,path)
    atomic_json(dict(version=1,api=api,params=params,sha256=hashlib.sha256(path.read_bytes()).hexdigest()),path.with_suffix('.json'))
    return result


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_history_incremental(root, selected, asof, previous_source):
    """Reuse yesterday's prepared history when today's mapped main contract did not change.

    Returns (partial_report, remaining_main_codes). Remaining codes need the full
    prepare_history path because they are missing, stale, corrupted, or rolled.
    """
    root, previous_source = Path(root), Path(previous_source)
    prepared, exclusions, remaining = [], [], []
    previous_report_path = previous_source / 'quality/history_run.json'
    if not previous_report_path.exists():
        return dict(asof=asof, prepared=[], exclusions=[]), sorted(selected[selected.role.eq('main')].main_code.unique())
    try:
        previous_entries = {entry['ts_code']: entry for entry in json.loads(previous_report_path.read_text(encoding='utf-8')).get('prepared', [])}
    except (ValueError, OSError):
        return dict(asof=asof, prepared=[], exclusions=[]), sorted(selected[selected.role.eq('main')].main_code.unique())
    mains = selected[selected.role.eq('main')].sort_values(['exchange', 'main_code'])
    for current in mains.itertuples():
        code, safe = current.main_code, current.main_code.replace('.', '_')
        history_src = previous_source / f'processed/history/{safe}.csv'
        pair_src = previous_source / f'processed/pair_history/{safe}.csv'
        try:
            entry = previous_entries.get(code)
            if not entry:
                raise DataError('previous history entry missing')
            if entry.get('history_sha256') != _hash(history_src) or entry.get('pair_sha256') != _hash(pair_src):
                raise DataError('previous history hash mismatch')
            history = read_csv(history_src).sort_values('trade_date').reset_index(drop=True)
            if history.empty or str(history.trade_date.iloc[-1]) >= asof:
                raise DataError('previous history is not older than update date')
            if history.mapping_ts_code.iloc[-1] != current.ts_code:
                raise DataError('main contract changed; full roll rebuild required')
            last = history.iloc[-1]
            factor = float(last.get('adj_factor', 1.0))
            row = {column: getattr(current, column) for column in selected.columns if hasattr(current, column)}
            row.update(ts_code=code, mapping_ts_code=current.ts_code, exchange=current.exchange,
                raw_close=float(current.close), adj_factor=factor, adjustment='forward_ratio_same_day_overlap')
            for field in ['open', 'high', 'low', 'close', 'settle']:
                if field in row and pd.notna(row[field]):
                    row[field] = float(row[field]) * factor
            history = pd.concat([history, pd.DataFrame([row])], ignore_index=True, sort=False)
            history_path = root / f'processed/history/{safe}.csv'
            atomic_csv(history, history_path)
            rolls_src = history_src.with_suffix('.rolls.csv')
            rolls_dst = history_path.with_suffix('.rolls.csv')
            if rolls_src.exists():
                rolls_dst.parent.mkdir(parents=True, exist_ok=True)
                rolls_dst.write_bytes(rolls_src.read_bytes())
            else:
                atomic_csv(pd.DataFrame(columns=['trade_date','reference_date','old_code','new_code','old_close','new_close']), rolls_dst)
            pair = read_csv(pair_src)
            today_pair = selected[selected.main_code.eq(code)].copy()
            combined = pd.concat([pair, today_pair], ignore_index=True, sort=False)
            combined = combined.drop_duplicates(['trade_date', 'role', 'ts_code'], keep='last')
            combined = combined.sort_values(['trade_date', 'role', 'ts_code']).groupby('role', group_keys=False).tail(65)
            pair_path = root / f'processed/pair_history/{safe}.csv'
            atomic_csv(combined, pair_path)
            prepared.append(dict(ts_code=code, exchange=current.exchange, rows=len(history), rolls=None,
                history_sha256=_hash(history_path), pair_sha256=_hash(pair_path), incremental=True))
        except (DataError, OSError, ValueError, KeyError) as exc:
            remaining.append(code)
            exclusions.append(dict(ts_code=code, exchange=getattr(current, 'exchange', None), reason=f'incremental skipped: {exc}'))
    return dict(asof=asof, prepared=prepared, exclusions=exclusions), sorted(set(remaining))


def prepare_history(collector, selected, asof, days=550, min_history=280, force=False,progress=None):
    start = (datetime.strptime(asof,'%Y%m%d') - timedelta(days=days)).strftime('%Y%m%d')
    exclusions, prepared = [], []
    calendars = {}
    mains = selected[selected.role.eq('main')].sort_values(['exchange','main_code'])
    for i, current in enumerate(mains.itertuples(),1):
        code, exchange = current.main_code, current.exchange
        print(f'History {i}/{len(mains)} {code}', flush=True)
        if progress:progress(f'历史 {i}/{len(mains)} {code}')
        try:
            if exchange not in calendars:
                calendars[exchange] = collector.calendar(exchange,start,asof)
            calendar = calendars[exchange]
            maps = query_history(collector,'fut_mapping',code,start,asof,force)
            required(maps,['mapping_ts_code'])
            maps = maps[maps.trade_date.isin(calendar)].copy()
            if len(maps) < min_history:
                raise DataError(f'Insufficient main history: {len(maps)} < {min_history}')
            expected = [d for d in calendar if d >= maps.trade_date.iloc[0]]
            if maps.trade_date.tolist() != expected:
                raise DataError('Missing main mapping trading days')
            if maps.mapping_ts_code.iloc[-1] != current.ts_code:
                raise DataError('Latest mapping differs from selected main')
            if not maps.mapping_ts_code.astype(str).str.match(r'^[A-Za-z]+\d{3,4}\.[A-Z]+$').all():
                raise DataError('Nonstandard historical main target')
            codes = set(maps.mapping_ts_code)
            secondary = selected[(selected.main_code.eq(code)) & (selected.role.eq('secondary'))]
            codes |= set(secondary.ts_code)
            contracts = {}
            for real_code in sorted(codes):
                contracts[real_code] = query_history(collector,'fut_daily',real_code,start,asof,force).set_index('trade_date',drop=False)
            rows, overlaps, audit = [], {}, []
            previous = None
            for mapped in maps.itertuples():
                table = contracts[mapped.mapping_ts_code]
                if mapped.trade_date not in table.index:
                    raise DataError(f'Missing real main quote: {mapped.trade_date} {mapped.mapping_ts_code}')
                row = table.loc[mapped.trade_date].to_dict()
                row.update(mapping_ts_code=mapped.mapping_ts_code,ts_code=code,exchange=exchange)
                rows.append(row)
                if previous and previous.mapping_ts_code != mapped.mapping_ts_code:
                    day = previous.trade_date
                    old, new = contracts[previous.mapping_ts_code], contracts[mapped.mapping_ts_code]
                    if day not in old.index or day not in new.index:
                        raise DataError(f'Missing same-day roll overlap {day}')
                    old_close, new_close = old.loc[day,'close'],new.loc[day,'close']
                    overlaps[(day,previous.mapping_ts_code,mapped.mapping_ts_code)] = (old_close,new_close)
                    audit.append(dict(trade_date=mapped.trade_date,reference_date=day,old_code=previous.mapping_ts_code,new_code=mapped.mapping_ts_code,
                        old_close=old_close,new_close=new_close))
                previous = mapped
            raw = pd.DataFrame(rows)
            if not math.isclose(float(raw.close.iloc[-1]),float(current.close),rel_tol=1e-8,abs_tol=1e-6):
                raise DataError('Latest real main history differs from snapshot close')
            for field in ['open','high','low','close']:
                values = pd.to_numeric(raw[field], errors='coerce')
                if values.isna().any() or not values.map(lambda x: math.isfinite(x) and x > 0).all():
                    raise DataError(f'Invalid main history price: {field}')
                raw[field] = values
            if (raw.high < raw[['open','low','close']].max(axis=1)).any() or (raw.low > raw[['open','high','close']].min(axis=1)).any():
                raise DataError('Invalid main history OHLC')
            adjusted = adjust_rolls(raw,overlaps)
            target = collector.root / f'processed/history/{code.replace(".","_")}.csv'
            atomic_csv(adjusted,target)
            atomic_csv(pd.DataFrame(audit,columns=['trade_date','reference_date','old_code','new_code','old_close','new_close']),target.with_suffix('.rolls.csv'))
            recent = []
            for role, real_code in [('main',current.ts_code)] + [('secondary',r.ts_code) for r in secondary.itertuples()]:
                table = contracts[real_code].reset_index(drop=True).tail(65).copy()
                table['role'],table['main_code'],table['exchange'] = role,code,exchange
                recent.append(table)
            atomic_csv(pd.concat(recent,ignore_index=True), collector.root / f'processed/pair_history/{code.replace(".","_")}.csv')
            pair_path = collector.root / f'processed/pair_history/{code.replace(".","_")}.csv'
            prepared.append(dict(ts_code=code,exchange=exchange,rows=len(adjusted),rolls=len(audit),
                history_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                pair_sha256=hashlib.sha256(pair_path.read_bytes()).hexdigest()))
        except DataError as exc:
            exclusions.append(dict(ts_code=code,exchange=exchange,reason=str(exc)))
            print(f'Excluded {code}: {exc}',flush=True)
    report = dict(asof=asof,start=start,prepared=prepared,exclusions=exclusions)
    atomic_json(report,collector.root/'quality/history_run.json')
    return report


def prepare_history_fast(collector, selected, asof, previous_source=None, days=550, min_history=280, force=False, progress=None):
    if force or previous_source is None:
        return prepare_history(collector, selected, asof, days, min_history, force, progress)
    incremental, remaining = prepare_history_incremental(collector.root, selected, asof, previous_source)
    if remaining:
        if progress:
            progress(f'增量历史命中 {len(incremental["prepared"])} 个；重建 {len(remaining)} 个')
        subset = selected[selected.main_code.isin(remaining)].copy()
        rebuilt = prepare_history(collector, subset, asof, days, min_history, force, progress)
        prepared = incremental['prepared'] + rebuilt['prepared']
        exclusions = rebuilt['exclusions']
    else:
        prepared, exclusions = incremental['prepared'], incremental['exclusions']
    report = dict(asof=asof, start=(datetime.strptime(asof,'%Y%m%d') - timedelta(days=days)).strftime('%Y%m%d'),
        prepared=prepared, exclusions=exclusions, incremental_prepared=len(incremental['prepared']),
        full_rebuild_count=len(remaining))
    atomic_json(report, collector.root/'quality/history_run.json')
    return report
