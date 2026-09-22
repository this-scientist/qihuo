"""V2 decision layer: direction -> start -> structure -> option."""
from collections import defaultdict
import math
from trend_state import classify_trend_state
from trend_model import MODEL_VERSION, price_trend, burst_index


DIR_GATE = 25
STRONG_DIR_GATE = 50
START_GATE = 70
READY_GATE = 50


def _finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _num(value, default=0.0):
    return float(value) if _finite(value) else default


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, float(value)))


def _sign(direction):
    return 1 if direction == 'long' else -1 if direction == 'short' else 0


def _truthy(value):
    if isinstance(value, bool):
        return value
    return str(value).lower() == 'true'


def _ratio_score(value, max_value):
    return _clamp(_num(value) / max_value)


def _funding_strength(row, side_sign):
    oi = row.get('oi_change5')
    ret = row.get('return5')
    if _finite(oi) and _finite(ret):
        oi_value = float(oi)
        ret_value = float(ret)
        if oi_value > 0 and side_sign * ret_value > 0:
            return 1.0
        if oi_value > 0:
            return 0.55
        if side_sign * ret_value > 0 and oi_value >= -2:
            return 0.25
        return 0.0
    if _finite(row.get('score_funding')):
        return _ratio_score(row.get('score_funding'), 15)
    return 0.0


def side_strength(row):
    """Return 0-100 evidence that this directional row is the least-resistance side."""
    sign = _sign(row.get('direction'))
    if not sign:
        return 0.0
    price_structure = _ratio_score(row.get('score_ma'), 20) * 35
    adx_di = _ratio_score(row.get('score_quality'), 15) * 25
    rps = _ratio_score(row.get('score_rps'), 20) * 20
    price_oi = _funding_strength(row, sign) * 20
    return round(price_structure + adx_di + rps + price_oi, 2)


def _volume_attention(row):
    ratio = row.get('volume_ratio')
    if not _finite(ratio):
        return None
    ratio = float(ratio)
    if ratio >= 2.0:
        return 100.0
    if ratio >= 1.5:
        return 85.0
    if ratio >= 1.2:
        return 70.0
    if ratio >= 1.0:
        return 50.0
    return max(0.0, ratio * 50)


def start_score(row):
    """Return 0-100 score for trend-start evidence on the selected side."""
    sign = _sign(row.get('direction'))
    breakout = 30.0 if _truthy(row.get('signal_base_breakout')) else _ratio_score(row.get('score_breakout'), 20) * 30

    volume = 0.0
    attention = _volume_attention(row)
    if attention is not None:
        volume = min(25.0, attention / 100 * 25)
    if _truthy(row.get('signal_mild_volume')):
        volume = max(volume, 20.0)

    oi = 0.0
    oi_change = row.get('oi_change5')
    if _finite(oi_change):
        oi_value = max(0.0, float(oi_change))
        oi = min(25.0, 12.5 + oi_value * 2.0) if oi_value > 0 else 0.0
    if _truthy(row.get('signal_oi_growth')):
        oi = max(oi, 25.0)
    if sign and _finite(row.get('return5')) and sign * float(row.get('return5')) <= 0:
        oi = min(oi, 12.0)

    adx = 10.0 if _truthy(row.get('signal_adx_rising')) else (6.0 if _num(row.get('adx_slope')) > 0 else 0.0)
    atr = 10.0 if _truthy(row.get('signal_atr_expansion')) else (5.0 if _num(row.get('atr_change5')) > 0 else 0.0)
    return round(min(100.0, breakout + volume + oi + adx + atr), 2)


def structure_confirm(row, side):
    from option_scanner import structure_radar
    radar = row.get('structure_evidence') or structure_radar(row)
    if not radar['coverage']:
        return 'UNKNOWN'
    if side not in {'long', 'short'} or not radar['dominant']:
        return 'NEUTRAL'
    return 'SUPPORT' if radar['dominant'] == side else 'CONFLICT'


def _dir_bucket(score):
    if score >= STRONG_DIR_GATE:
        return '强多'
    if score >= DIR_GATE:
        return '偏多'
    if score <= -STRONG_DIR_GATE:
        return '强空'
    if score <= -DIR_GATE:
        return '偏空'
    return '中性'


def _state(row, dir_score, start, structure):
    if abs(dir_score) < DIR_GATE:
        return 'WAIT'
    if _truthy(row.get('overextended')) or row.get('phase') == '过度延伸':
        return 'EXHAUST'
    if row.get('phase') == '趋势减弱' and start < READY_GATE:
        return 'EXHAUST'
    if start >= START_GATE and (_truthy(row.get('startup_eligible')) or _truthy(row.get('technical_start')) or _truthy(row.get('signal_base_breakout'))):
        return 'START'
    if _truthy(row.get('confirmed')) or row.get('phase') in {'持续趋势', '中短期强势'}:
        return 'TREND'
    if start >= READY_GATE or row.get('phase') in {'方向形成', '趋势启动'}:
        return 'PREPARE'
    if structure == 'CONFLICT':
        return 'PREPARE'
    return 'PREPARE'


def _candidate_tier(state, start):
    if state in {'START', 'TREND'}:
        return 'ACTIVE'
    if state == 'PREPARE' and start >= READY_GATE:
        return 'READY'
    if state == 'PREPARE':
        return 'WATCH'
    return 'WAIT'


def _option_action(side, state, structure, trend_gate=None):
    if trend_gate == 'BLOCK':
        return '不做'
    if state in {'WAIT', 'EXHAUST'} or structure == 'CONFLICT':
        return '不做'
    if state == 'PREPARE':
        return '等待'
    if trend_gate == 'CONDITIONAL' and state != 'TREND':
        return '等待'
    return 'Call' if side == 'long' else 'Put' if side == 'short' else '不做'


def _direction_label(side):
    return '多' if side == 'long' else '空' if side == 'short' else '中性'


def _oi_behavior(row):
    value = row.get('oi_change5')
    if not _finite(value):
        return '缺失'
    value = float(value)
    if value > 1:
        return '增仓'
    if value < -1:
        return '减仓'
    return '平'


def _pick_side(rows):
    by_side = {row.get('direction'): row for row in rows}
    long = by_side.get('long')
    short = by_side.get('short')
    long_strength = side_strength(long) if long else 0.0
    short_strength = side_strength(short) if short else 0.0
    if long and short:
        score = round(long_strength - short_strength, 2)
    elif long:
        score = round(long_strength, 2)
    elif short:
        score = round(-short_strength, 2)
    else:
        score = 0.0
    if score >= DIR_GATE:
        return 'long', long or short, score, long_strength, short_strength
    if score <= -DIR_GATE:
        return 'short', short or long, score, long_strength, short_strength
    primary = long if long_strength >= short_strength else short
    return 'neutral', primary or (rows[0] if rows else {}), score, long_strength, short_strength


def _rank_field(decisions, source, target, fallback):
    valid = [(idx, decision.get(source)) for idx, decision in enumerate(decisions) if _finite(decision.get(source))]
    if not valid:
        for decision in decisions:
            decision[target] = None
        return
    if len(valid) == 1:
        idx, _ = valid[0]
        decisions[idx][target] = fallback(decisions[idx])
        for pos, decision in enumerate(decisions):
            if pos != idx:
                decision[target] = None
        return
    ordered = sorted(valid, key=lambda item: float(item[1]))
    for decision in decisions:
        decision[target] = None
    ranks = defaultdict(list)
    for rank, (_, value) in enumerate(ordered):
        ranks[float(value)].append(rank)
    for idx, value in ordered:
        tied = ranks[float(value)]
        decisions[idx][target] = round(sum(tied)/len(tied)/(len(ordered)-1)*100, 2)


def build_decisions(records):
    grouped = defaultdict(list)
    for row in records:
        grouped[row.get('ts_code')].append(dict(row))

    decisions = []
    for code, rows in grouped.items():
        side, primary, dir_score, long_strength, short_strength = _pick_side(rows)
        model = price_trend(rows[0])
        if model['status'] == 'ok':
            side, dir_score = model['side'], model['score']
            primary = next((r for r in rows if r.get('direction') == side), primary)
        else:
            side, dir_score = 'neutral', 0.0
        decision = dict(primary)
        decision['trend_model'] = MODEL_VERSION
        decision['trend_model_status'] = model['status']
        decision['trend_components'] = model['components']
        decision['legacy_trend_direction'] = decision.get('trend_direction')
        decision['trend_direction'] = side
        decision['rps_accel'] = (float(decision['rps20'])-float(decision['rps20_prev5'])
                                 if _finite(decision.get('rps20')) and _finite(decision.get('rps20_prev5')) else None)
        if model['status'] == 'ok':
            sign = _sign(side)
            decision['extension_atr'] = sign * (decision['close']-decision['ma20'])/decision['atr14']
            decision['overextended'] = decision['extension_atr'] > 3
            decision['confirmed'] = abs(dir_score) >= 50 and _num(decision.get('adx')) >= 20
            decision['phase'] = ('震荡' if not sign else '过度延伸' if decision['overextended'] else
                                 '持续趋势' if decision['confirmed'] else '方向形成')
        from option_scanner import structure_radar
        decision['structure_evidence'] = structure_radar(decision)
        decision['structure_direction'] = decision['structure_evidence']['dominant'] or ('neutral' if decision['structure_evidence']['coverage'] else 'unknown')
        decision['structure_score'] = (round(decision['structure_evidence']['long_score']-decision['structure_evidence']['short_score'], 2)
                                       if decision['structure_evidence']['coverage'] else None)
        decision.update(burst_index(decision, side))
        decision['ts_code'] = code
        decision['decision_side'] = side
        decision['decision_direction'] = _direction_label(side)
        decision['dir_score'] = dir_score
        decision['dir_bucket'] = _dir_bucket(dir_score)
        decision['long_dir_evidence'] = long_strength
        decision['short_dir_evidence'] = short_strength
        decision['start_score'] = 0.0 if side == 'neutral' else start_score(decision)
        decision['price_rps'] = decision.get('directional_rps20') if side != 'neutral' else None
        decision['structure_confirm'] = structure_confirm(decision, side)
        decision['state_v2'] = _state(decision, dir_score, decision['start_score'], decision['structure_confirm'])
        decision.update(classify_trend_state(decision, side, decision['state_v2'], decision['start_score']))
        decision['phase_reason'] = decision['trend_state_reason']
        decision['phase_age'] = None
        decision['candidate_tier'] = _candidate_tier(decision['state_v2'], decision['start_score'])
        decision['option_action'] = _option_action(side, decision['state_v2'], decision['structure_confirm'], decision.get('trend_option_gate'))
        decision['v2_active'] = decision['state_v2'] in {'START', 'TREND'}
        decision['v2_trade_allowed'] = decision['option_action'] in {'Call', 'Put'}
        decision['structure_support'] = decision['structure_confirm'] == 'SUPPORT'
        decision['oi_behavior'] = _oi_behavior(decision)
        decision['v2_rank'] = (
            0 if decision['state_v2'] == 'START' else
            1 if decision['state_v2'] == 'TREND' else
            2 if decision['state_v2'] == 'PREPARE' else
            3 if decision['state_v2'] == 'EXHAUST' else 4
        )
        decisions.append(decision)

    _rank_field(decisions, 'volume_ratio', 'vol_rps', lambda row: _volume_attention(row))
    _rank_field(decisions, 'oi_change5', 'oi_change_rps', lambda row: min(100.0, max(0.0, _num(row.get('oi_change5')) * 10)))
    return decisions


def unify_records(records, decisions):
    """Directional input rows remain two-sided; commodity conclusions are shared."""
    by_code = {row['ts_code']: row for row in decisions}
    fields = ['decision_side', 'decision_direction', 'trend_direction', 'trend_model',
              'dir_score', 'trend_state', 'trend_state_label', 'trend_state_reason',
              'structure_direction', 'structure_score', 'structure_confirm', 'structure_evidence',
              'rps_accel', 'burst_score', 'burst_coverage', 'phase', 'phase_reason', 'phase_age', 'state_v2']
    for row in records:
        decision = by_code.get(row['ts_code'])
        if decision:
            row.update({key: decision.get(key) for key in fields})
            row['phase_match'] = row.get('direction') == decision['decision_side']
    return records
