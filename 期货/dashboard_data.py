"""Validated public data for the local dashboard. No provider credentials."""
import json
import math
from pathlib import Path
import pandas as pd
from screen_futures import screen, load_inputs
from strategy import Settings
from collector import read_csv
from trend_phases import PhaseSettings, phase_for_row, enrich_technical
from historical_validation import historical_panels
from dataclasses import asdict
from decision_v2 import build_decisions, unify_records
from trend_model import MODEL_VERSION
from futures_signals import chart_signals, signal_for_history

SECTORS = json.loads(Path(__file__).with_name('sectors.json').read_text(encoding='utf-8'))
PERCENT_FIELDS = {'return1','return5','return20','return60','return120','slope20','slope60','slope120',
    'trend_spread','trend_spread_change5','atr_change5','oi_change5','oi_change20',
    'main_oi_change5','main_oi_change20','secondary_oi_change5','secondary_oi_change20',
    'rollover_absorption5','carry_annualized','carry_change5','carry_change20','spread_pct'}


def classify(code):
    product = code.split('.')[0]
    return next((name for name, members in SECTORS.items() if product in members), '其他')


def public_metrics(row):
    output = {}
    for key, value in row.items():
        if value is None or pd.isna(value):
            output[key] = None
        elif isinstance(value, (bool,)) or type(value).__name__ == 'bool':
            output[key] = bool(value)
        elif isinstance(value, str):
            output[key] = value
        else:
            numeric = float(value)
            output[key] = numeric * (100 if key in PERCENT_FIELDS else 1) if math.isfinite(numeric) else None
    return output


def aggregate_curves(curves):
    groups = {}
    for sector in SECTORS:
        members = {code: dict(values) for code, values in curves.items() if classify(code) == sector}
        if not members:
            continue
        dates = sorted(set.intersection(*(set(values) for values in members.values())))
        if not dates:
            continue
        indices = [[day, sum(values[day]/values[dates[0]]*100 for values in members.values())/len(members)] for day in dates]
        groups[sector] = {'members': list(members), 'count':len(members), 'values':indices}
    return groups


LABELS = {
    'close':('复权收盘','价格 / 均线',''), 'raw_close':('真实主力收盘','价格 / 均线',''),
    'ma20':('MA20','价格 / 均线',''), 'ma60':('MA60','价格 / 均线',''), 'ma120':('MA120','价格 / 均线',''),
    'return20':('20日涨跌幅','价格 / 均线','%'), 'return60':('60日涨跌幅','价格 / 均线','%'), 'return120':('120日涨跌幅','价格 / 均线','%'),
    'return5':('5日涨跌幅','价格 / 均线','%'),
    'return1':('1日收盘涨跌幅','价格 / 均线','%'),
    'day_change':('当日涨跌幅（昨结）','价格 / 均线','%'),
    'rps5':('RPS5','相对强弱',''),
    'rps_accel':('RPS20五日变化','相对强弱','百分点'),
    'pair_oi':('固定主次合计持仓','量仓 / 结构','手'),
    'main_oi':('主力持仓','量仓 / 结构','手'),
    'secondary_oi':('次主力持仓','量仓 / 结构','手'),
    'burst_score':('标的爆发指数','统一趋势','分'),
    'burst_coverage':('爆发因子覆盖率','统一趋势','%'),
    'slope20':('MA20五日斜率','价格 / 均线','%'), 'slope60':('MA60五日斜率','价格 / 均线','%'), 'slope120':('MA120五日斜率','价格 / 均线','%'),
    'trend_spread':('MA20 / MA120发散度','价格 / 均线','%'), 'trend_spread_change5':('发散度五日变化','价格 / 均线','百分点'),
    'ma_spread_atr_change5':('均线ATR发散五日变化','价格 / 均线','ATR'),
    'rps20':('原始RPS20','相对强弱',''), 'rps60':('原始RPS60','相对强弱',''), 'rps120':('原始RPS120','相对强弱',''),
    'directional_rps20':('方向RPS20','相对强弱',''), 'directional_rps60':('方向RPS60','相对强弱',''), 'directional_rps120':('方向RPS120','相对强弱',''),
    'adx':('ADX14','趋势强度',''), 'adx_slope':('ADX五日变化','趋势强度','点'), 'plus_di':('+DI14','趋势强度',''), 'minus_di':('−DI14','趋势强度',''),
    'atr14':('ATR14','波动 / 突破',''), 'atr_pct':('ATR百分比','波动 / 突破','%'), 'atr_ratio':('ATR / 六十日均ATR','波动 / 突破','倍'),
    'atr_change5':('ATR五日变化','波动 / 突破','%'), 'atr_percentile':('ATR百分比252日分位','波动 / 突破',''),
    'high20':('前20日最高价','波动 / 突破',''), 'low20':('前20日最低价','波动 / 突破',''), 'high55':('前55日最高价','波动 / 突破',''), 'low55':('前55日最低价','波动 / 突破',''),
    'break20_up':('当日向上突破20日','波动 / 突破',''), 'break20_down':('当日向下突破20日','波动 / 突破',''), 'break55_up':('当日向上突破55日','波动 / 突破',''), 'break55_down':('当日向下突破55日','波动 / 突破',''),
    'oi_change5':('固定主次合约OI五日变化','量仓 / 结构','%'), 'oi_change20':('固定主次合约OI二十日变化','量仓 / 结构','%'), 'volume_ratio':('固定月对成交量 / 前20日均量','量仓 / 结构','倍'),
    'main_oi_change5':('主力合约OI五日变化','移仓换月','%'), 'main_oi_change20':('主力合约OI二十日变化','移仓换月','%'),
    'secondary_oi_change5':('次主力合约OI五日变化','移仓换月','%'), 'secondary_oi_change20':('次主力合约OI二十日变化','移仓换月','%'),
    'rollover_absorption5':('远月接仓比例','移仓换月','%'), 'rollover_transfer':('移仓中：远月接住主力减仓','移仓换月',''),
    'spread':('近月减远月结算价差','量仓 / 结构',''), 'spread_change5':('月间价差五日变化','量仓 / 结构',''),
    'spread_pct':('近远月价差百分比','量仓 / 结构','%'), 'carry_annualized':('年化期限结构Carry','量仓 / 结构','%'),
    'carry_change5':('Carry五日变化','量仓 / 结构','百分点'), 'carry_change20':('Carry二十日变化','量仓 / 结构','百分点'),
    'structure':('期限结构形态','量仓 / 结构',''), 'structure_flip5':('期限结构五日内拐头','量仓 / 结构',''),
    'curvature':('期限结构曲率（近+远-2×中）','量仓 / 结构',''),
    'basis_change5':('基差五日变化（未接入）','量仓 / 结构',''), 'spot_change5':('现货五日变化（未接入）','量仓 / 结构','%'),
    'trend_score':('原版趋势分','策略评分',''), 'startup_score':('原版启动分','策略评分',''), 'startup_hits':('启动信号命中数','策略评分','项'),
    'trend_coverage':('趋势因子覆盖率','策略评分','%'), 'startup_coverage':('启动因子覆盖率','策略评分','%'), 'extension_atr':('顺方向偏离MA20','策略评分','ATR'),
    'confirmed':('原版趋势方向确认','策略评分',''), 'startup_eligible':('原版启动榜合格','策略评分',''),
    'dir_score':('DIR_SCORE','V2决策',''), 'start_score':('START_SCORE','V2决策',''),
    'price_rps':('Price RPS','V2决策',''), 'vol_rps':('VOL_RPS','V2决策',''), 'oi_change_rps':('ΔOI_RPS','V2决策',''),
    'v2_active':('V2活跃候选','V2决策',''), 'v2_trade_allowed':('V2允许期权表达','V2决策',''), 'structure_support':('商品结构支持','V2决策',''),
    'signal_ma_cross':('近期均线交叉','启动信号',''), 'signal_rps_jump':('RPS跃升','启动信号',''), 'signal_rps_lead':('短期RPS领先长期','启动信号',''),
    'signal_base_breakout':('近期基底突破','启动信号',''), 'signal_adx_rising':('ADX启动抬升','启动信号',''), 'signal_atr_expansion':('ATR压缩转扩张','启动信号',''),
    'signal_oi_growth':('固定月对OI增长','启动信号',''), 'signal_mild_volume':('温和放量','启动信号',''), 'signal_curve_strength':('月间结构同向强化','启动信号',''),
    'score_ma':('均线模块分','模块评分','分'), 'score_rps':('RPS模块分','模块评分','分'), 'score_breakout':('突破模块分','模块评分','分'),
    'score_quality':('趋势质量模块分','模块评分','分'), 'score_funding':('量仓模块分','模块评分','分'), 'score_structure':('月间结构模块分','模块评分','分'), 'score_basis':('基差模块分（未接入）','模块评分','分')}
LABELS.update({'technical_start':('技术启动阶段','趋势阶段',''),'phase_match':('阶段方向与筛选方向一致','趋势阶段',''),
    'phase_age':('当前阶段持续交易日','趋势阶段','日'),'phase_extension_atr':('当前趋势方向偏离MA20','趋势阶段','ATR'),
    'commodity_oi_change5':('外部全品种OI五日变化','补充数据','%'),'commodity_oi_change20':('外部全品种OI二十日变化','补充数据','%')})
BOOLEAN_FIELDS = {key for key in LABELS if key.startswith(('signal_','break'))} | {'confirmed','startup_eligible'}
BOOLEAN_FIELDS |= {'technical_start','phase_match','rollover_transfer','structure_flip5'}
BOOLEAN_FIELDS |= {'v2_active','v2_trade_allowed','structure_support'}


def build_payload(root, asof,phase_settings=None):
    root = Path(root)
    quality, _ = screen(root, asof)
    selected, histories, exclusions, _ = load_inputs(root, asof, Settings())
    snapshot = selected[selected.role.eq('main')].set_index('main_code').to_dict('index')
    common = sorted(set.intersection(*(set(h.trade_date) for h in histories.values())))[-251:]
    curves, moving, candles, technical_signals = {}, {}, {}, {}
    for code, table in histories.items():
        shared = table.set_index('trade_date').loc[common]
        curves[code] = [[day, round(float(value),6)] for day,value in shared.close.items()]
        candles[code] = [[day, round(float(row['open']),6), round(float(row['high']),6), round(float(row['low']),6), round(float(row['close']),6)]
                         for day,row in shared.iterrows()]
        moving[code] = {key:[round(float(v),6) if pd.notna(v) else None for v in shared[key]] for key in ['ma20','ma60','ma120']}
        technical_signals[code] = chart_signals(shared.reset_index())
    scores = read_csv(root/f'processed/radar/{asof}/scores.csv')
    records = [public_metrics(row) for row in scores.to_dict('records')]
    phase_settings=phase_settings or PhaseSettings()
    phases={}
    for code,table in historical_panels(histories).items():
        frame=enrich_technical(table,'long');prior=None;age=0
        for row in frame.iloc[279:].to_dict('records'):
            phase=phase_for_row(row,phase_settings);identity=(phase['phase'],phase['trend_direction'])
            age=age+1 if identity==prior else 1;prior=identity
        phases[code]=phase|{'phase_age':age}
    names = {code: SECTORS[classify(code)].get(code.split('.')[0],code) for code in histories}
    factors = [dict(key=key,label=value[0],group=value[1],unit=value[2],type='boolean' if key in BOOLEAN_FIELDS else 'number') for key,value in LABELS.items()]
    for record in records:
        record['name'], record['sector'] = names[record['ts_code']], classify(record['ts_code'])
        record.update(signal_for_history(histories[record['ts_code']]))
        bar = snapshot.get(record['ts_code'], {})
        pre_settle, close = bar.get('pre_settle'), bar.get('close')
        record['day_change'] = ((float(close)/float(pre_settle)-1)*100
                                if pd.notna(close) and pd.notna(pre_settle) and pre_settle > 0 else None)
        record['main_oi'] = float(bar['oi']) if pd.notna(bar.get('oi')) else None
        record['trader_positions'] = None
        record.update(phases[record['ts_code']]);record['phase_match']=record['trend_direction']==record['direction']
        record['technical_start']=record['technical_start'] and record['phase_match']
    from supplements import supplement_context
    supplemental_status=[]
    for record in records:
        context,status=supplement_context(root,record['ts_code'],asof,record, histories[record['ts_code']].trade_date.tolist())
        record.update(context)
        if record['direction']=='long':supplemental_status.append(dict(ts_code=record['ts_code'],**status))
    # 可交易期限曲线：采集层保存的全合约真实快照（raw/curve），剔除临近交割后按OI取三档。
    import re
    from term_structure import real_curve, tradable_curve, curvature
    curve_path = root/f'raw/curve/{asof}.csv'
    liquid = real_curve(read_csv(curve_path), asof) if curve_path.exists() else None
    for record in records:
        if liquid is None:
            record['curve'],record['curvature'] = [],None
            continue
        subset = liquid[liquid.ts_code.str.match(rf'^{re.escape(record["ts_code"].split(".")[0])}\d+\.')]
        rows = tradable_curve(subset)
        record['curve'] = rows
        record['curvature'] = curvature(rows[0]['settle'],rows[1]['settle'],rows[2]['settle']) if len(rows)>=3 else None
    decisions = build_decisions(records)
    unify_records(records, decisions)
    for decision in decisions:
        decision.update(signal_for_history(histories[decision['ts_code']]))
    decision_summary = {state: sum(1 for row in decisions if row['state_v2'] == state) for state in ['WAIT','PREPARE','START','TREND','EXHAUST']}
    return dict(asof=asof, names=names, records=records, curves=curves, moving=moving, candles=candles,
        technical_signals=technical_signals,
        decisions=decisions, decision_summary=decision_summary, model_version=MODEL_VERSION,
        sectors=aggregate_curves(curves), factors=factors, quality=quality, exclusions=exclusions,
        phase_settings=asdict(phase_settings),supplemental_status=supplemental_status,
        scope='主次合约OI保持固定月对口径；外部全品种OI、现货/基差独立列示来源和覆盖', curve_scope='复权主连；大类为当前有效成分等权对比指数，非交易所指数')
