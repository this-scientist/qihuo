"""Canonical EMA20 strength, distance, and trade-actionability assessment."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Ema20Settings:
    medium_slope_atr: float = .25
    strong_slope_atr: float = .75
    actionable_distance_atr: float = 2
    max_distance_atr: float = 3


LABELS = {
    'actionable': '可做',
    'wait_pullback': '等待回踩',
    'do_not_chase': '不可追',
    'not_actionable': '不可做',
}


def _finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def ema20_assessment(row, side, quality_ok=True, quality_reason=None, settings=None):
    """Return a symmetric EMA20 assessment for a proposed long or short side."""
    settings = settings or Ema20Settings()
    slope = row.get('ema20_slope5_atr')
    distance = row.get('ema20_distance_atr')
    missing = not all(_finite(row.get(key)) for key in ['ema20', 'ema20_slope5_atr', 'ema20_distance_atr'])
    sign = 1 if side == 'long' else -1 if side == 'short' else 0
    raw_slope = float(slope) if _finite(slope) else None
    raw_distance = float(distance) if _finite(distance) else None
    directional_slope = sign * raw_slope if sign and raw_slope is not None else None
    directional_distance = sign * raw_distance if sign and raw_distance is not None else None
    magnitude = abs(raw_slope) if raw_slope is not None else None
    strength = ('unavailable' if magnitude is None else 'strong' if magnitude >= settings.strong_slope_atr
                else 'medium' if magnitude >= settings.medium_slope_atr else 'weak')
    direction = ('unavailable' if raw_slope is None else 'flat' if strength == 'weak'
                 else 'rising' if raw_slope > 0 else 'falling')
    reasons = []
    if missing:
        reasons.append('EMA20或ATR数据不足')
    elif not sign:
        reasons.append('当前没有明确多空方向')
    else:
        if directional_slope < settings.medium_slope_atr:
            reasons.append('EMA20趋势偏弱或与交易方向相反')
        if directional_distance < 0:
            reasons.append('当前价格位于EMA20错误一侧')
        if not quality_ok:
            reasons.append(quality_reason or '其他必要质量条件未通过')

    if reasons:
        status = 'not_actionable'
    elif directional_distance > settings.max_distance_atr:
        status = 'do_not_chase'
        reasons.append(f'价格顺方向偏离EMA20超过{settings.max_distance_atr:g} ATR')
    elif directional_distance > settings.actionable_distance_atr:
        status = 'wait_pullback'
        reasons.append(f'价格顺方向偏离EMA20超过{settings.actionable_distance_atr:g} ATR')
    else:
        status = 'actionable'
        reasons.append('EMA20方向、强度和价格距离均合格')

    return {
        'ema20_direction': direction,
        'ema20_strength': strength,
        'ema20_slope5_atr': raw_slope,
        'ema20_distance_atr': raw_distance,
        'directional_ema20_slope5_atr': directional_slope,
        'directional_ema20_distance_atr': directional_distance,
        'ema20_actionability': status,
        'ema20_actionability_label': LABELS[status],
        'ema20_actionability_reasons': reasons,
    }
