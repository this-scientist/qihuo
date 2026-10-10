# -*- coding: utf-8 -*-
"""Brooks-style market-cycle weak labels for futures daily bars."""
from __future__ import annotations

import math

import pandas as pd


CYCLE_LABELS = {
    "TRADING_RANGE": "交易区间",
    "BREAKOUT_ATTEMPT": "突破尝试",
    "BREAKOUT_SPIKE": "突破尖峰",
    "TIGHT_CHANNEL": "紧密通道",
    "BROAD_CHANNEL": "宽通道",
    "EXHAUSTION": "趋势末端",
}


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    data = df.sort_values("trade_date").reset_index(drop=True).copy()
    close = pd.to_numeric(data["close"], errors="coerce")
    high = pd.to_numeric(data["high"], errors="coerce")
    low = pd.to_numeric(data["low"], errors="coerce")
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    data["atr14"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=3).mean()
    data["ema20"] = close.ewm(span=20, adjust=False, min_periods=3).mean()
    data["close_above_ema20"] = (close > data["ema20"]).astype(int)
    data["ema20_slope5_atr"] = (data["ema20"] - data["ema20"].shift(5)) / data["atr14"]
    data["ema20_slope10_atr"] = (data["ema20"] - data["ema20"].shift(10)) / data["atr14"]
    data["distance_ema20_atr"] = (close - data["ema20"]) / data["atr14"]
    data["ema20_cross"] = (data["close_above_ema20"] != data["close_above_ema20"].shift(1)).astype(int)
    data["ema20_cross_count20"] = data["ema20_cross"].rolling(20, min_periods=3).sum()
    side = data["close_above_ema20"].replace({0: -1})
    run_id = side.ne(side.shift()).cumsum()
    data["bars_on_ema20_side"] = side.groupby(run_id).cumcount() + 1
    data["bars_above_ema20"] = data["bars_on_ema20_side"].where(data["close_above_ema20"] == 1, 0)
    data["bars_below_ema20"] = data["bars_on_ema20_side"].where(data["close_above_ema20"] == 0, 0)
    data["touched_ema20"] = ((low <= data["ema20"]) & (high >= data["ema20"])).astype(int)
    data["ema20_support_reaction"] = (
        (data["touched_ema20"] == 1) & (close > data["ema20"]) & (close > pd.to_numeric(data["open"], errors="coerce"))
    ).astype(int)
    data["ema20_resistance_reaction"] = (
        (data["touched_ema20"] == 1) & (close < data["ema20"]) & (close < pd.to_numeric(data["open"], errors="coerce"))
    ).astype(int)
    data["body_atr"] = (close - pd.to_numeric(data["open"], errors="coerce")).abs() / data["atr14"]
    data["range_atr"] = (high - low).abs() / data["atr14"]
    data["close_position"] = (close - low) / (high - low).replace(0, pd.NA)
    data["gap_atr"] = (pd.to_numeric(data["open"], errors="coerce") - prev_close) / data["atr14"]
    return data


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _num(row, key, default=0.0) -> float:
    value = row.get(key)
    return float(value) if _finite(value) else default


def signal_bar_for_row(row: pd.Series) -> str:
    open_ = _num(row, "open")
    close = _num(row, "close")
    high = _num(row, "high")
    low = _num(row, "low")
    atr = max(_num(row, "atr14"), 1e-9)
    body_atr = abs(close - open_) / atr
    close_pos = (close - low) / (high - low) if high > low else 0.5
    body = abs(close - open_)
    upper_wick = high - max(open_, close)
    lower_wick = min(open_, close) - low
    if close < open_ and close_pos <= 0.25 and upper_wick >= body * 0.25:
        return "BEAR_REVERSAL_BAR"
    if close > open_ and close_pos >= 0.75 and lower_wick >= body * 0.25:
        return "BULL_REVERSAL_BAR"
    if body_atr >= 1.0 and close > open_ and close_pos >= 0.7:
        return "BULL_TREND_BAR"
    if body_atr >= 1.0 and close < open_ and close_pos <= 0.3:
        return "BEAR_TREND_BAR"
    if _finite(row.get("gap_atr")) and abs(float(row.get("gap_atr"))) >= 0.8:
        return "GAP_BAR"
    return "OVERLAP_BAR"


def classify_cycle_row(df: pd.DataFrame, idx: int) -> dict:
    data = add_indicators(df) if "ema20" not in df else df.reset_index(drop=True)
    row = data.iloc[idx]
    close = _num(row, "close")
    ema = _num(row, "ema20", close)
    slope = _num(row, "ema20_slope5_atr")
    distance = _num(row, "distance_ema20_atr")
    atr = max(_num(row, "atr14"), 1e-9)
    lookback = data.iloc[max(0, idx - 5):idx]
    prior = data.iloc[max(0, idx - 20):idx]
    recent_close = pd.to_numeric(data.iloc[max(0, idx - 5):idx + 1]["close"], errors="coerce")
    recent_up = len(recent_close) >= 4 and recent_close.is_monotonic_increasing
    recent_down = len(recent_close) >= 4 and recent_close.is_monotonic_decreasing
    direction = "long" if (slope >= 0.25 and close >= ema) or recent_up else "short" if (slope <= -0.25 and close <= ema) or recent_down else "neutral"
    signal = signal_bar_for_row(row)
    phase = "TRADING_RANGE"
    if len(prior) >= 3:
        prior_high = pd.to_numeric(prior["high"], errors="coerce").max()
        prior_low = pd.to_numeric(prior["low"], errors="coerce").min()
        long_break = close > prior_high and signal in {"BULL_TREND_BAR", "BULL_REVERSAL_BAR", "GAP_BAR"}
        short_break = close < prior_low and signal in {"BEAR_TREND_BAR", "BEAR_REVERSAL_BAR", "GAP_BAR"}
        if long_break or short_break:
            phase = "BREAKOUT_SPIKE"
            direction = "long" if long_break else "short"
    if phase == "TRADING_RANGE" and direction != "neutral" and len(lookback) >= 3:
        same_side = ((pd.to_numeric(lookback["close"], errors="coerce") - pd.to_numeric(lookback.get("ema20", ema), errors="coerce")) * (1 if direction == "long" else -1) > 0).mean()
        overlap = (pd.to_numeric(lookback["high"], errors="coerce").shift(1) >= pd.to_numeric(lookback["low"], errors="coerce")).mean()
        closes = pd.to_numeric(lookback["close"], errors="coerce")
        monotonic = closes.is_monotonic_increasing if direction == "long" else closes.is_monotonic_decreasing
        if (abs(slope) >= 0.75 or monotonic) and abs(distance) <= 3.5 and (same_side >= 0.8 or monotonic) and overlap >= 0.8:
            phase = "TIGHT_CHANNEL"
        elif abs(slope) >= 0.25:
            phase = "BROAD_CHANNEL"
    if phase == "TRADING_RANGE" and direction != "neutral" and _num(row, "body_atr") >= 0.7:
        phase = "BREAKOUT_ATTEMPT"
    if phase in {"TIGHT_CHANNEL", "BROAD_CHANNEL"} and abs(distance) >= 3.0 and _num(row, "body_atr") >= 1.2:
        phase = "EXHAUSTION"
    return {
        "market_cycle_phase": phase,
        "market_cycle_label": CYCLE_LABELS[phase],
        "direction": direction,
        "signal_bar": signal,
        "ema20": _num(row, "ema20", None),
        "atr14": atr,
        "ema20_slope5_atr": slope,
        "ema20_slope10_atr": _num(row, "ema20_slope10_atr"),
        "distance_ema20_atr": distance,
        "close_above_ema20": int(_num(row, "close_above_ema20")),
        "ema20_cross_count20": _num(row, "ema20_cross_count20"),
        "bars_above_ema20": _num(row, "bars_above_ema20"),
        "bars_below_ema20": _num(row, "bars_below_ema20"),
        "touched_ema20": int(_num(row, "touched_ema20")),
        "ema20_support_reaction": int(_num(row, "ema20_support_reaction")),
        "ema20_resistance_reaction": int(_num(row, "ema20_resistance_reaction")),
    }
