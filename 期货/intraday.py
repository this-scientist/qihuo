# -*- coding: utf-8 -*-
"""盘中可执行性：把前一收盘日的方向判断与支撑压力位，叠加实时价，判断现在这个位置值不值得动手。

只读旁路，不写入 payload、MySQL 或快照，收盘口径的可复现性不受影响。
所有分值都是规则分：既不是胜率，也没有经过回测，只用来排序和筛掉明显不该动手的位置。

价位口径：payload 里 today_* 属于已经过去的那个交易日，当前盘中要用 tomorrow_*，
即由最后收盘日 K 线推出的次日价位（tomorrow_support / resistance / breakout / reversal）。
"""
from realtime import snapshot

EXEC_WEIGHT_POSITION = 0.6
EXEC_WEIGHT_DIRECTION = 0.4

# 日线状态对应的「方向质量」：刚启动最优，等待/过度延伸最差
STATE_SCORES = {'START': 100, 'TREND': 85, 'PREPARE': 60, 'EXHAUST': 30, 'WAIT': 20}
UNKNOWN_DIRECTION_SCORE = 40

# 支撑压力箱体窄于价格的这个比例时，位置分没有意义（当日近乎十字星）
MIN_BOX_RATIO = 0.0005


def position_band(progress):
    """按「顺方向推进度」给位置分。progress = 顺方向距离 / 上一交易日振幅，0 在近端价位、1 在远端价位。"""
    if progress is None:
        return dict(key='unknown', label='无价位', score=None)
    if progress < -0.5:
        return dict(key='broken', label='反向破位', score=8)
    if progress < 0:
        return dict(key='crossed', label='逆势越界', score=30)
    if progress <= 0.3:
        return dict(key='edge', label='顺向边缘', score=90)
    if progress < 0.7:
        return dict(key='middle', label='区间中部', score=50)
    if progress <= 1.0:
        return dict(key='far', label='接近目标位', score=35)
    if progress <= 1.3:
        return dict(key='broke', label='刚破目标位', score=75)
    return dict(key='runaway', label='远离目标位', score=25)


def direction_quality(row):
    """日线方向质量：无方向直接归零，否则按趋势状态取值。"""
    side = row.get('decision_side')
    if side not in ('long', 'short'):
        return dict(side=side or 'neutral', score=0, label='日线无方向')
    state = row.get('state_v2')
    return dict(side=side, score=STATE_SCORES.get(state, UNKNOWN_DIRECTION_SCORE),
                label=state or '状态未知')


def price_scale(row):
    """把复权口径的日线价位换到真实合约口径。

    日线价位来自复权连续（close），盘中报价是真实合约价（raw_close）：
    两者差一个复权因子，68 个品种里有 60 个因子明显偏离 1。
    不换算的话整个支撑压力箱体会被等比放大，推进度会算出 -11 这种荒谬值。
    因子缺失时返回 None，宁可不打分也不给出错误的位置分。
    """
    close, raw = row.get('close'), row.get('raw_close')
    if not close or not raw or close <= 0 or raw <= 0:
        return None
    return raw / close


def progress_of(side, last, support, resistance):
    """顺方向推进度；价位缺失或箱体过窄时返回 None。"""
    if side not in ('long', 'short') or last is None or support is None or resistance is None:
        return None
    width = resistance - support
    if not width or not last or abs(width) / abs(last) < MIN_BOX_RATIO:
        return None
    distance = (last - support) if side == 'long' else (resistance - last)
    return distance / width


def evaluate(row, quote):
    """把一条日线决策行与它的实时报价合成可执行性判断；缺报价或缺价位时仍返回条目，只是分值为空。"""
    side = row.get('decision_side') if row.get('decision_side') in ('long', 'short') else 'neutral'
    scale = price_scale(row)
    levels = {key: (row.get(f'tomorrow_{key}') * scale if scale is not None and row.get(f'tomorrow_{key}') is not None else None)
              for key in ('support', 'resistance', 'breakout', 'reversal')}
    last = quote.get('last') if quote else None
    progress = progress_of(side, last, levels['support'], levels['resistance'])
    band = position_band(progress)
    direction = direction_quality(row)
    score = None
    if band['score'] is not None and direction['score'] is not None:
        score = round(EXEC_WEIGHT_POSITION * band['score'] + EXEC_WEIGHT_DIRECTION * direction['score'])
    return dict(ts_code=row.get('ts_code'), main_code=row.get('main_code'), name=row.get('name'),
                sector=row.get('sector'), side=side, state_v2=row.get('state_v2'),
                dir_score=row.get('dir_score'), support=levels['support'], resistance=levels['resistance'],
                breakout=levels['breakout'], reversal=levels['reversal'], price_scale=scale,
                last=last, bid=quote.get('bid') if quote else None, ask=quote.get('ask') if quote else None,
                pre_settle=quote.get('pre_settle') if quote else None,
                change_pct=quote.get('change_pct') if quote else None,
                spread=quote.get('spread') if quote else None,
                quote_time=quote.get('time') if quote else None,
                quote_age=quote.get('age_seconds') if quote else None,
                progress=None if progress is None else round(progress, 4),
                stance=band['key'], stance_label=band['label'], position_score=band['score'],
                direction_label=direction['label'], direction_score=direction['score'],
                exec_score=score)


def rank(rows, quotes):
    """按可执行性降序排列；无分值的排在最后，缺失值不会当成 0 混进前列。"""
    entries = [evaluate(row, quotes.get(row.get('main_code'))) for row in rows]
    scored = [item for item in entries if item['exec_score'] is not None]
    unscored = [item for item in entries if item['exec_score'] is None]
    scored.sort(key=lambda item: (-item['exec_score'], -(item['dir_score'] or 0), item['ts_code'] or ''))
    return scored + unscored


def snapshot_ranking(rows, codes, **kwargs):
    """取一次报价快照并直接产出排名，供服务端一个请求内完成。"""
    quotes = snapshot(codes, **kwargs)
    return dict(quotes=quotes['quotes'], error=quotes['error'], cached=quotes['cached'],
                execution=rank(rows, quotes['quotes']))
