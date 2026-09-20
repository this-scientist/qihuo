# -*- coding: utf-8 -*-
"""Unified T0-T5 trend state classifier for directional commodity decisions."""
from __future__ import annotations

import math


STATE_LABELS = {
    "T0": "T0 无趋势",
    "T1": "T1 趋势酝酿",
    "T2": "T2 趋势启动",
    "T3": "T3 趋势加速",
    "T4": "T4 趋势延续",
    "T5": "T5 趋势衰竭",
}


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _num(value, default=0.0) -> float:
    return float(value) if _finite(value) else default


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"


def _side_sign(side: str | None) -> int:
    return 1 if side == "long" else -1 if side == "short" else 0


def _directional_rps(row: dict, sign: int) -> float:
    if _finite(row.get("directional_rps20")):
        return _num(row.get("directional_rps20"))
    rps = _num(row.get("rps20"), 50.0)
    return rps if sign >= 0 else 100.0 - rps


def _directional_rps_prev5(row: dict, sign: int) -> float:
    value = row.get("rps20_prev5")
    if not _finite(value):
        return _directional_rps(row, sign)
    value = _num(value)
    return value if sign >= 0 else 100.0 - value


def _di_gap(row: dict, sign: int) -> float:
    if not sign:
        return 0.0
    return sign * (_num(row.get("plus_di")) - _num(row.get("minus_di")))


def _oi_aligned(row: dict, sign: int) -> bool:
    return sign and _num(row.get("oi_change5")) > 0 and sign * _num(row.get("return5")) > 0


def _speed_level(row: dict, sign: int) -> str:
    rps_now = _directional_rps(row, sign)
    rps_delta = rps_now - _directional_rps_prev5(row, sign)
    adx_slope = _num(row.get("adx_slope"))
    if rps_delta >= 15 or adx_slope >= 5:
        return "强"
    if rps_delta >= 6 or adx_slope >= 2:
        return "中"
    if rps_delta <= -8 or adx_slope <= -3:
        return "转弱"
    return "弱"


def _accel_level(row: dict, sign: int) -> str:
    positive = 0
    negative = 0
    rps_delta = _directional_rps(row, sign) - _directional_rps_prev5(row, sign)
    for ok in [
        rps_delta >= 10,
        _num(row.get("adx_slope")) >= 3,
        _num(row.get("atr_change5")) > 0 or _truthy(row.get("signal_atr_expansion")),
        _oi_aligned(row, sign),
        _num(row.get("volume_ratio"), 1.0) >= 1.5,
    ]:
        positive += 1 if ok else 0
    for ok in [
        rps_delta <= -8,
        _num(row.get("adx_slope")) <= -3,
        _num(row.get("oi_change5")) < -1 and sign * _num(row.get("return5")) > 0,
    ]:
        negative += 1 if ok else 0
    if positive >= 3:
        return "增强"
    if negative >= 2:
        return "减弱"
    return "平稳"


def _score_for_state(state: str, start_score: float, rps: float, adx: float) -> float:
    base = {
        "T0": 15.0,
        "T1": 60.0,
        "T2": 78.0,
        "T3": 90.0,
        "T4": 72.0,
        "T5": 38.0,
    }[state]
    if state in {"T1", "T2", "T3"}:
        base = max(base, min(100.0, start_score))
    if state in {"T3", "T4"}:
        base = max(base, min(100.0, (rps + min(adx, 45.0) / 45.0 * 100.0) / 2.0))
    return round(base, 2)


def classify_trend_state(row: dict, side: str | None, state_v2: str | None, start_score: float | int | None) -> dict:
    """Classify a decision row into T0-T5 using existing reliable indicators.

    This first version deliberately avoids pretending to use unavailable fields such
    as bid/ask, inventory, or IV rank. It converts the current directional evidence
    into a stable lifecycle state that UI and option gating can share.
    """
    sign = _side_sign(side)
    phase = row.get("phase")
    start = _num(start_score)
    rps = _directional_rps(row, sign)
    adx = _num(row.get("adx"))
    adx_slope = _num(row.get("adx_slope"))
    di_gap = _di_gap(row, sign)
    speed = _speed_level(row, sign)
    accel = _accel_level(row, sign)
    overextended = _truthy(row.get("overextended")) or phase == "过度延伸"
    weakening = phase == "趋势减弱" or state_v2 == "EXHAUST"
    breakout = _truthy(row.get("technical_start")) or _truthy(row.get("signal_base_breakout")) or phase == "趋势启动"
    accelerating = (
        accel == "增强"
        and rps >= 85
        and adx >= 25
        and (adx_slope >= 4 or _truthy(row.get("signal_atr_expansion")) or _num(row.get("atr_change5")) > 8)
        and _oi_aligned(row, sign)
    )

    if not sign or state_v2 == "WAIT" or (state_v2 is None and abs(_num(row.get("dir_score"))) < 20):
        state, transition, gate = "T0", "等待", "BLOCK"
        reason = "多空方向优势不足，维持等待。"
    elif overextended or weakening:
        state, transition, gate = "T5", "T4→T5", "BLOCK"
        reason = "趋势仍在但出现过度延伸、ADX/OI/价格推进衰减或旧趋势走弱，不再推荐新开买方仓。"
    elif accelerating:
        state, transition, gate = "T3", "T2→T3", "ALLOW"
        reason = "RPS、ADX、ATR/量能与增仓同向加速，进入买方期权 Gamma 爆发区。"
    elif state_v2 == "START" or (breakout and start >= 70 and adx >= 20 and di_gap > 0):
        state, transition, gate = "T2", "T1→T2", "ALLOW"
        reason = "关键位突破、ADX/DI确认且启动证据足够，新趋势正式形成。"
    elif state_v2 == "TREND" or phase in {"持续趋势", "中短期强势"} or _truthy(row.get("confirmed")):
        state, transition, gate = "T4", "T3→T4", "CONDITIONAL"
        reason = "趋势成熟并仍保持同向结构，适合持有或等待回调后的二次启动。"
    elif state_v2 == "PREPARE" or phase == "方向形成" or start >= 50 or (rps >= 60 and adx_slope > 0 and di_gap > 0):
        state, transition, gate = "T1", "T0→T1", "WATCH"
        reason = "平衡正在被打破，RPS/ADX/DI/OI已有酝酿迹象，但尚未完成正式启动。"
    else:
        state, transition, gate = "T0", "等待", "BLOCK"
        reason = "缺少足够的方向、启动或趋势延续证据。"

    return {
        "trend_state": state,
        "trend_state_label": STATE_LABELS[state],
        "trend_state_score": _score_for_state(state, start, rps, adx),
        "trend_transition": transition,
        "trend_state_reason": reason,
        "trend_speed_level": speed,
        "trend_accel_level": accel,
        "trend_option_gate": gate,
    }
