"""Chronological, non-overlapping trend comparison on the current eligible basket."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from collector import atomic_json, atomic_csv
from dashboard_data import public_metrics, classify
from historical_validation import historical_panels, event_outcome
from screen_futures import load_inputs
from strategy import Settings, evaluate
from decision_v2 import side_strength
from trend_model import price_trend, MODEL_VERSION


def summarize(frame):
    active = frame[frame.side.ne('neutral')]
    by_date = active.groupby('signal_date').net_return.mean()
    return dict(samples=len(frame), signals=len(active), coverage=round(len(active)/len(frame)*100, 2) if len(frame) else None,
                hit_rate=round(active.net_return.gt(0).mean()*100, 2) if len(active) else None,
                mean_return=round(active.net_return.mean(), 4) if len(active) else None,
                median_return=round(active.net_return.median(), 4) if len(active) else None,
                date_balanced_return=round(by_date.mean(), 4) if len(by_date) else None)


def run(root, asof, out):
    _, histories, _, _ = load_inputs(root, asof, Settings())
    tables = historical_panels(histories)
    dates = sorted(set.intersection(*(set(t.trade_date.iloc[125:]) for t in tables.values())))
    blocks = [list(a) for a in np.array_split(dates, 3)]
    events = []
    for hold in [5, 20]:
        for block_id, block in enumerate(blocks, 1):
            if len(block) <= hold:
                continue
            # Same dates across models; no returns cross chronological block edges.
            signals = block[:-hold:hold]
            for code, table in tables.items():
                indexes = {str(day): i for i, day in enumerate(table.trade_date)}
                for date in signals:
                    i = indexes[date]
                    if str(table.trade_date.iloc[i+hold]) > block[-1]:
                        continue
                    row = public_metrics(table.iloc[i].to_dict())
                    model = price_trend(row)
                    if model['status'] != 'ok':
                        continue
                    sides = {'unified': model['side']}
                    for omit in ['price', 'momentum', 'di']:
                        sides['without_'+omit] = price_trend(row, omit)['side']
                    ret = row['return20']
                    sides['momentum20'] = 'long' if ret > 0 else 'short' if ret < 0 else 'neutral'
                    sides['ma20'] = ('long' if row['close'] > row['ma20'] and row['slope20'] > 0 else
                                     'short' if row['close'] < row['ma20'] and row['slope20'] < 0 else 'neutral')
                    sides['rps20'] = 'long' if row['rps20'] >= 65 else 'short' if row['rps20'] <= 35 else 'neutral'
                    sides['rps5'] = 'long' if row['rps5'] >= 65 else 'short' if row['rps5'] <= 35 else 'neutral'
                    delta = row['rps20']-row['rps20_prev5']
                    sides['rps_accel'] = 'long' if delta >= 10 else 'short' if delta <= -10 else 'neutral'
                    strengths = []
                    for d in [1, -1]:
                        prior = evaluate(table.iloc[:i+1], d, {}, Settings())
                        strengths.append(side_strength(prior))
                    legacy = strengths[0]-strengths[1]
                    sides['legacy_price_only'] = 'long' if legacy >= 25 else 'short' if legacy <= -25 else 'neutral'
                    for name, side in sides.items():
                        outcome = event_outcome(table, i, side if side != 'neutral' else 'long', hold, 10)
                        if outcome['status'] != 'completed':
                            continue
                        events.append(dict(model=name, block=block_id, hold=hold, ts_code=code,
                                           sector=classify(code), side=side, **outcome))
    frame = pd.DataFrame(events)
    summaries = [dict(model=model, hold=int(hold), **summarize(group),
                     blocks=[dict(block=int(b), **summarize(g)) for b, g in group.groupby('block')])
                 for (model, hold), group in frame.groupby(['model', 'hold'])]
    report = dict(asof=asof, model_version=MODEL_VERSION, universe=len(tables),
                  blocks=[dict(start=b[0], end=b[-1]) for b in blocks if b], summary=summaries,
                  limitations=[
                      '当前有效品种篮子回看，存在幸存者偏差；同日品种高度相关，信号条数不是独立样本数。',
                      '预先固定参数的三段时间检验，未训练或调参；不是独立保留样本，更非最优证明。',
                      '收盘信号，次日开盘进，第N日收盘出；同品种不重叠，假设往返成本10bp。',
                      '复权主连收益非实盘净值；滑点、涨跌停和换月成本未完整建模。',
                      '历史固定月对与现货/库存不完整，未检验OI/结构增量；legacy仅价格部分可复建。',
                      '中性样本不计命中率；不同模型覆盖不同，需结合覆盖率和三个时段而非仅比总命中率。'])
    atomic_json(report, out/'factor_audit.json')
    atomic_csv(frame, out/'factor_events.csv')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--asof', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root, args.asof, args.out)
    for row in result['summary']:
        print(row['model'], row['hold'], row['signals'], row['coverage'], row['hit_rate'], row['mean_return'])
