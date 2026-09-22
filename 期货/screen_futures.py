# -*- coding: utf-8 -*-
"""Explainable long/short trend radar; no order execution."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pandas as pd

from collector import DataError, atomic_csv, atomic_json, read_csv, required
from config import DATA_DIR, COMMODITY_EXCHANGES
from fetch_futures_data import make_collector
from focused import run_focused
from history import prepare_history
from strategy import Settings, indicators, rps_panel, pair_context, evaluate, rank_candidates


def load_inputs(root, asof, settings):
    root=Path(root)
    report_path=root/'quality/latest_run.json'
    history_path=root/'quality/history_run.json'
    if not report_path.exists() or not history_path.exists():
        raise DataError('Missing prepared data; run with --refresh-history first')
    snapshot_report=json.loads(report_path.read_text(encoding='utf-8'))
    history_report=json.loads(history_path.read_text(encoding='utf-8'))
    if snapshot_report.get('mode')!='focused' or asof not in snapshot_report.get('published_days',[]):
        raise DataError('Snapshot incomplete or requested date not published')
    if set(snapshot_report['exchanges'])!=set(COMMODITY_EXCHANGES):
        raise DataError('Official market-wide radar requires all five commodity exchanges')
    if history_report.get('asof')!=asof:
        raise DataError('History report asof mismatch; prepare the requested date')
    selected=read_csv(root/f'raw/selected/{asof}.csv')
    required(selected,['main_code','role','exchange','ts_code'])
    series={}
    exclusions=list(history_report['exclusions'])
    prepared={entry['ts_code']:entry for entry in history_report['prepared']}
    current=selected[selected.role.eq('main')].set_index('main_code')
    for code,entry in prepared.items():
        try:
            if code not in current.index:
                raise DataError('Not in current liquid commodity universe')
            file=root/f'processed/history/{code.replace(".","_")}.csv'
            digest=hashlib.sha256(file.read_bytes()).hexdigest()
            if entry.get('history_sha256')!=digest:
                raise DataError('Missing/mismatched history hash; rerun history preparation')
            raw=read_csv(file)
            raw=raw[raw.trade_date.astype(str).le(asof)].copy()
            if len(raw)<settings.min_history or raw.trade_date.iloc[-1]!=asof:
                raise DataError('Insufficient history or stale latest bar')
            if not raw.adjustment.eq('forward_ratio_same_day_overlap').all():
                raise DataError('Unadjusted main series cannot be used for trend screening')
            if not raw.ts_code.eq(code).all() or raw.mapping_ts_code.iloc[-1]!=current.loc[code,'ts_code']:
                raise DataError('History commodity/main mapping mismatch')
            series[code]=indicators(raw)
        except (DataError,OSError) as exc:
            exclusions.append(dict(ts_code=code,exchange=entry['exchange'],reason=str(exc)))
    return selected,series,exclusions,prepared


def partial_coverage(root, asof):
    """部分交易所当日未采集时，跨品种分位按缩减篮子计算，必须显式标注。"""
    path=Path(root)/'quality/latest_run.json'
    if not path.exists():
        return None
    entry=next((item for item in json.loads(path.read_text(encoding='utf-8')).get('partial_days',[])
        if item.get('trade_date')==asof),None)
    if not entry:
        return None
    return dict(trade_date=asof,missing_exchanges=entry['missing_exchanges'],
        note='部分交易所当日未采集；RPS等跨品种分位按缩减篮子计算，与全篮子历史日期不可比')


def screen(root, asof, settings=None):
    root=Path(root); settings=settings or Settings()
    selected,series,exclusions,prepared=load_inputs(root,asof,settings)
    universe=len(series)
    latest=[]; scores=[]
    if series:
        panel=rps_panel(pd.concat(series.values(),ignore_index=True))
        rank_cols=[c for c in panel.columns if c.startswith('rps')]
        for code,data in series.items():
            ranks=panel.loc[panel.ts_code.eq(code),['trade_date']+rank_cols]
            data=data.merge(ranks,on='trade_date',how='left',validate='one_to_one')
            context={}
            try:
                pair_path=root/f'processed/pair_history/{code.replace(".","_")}.csv'
                if prepared[code].get('pair_sha256')!=hashlib.sha256(pair_path.read_bytes()).hexdigest():
                    raise DataError('Pair history hash mismatch')
                pair=read_csv(pair_path)
                expected=selected[selected.main_code.eq(code)].set_index('role').ts_code.to_dict()
                actual=pair.groupby('role').ts_code.first().to_dict()
                if expected!=actual:
                    raise DataError('Pair history contract identities differ from snapshot')
                context=pair_context(pair,asof,data.trade_date)
            except (DataError,OSError) as exc:
                exclusions.append(dict(ts_code=code,exchange=data.exchange.iloc[-1],reason=f'Funding/curve unavailable: {exc}'))
            fields=data.iloc[-1].to_dict()
            fields.update(context)
            latest.append(fields)
            for direction in [1,-1]:
                result=evaluate(data,direction,context,settings)
                result.update(fields)
                # Directional score fields must not be overwritten by context.
                scores.append(result)
    score_table=pd.DataFrame(scores)
    out=root/f'processed/radar/{asof}'
    out.mkdir(parents=True,exist_ok=True)
    valid=universe>=settings.min_universe
    lists={}
    for side in ['long','short']:
        for category in ['trend','startup']:
            sub=score_table[score_table.direction.eq(side)].copy() if not score_table.empty else score_table.copy()
            candidates=rank_candidates(sub,category,settings) if valid else sub.iloc[:0].copy()
            lists[f'{side}_{category}']=candidates
            atomic_csv(candidates,out/f'{side}_{category}.csv')
    atomic_csv(pd.DataFrame(latest),out/'indicators.csv')
    atomic_csv(score_table,out/'scores.csv')
    atomic_csv(pd.DataFrame(exclusions,columns=['ts_code','exchange','reason']),out/'exclusions.csv')
    report=dict(asof=asof,success=valid,eligible_universe=universe,current_liquid_commodities=int(selected.role.eq('main').sum()),
        excluded_histories=len(selected[selected.role.eq('main')])-universe,settings=asdict(settings),
        counts={key:len(value) for key,value in lists.items()},
        coverage_warning=partial_coverage(root,asof),
        reason=None if valid else f'Universe below {settings.min_universe}; official lists withheld',
        basis='not available; explicitly excluded from available weight',
        oi_scope='current fixed main/secondary pair, not whole commodity OI',
        option_suitability='not assessed: IV, expiry and executable quotes required',
        history_rps_universe='current liquid eligible basket; not a bias-free backtest')
    atomic_json(report,out/'quality.json')
    write_daily(out,report,lists)
    return report,lists


def write_daily(out, report, lists):
    lines=[f'# 商品期货趋势雷达 {report["asof"]}', '',
        f'当前有成交品种 {report["current_liquid_commodities"]} 个，历史完整且可计算指标的品种 {report["eligible_universe"]} 个。',
        '主连已按同日新旧主力价格比复权；量仓使用当前固定的主力/次主力月对，不代表全品种OI。',
        '基差缺失，分数按可用权重标准化，覆盖率低于配置门槛不进入榜单。',
        '表中RPS20为方向强度：多头使用原始RPS，空头使用100−原始RPS，越高表示该方向越强。', '']
    if not report['success']:
        lines += [f'正式榜单未发布：{report["reason"]}', '']
    for key,title in [('long_startup','多头启动观察'),('short_startup','空头启动观察'),('long_trend','已确认多头趋势'),('short_trend','已确认空头趋势')]:
        lines += [f'## {title}', '']
        frame=lists[key]
        if frame.empty:
            lines += ['没有符合当前门槛的品种。', '']
            continue
        lines += ['| 品种 | 主力 | 次主力 | 趋势分 | 启动分 | 命中项 | ADX | RPS20 | 覆盖率 |',
            '|---|---|---|---:|---:|---:|---:|---:|---:|']
        for row in frame.itertuples():
            lines.append(f'| {row.ts_code} | {row.main_code} | {getattr(row,"secondary_code","")} | {row.trend_score:.1f} | {row.startup_score:.1f} | {row.startup_hits}/9 | {row.adx:.1f} | {row.directional_rps20:.1f} | {row.trend_coverage}% |')
        lines += ['']
    lines += ['完整指标和六模块分数见同目录 indicators.csv 与 scores.csv；缺失/排除原因见 exclusions.csv。',
        '筛选结果用于品种观察，尚未评估期权IV、剩余期限及可成交报价。',
        '评分参数为第一版规则，尚未做历史收益验证；分数不代表胜率。']
    (out/'daily_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description='中国商品期货趋势分/启动分筛选')
    parser.add_argument('--asof',required=True,help='收盘交易日YYYYMMDD')
    parser.add_argument('--data-dir',type=Path,default=DATA_DIR)
    parser.add_argument('--settings',type=Path,default=Path(__file__).with_name('strategy_config.json'))
    parser.add_argument('--refresh-history',action='store_true',help='采集当天主次合约并补充主力历史；首次使用需要')
    parser.add_argument('--force',action='store_true',help='强制刷新供应商数据，需要同时使用--refresh-history')
    args=parser.parse_args()
    try:
        settings=Settings.load(args.settings)
        if args.force and not args.refresh_history:
            raise ValueError('--force requires --refresh-history')
        if args.refresh_history:
            collector=make_collector(root=args.data_dir)
            snapshot=run_focused(collector,args.asof,args.asof,args.force)
            if not snapshot['success'] or args.asof not in snapshot['published_days']:
                raise DataError('Snapshot incomplete/date closed; inspect quality/latest_run.json')
            selected=read_csv(args.data_dir/f'raw/selected/{args.asof}.csv')
            prepare_history(collector,selected,args.asof,min_history=settings.min_history,force=args.force)
        report,_=screen(args.data_dir,args.asof,settings)
    except (DataError,ValueError,TypeError,OSError,KeyError) as exc:
        print(f'Screening failed: {exc}')
        return 1
    print(f'Eligible universe: {report["eligible_universe"]}; lists: {report["counts"]}')
    print(f'Report: {args.data_dir / "processed/radar" / args.asof / "daily_report.md"}')
    return 0 if report['success'] else 1


if __name__=='__main__':
    raise SystemExit(main())
