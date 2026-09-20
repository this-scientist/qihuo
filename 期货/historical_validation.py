"""Exploratory causal signal-event study, not a survivorship-free portfolio backtest."""
import math
import uuid
from dataclasses import asdict
import pandas as pd
from collector import DataError, atomic_csv, atomic_json
from screen_futures import load_inputs
from strategy import Settings, rps_panel
from trend_phases import phase_for_row, enrich_technical, PhaseSettings


def event_outcome(data,signal_index,direction,hold=20,cost_bps=0):
    entry,exit_index=signal_index+1,signal_index+hold
    result=dict(signal_date=str(data.trade_date.iloc[signal_index]),direction=direction,status='pending')
    if entry>=len(data) or exit_index>=len(data):return result
    frame=data.iloc[entry:exit_index+1]
    price=float(data.open.iloc[entry]);exit_price=float(data.close.iloc[exit_index]);d=1 if direction=='long' else -1
    gross=d*(exit_price/price-1)*100
    favorable=(float(frame.high.max())/price-1)*100 if d==1 else (1-float(frame.low.min())/price)*100
    adverse=(float(frame.low.min())/price-1)*100 if d==1 else (1-float(frame.high.max())/price)*100
    result.update(status='completed',entry_date=str(data.trade_date.iloc[entry]),exit_date=str(data.trade_date.iloc[exit_index]),
        entry_price=price,exit_price=exit_price,gross_return=round(gross,6),net_return=round(gross-cost_bps/100,6),
        mfe=round(max(0,favorable),6),mae=round(min(0,adverse),6),rolls=int(data.mapping_ts_code.iloc[entry:exit_index+1].ne(data.mapping_ts_code.shift(1).iloc[entry:exit_index+1]).sum()) if 'mapping_ts_code' in data else 0)
    return result


def historical_panels(histories):
    panel=rps_panel(pd.concat(histories.values(),ignore_index=True))
    rank_cols=[c for c in panel if c.startswith('rps')]
    return {code:table.merge(panel.loc[panel.ts_code.eq(code),['trade_date']+rank_cols],on='trade_date',validate='one_to_one') for code,table in histories.items()}


def run_validation(root,asof,request):
    from dashboard_data import public_metrics, classify, LABELS
    from research_rules import validate_rules, rule_matches
    _,histories,_,_=load_inputs(root,asof,Settings())
    hold=request.get('hold',20);cost=request.get('cost_bps',0);cooldown=request.get('cooldown',20)
    if type(hold) is not int or not 1<=hold<=120 or type(cooldown) is not int or not 1<=cooldown<=250 or not isinstance(cost,(int,float)) or not math.isfinite(cost) or not 0<=cost<=1000:raise ValueError('Invalid hold/cooldown/cost')
    direction=request.get('direction','both');mode=request.get('mode','technical_start');rules=request.get('rules',[]);match=request.get('match','all')
    if direction not in ['long','short','both'] or mode not in ['technical_start','custom']:raise ValueError('Invalid validation mode/direction')
    validate_rules(rules,match,LABELS)
    start=request.get('start','');end=request.get('end',asof)
    if start and (len(start)!=8 or not start.isdigit()) or len(end)!=8 or not end.isdigit() or end>asof or start and start>end:raise ValueError('Invalid validation dates')
    settings=PhaseSettings(**request.get('phase_settings',{}))
    events=[];missing_count=0;scanned=0
    for code,data in historical_panels(histories).items():
        if request.get('sector','all')!='all' and classify(code)!=request['sector']:continue
        for side in ['long','short'] if direction=='both' else [direction]:
            table=enrich_technical(data,side);last_event=-10000;prior_match=False
            for i in range(279,len(table)):
                row=table.iloc[i];day=str(row.trade_date)
                phase=phase_for_row(row,settings)
                values=public_metrics(row.to_dict())|phase|{'technical_start':phase['technical_start'] and phase['trend_direction']==side,'phase_match':phase['trend_direction']==side}
                matched=values['technical_start'] if mode=='technical_start' else rule_matches(values,rules,match)[0]
                if day>end:break
                if start and day<start:prior_match=matched;continue
                scanned+=1
                if mode=='custom':missing_count+=int(rule_matches(values,rules,match)[1]>0)
                # Transition-only, and no overlapping events within commodity/direction.
                if matched and not prior_match and i-last_event>=max(hold,cooldown):
                    events.append(dict(ts_code=code,sector=classify(code),phase=phase['phase'],**event_outcome(table,i,side,hold,cost)))
                    last_event=i
                prior_match=matched
    finished=[e for e in events if e['status']=='completed'];returns=[e['net_return'] for e in finished]
    run_id=uuid.uuid4().hex
    report=dict(id=run_id,asof=asof,request=request,events=events,summary=dict(signals=len(events),completed=len(finished),pending=len(events)-len(finished),
        positive_rate=sum(r>0 for r in returns)/len(returns)*100 if returns else None,mean_return=sum(returns)/len(returns) if returns else None,
        median_return=float(pd.Series(returns).median()) if returns else None,mean_mfe=sum(e['mfe'] for e in finished)/len(finished) if finished else None,
        mean_mae=sum(e['mae'] for e in finished)/len(finished) if finished else None,scanned=scanned,missing_rows=missing_count),
        limitations=['当前有效篮子回看，存在幸存者偏差；属于探索性信号事件研究',
            '历史主次身份量仓/基差及原版评分不可重建，历史规则中这些因子为缺失',
            '收盘信号→下一交易日开盘→第N交易日收盘；每品种方向不重叠，未结束事件不计收益',
            '复权主连事件收益，不是保证金收益、可执行组合净值或期权收益；换月执行成本未独立建模'])
    folder=root/'processed/validation';atomic_json(report,folder/f'{run_id}.json');atomic_csv(pd.DataFrame(events),folder/f'{run_id}.csv')
    return report
