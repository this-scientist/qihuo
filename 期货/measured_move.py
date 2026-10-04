"""Measured Move 检测模块 — 基于 Al Brooks 价格行为学。

Measured Move 是一个 ABC 三段走法，第三段和第一段大致等长：
  Leg 1 (A→B): 起始趋势段，定义投射距离
  Leg 2 (B→C): 回调段，回调幅度应小于 Leg 1 的 62%
  Leg 3 (C→D): 延续段，目标 D = C ± (B - A)

前提条件（Brooks 原则）：
  - 必须处于趋势中（不在震荡区间内使用）
  - Leg 1 必须有足够趋势 K 线（min_leg1_bars）
  - 回调深度 < 62%
  - C 必须形成更高的低点（多头）或更低的高点（空头）
  - Leg 3 必须已经启动（当前价格已越过 C 点）
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd


@dataclass
class SwingPoint:
    index: int
    date: str
    price: float
    kind: str  # 'high' | 'low'


@dataclass
class MeasuredMove:
    direction: str  # 'long' | 'short'
    leg1_start_index: int
    leg1_end_index: int
    leg1_start_date: str
    leg1_end_date: str
    leg1_start_price: float
    leg1_end_price: float
    pullback_end_index: int
    pullback_end_date: str
    pullback_end_price: float
    pullback_depth_pct: float
    target_price: float
    leg3_progress_pct: float
    leg3_current_price: float


def _clean_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    required = {'trade_date', 'open', 'high', 'low', 'close'}
    if not required.issubset(df.columns):
        return pd.DataFrame(columns=list(required))
    data = df.loc[:, sorted(required)].copy()
    for field in ['open', 'high', 'low', 'close']:
        data[field] = pd.to_numeric(data[field], errors='coerce')
    data['trade_date'] = data['trade_date'].astype(str)
    return data.dropna(subset=['open', 'high', 'low', 'close']).sort_values('trade_date').reset_index(drop=True)


def find_swings(df: pd.DataFrame, pivot_strength: int = 2) -> list[SwingPoint]:
    """用分形枢轴点寻找 swing high / swing low。

    swing high: 一根 K 线的最高价高于左右各 pivot_strength 根 K 线的最高价。
    swing low: 对称定义。
    连续同类型的枢轴点只保留最极端的一个。
    """
    if len(df) < pivot_strength * 2 + 1:
        return []
    highs = df['high'].values
    lows = df['low'].values
    dates = df['trade_date'].values
    raw: list[SwingPoint] = []
    for i in range(pivot_strength, len(df) - pivot_strength):
        is_high = all(
            highs[i] > highs[i + j]
            for j in range(-pivot_strength, pivot_strength + 1)
            if j != 0
        )
        is_low = all(
            lows[i] < lows[i + j]
            for j in range(-pivot_strength, pivot_strength + 1)
            if j != 0
        )
        if is_high:
            raw.append(SwingPoint(i, str(dates[i]), float(highs[i]), 'high'))
        elif is_low:
            raw.append(SwingPoint(i, str(dates[i]), float(lows[i]), 'low'))
    # 合并连续同类型枢轴：只保留最极端的一个
    merged: list[SwingPoint] = []
    for pt in raw:
        if merged and merged[-1].kind == pt.kind:
            if pt.kind == 'high' and pt.price > merged[-1].price:
                merged[-1] = pt
            elif pt.kind == 'low' and pt.price < merged[-1].price:
                merged[-1] = pt
        else:
            merged.append(pt)
    return merged


def detect_measured_moves(
    df: pd.DataFrame,
    pivot_strength: int = 2,
    min_leg1_bars: int = 3,
    max_pullback_pct: float = 62.0,
    max_leg3_progress_pct: float = 100.0,
    max_pullback_age_bars: int = 40,
) -> list[MeasuredMove]:
    """检测 K 线数据中的 measured move 模式。

    返回按时间倒序排列的 MeasuredMove 列表，每个方向只保留最近一个。
    只保留当前活跃的形态：回调结束（C 点）距今不超过 max_pullback_age_bars 根 K 线。
    """
    data = _clean_ohlc(df)
    if len(data) < pivot_strength * 2 + 5:
        return []
    swings = find_swings(data, pivot_strength)
    if len(swings) < 3:
        return []
    close_prices = data['close'].values
    current_close = float(close_prices[-1])
    moves: list[MeasuredMove] = []

    for i in range(len(swings) - 2):
        a, b, c = swings[i], swings[i + 1], swings[i + 2]

        # 时效性：回调结束（C 点）必须足够新，旧形态已经失效
        if len(data) - 1 - c.index > max_pullback_age_bars:
            continue

        # 多头 measured move: low → high → low（更高的低点）
        if a.kind == 'low' and b.kind == 'high' and c.kind == 'low':
            leg1 = b.price - a.price
            if leg1 <= 0 or b.index - a.index < min_leg1_bars:
                continue
            if c.price <= a.price:  # C 必须高于 A（更高的低点）
                continue
            pullback = b.price - c.price
            depth_pct = pullback / leg1 * 100
            if depth_pct > max_pullback_pct:
                continue
            target = c.price + leg1
            # Leg 3 必须已启动：当前价格高于 C
            leg3_current = current_close - c.price
            if leg3_current <= 0:
                continue
            leg3_progress = leg3_current / leg1 * 100
            if leg3_progress > max_leg3_progress_pct:
                continue
            moves.append(MeasuredMove(
                direction='long',
                leg1_start_index=a.index, leg1_end_index=b.index,
                leg1_start_date=a.date, leg1_end_date=b.date,
                leg1_start_price=round(a.price, 4),
                leg1_end_price=round(b.price, 4),
                pullback_end_index=c.index, pullback_end_date=c.date,
                pullback_end_price=round(c.price, 4),
                pullback_depth_pct=round(depth_pct, 1),
                target_price=round(target, 4),
                leg3_progress_pct=round(leg3_progress, 1),
                leg3_current_price=round(current_close, 4),
            ))

        # 空头 measured move: high → low → high（更低的高点）
        elif a.kind == 'high' and b.kind == 'low' and c.kind == 'high':
            leg1 = a.price - b.price
            if leg1 <= 0 or b.index - a.index < min_leg1_bars:
                continue
            if c.price >= a.price:  # C 必须低于 A（更低的高点）
                continue
            pullback = c.price - b.price
            depth_pct = pullback / leg1 * 100
            if depth_pct > max_pullback_pct:
                continue
            target = c.price - leg1
            leg3_current = c.price - current_close
            if leg3_current <= 0:
                continue
            leg3_progress = leg3_current / leg1 * 100
            if leg3_progress > max_leg3_progress_pct:
                continue
            moves.append(MeasuredMove(
                direction='short',
                leg1_start_index=a.index, leg1_end_index=b.index,
                leg1_start_date=a.date, leg1_end_date=b.date,
                leg1_start_price=round(a.price, 4),
                leg1_end_price=round(b.price, 4),
                pullback_end_index=c.index, pullback_end_date=c.date,
                pullback_end_price=round(c.price, 4),
                pullback_depth_pct=round(depth_pct, 1),
                target_price=round(target, 4),
                leg3_progress_pct=round(leg3_progress, 1),
                leg3_current_price=round(current_close, 4),
            ))

    # 按回调结束位置倒序，每个方向只保留最近一个
    moves.sort(key=lambda m: m.pullback_end_index, reverse=True)
    seen: set[str] = set()
    filtered: list[MeasuredMove] = []
    for move in moves:
        if move.direction not in seen:
            filtered.append(move)
            seen.add(move.direction)
    return filtered


def measured_move_summary(df: pd.DataFrame) -> dict:
    """返回 measured move 检测结果，供 payload 序列化。"""
    moves = detect_measured_moves(df)
    if not moves:
        return {'has_move': False, 'moves': []}
    return {'has_move': True, 'moves': [asdict(m) for m in moves]}
