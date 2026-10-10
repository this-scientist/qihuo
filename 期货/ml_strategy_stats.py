# -*- coding: utf-8 -*-
"""Build first-pass Brooks-cycle strategy statistics from futures daily data."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import pandas as pd

from collector import atomic_csv, atomic_json
from ml_cycle_labels import add_indicators, classify_cycle_row


REAL_CONTRACT = r"^[A-Za-z]+\d{3,4}\.[A-Z]+$"
DISPLAY_EXCHANGE = {"SHFE": "SHF", "CZCE": "ZCE", "GFEX": "GFE"}
STRATEGY_BY_PHASE = {
    "TRADING_RANGE": "RANGE_EDGE_OR_SKIP",
    "BREAKOUT_ATTEMPT": "WAIT_CONFIRMATION",
    "BREAKOUT_SPIKE": "TREND_BREAKOUT",
    "TIGHT_CHANNEL": "TREND_SHALLOW_PULLBACK",
    "BROAD_CHANNEL": "WITH_TREND_PULLBACK",
    "EXHAUSTION": "NO_NEW_POSITION",
}


def strategy_for_sample(cycle: dict) -> str:
    phase = cycle["market_cycle_phase"]
    direction = cycle["direction"]
    distance_ema20_atr = float(cycle["distance_ema20_atr"])
    touched_ema20 = int(cycle.get("touched_ema20", 0))
    support = int(cycle.get("ema20_support_reaction", 0))
    resistance = int(cycle.get("ema20_resistance_reaction", 0))
    cross_count = float(cycle.get("ema20_cross_count20", 0.0))
    trend_side_bars = float(cycle.get("bars_above_ema20" if direction == "long" else "bars_below_ema20", 0.0))
    same_side = (direction == "long" and distance_ema20_atr > 0) or (direction == "short" and distance_ema20_atr < 0)
    ema_reaction = support if direction == "long" else resistance
    if phase == "TIGHT_CHANNEL":
        if direction in {"long", "short"} and touched_ema20 and ema_reaction:
            return "TIGHT_CHANNEL_EMA20_REACTION"
        if direction in {"long", "short"} and abs(distance_ema20_atr) <= 1.2 and same_side:
            return "TIGHT_CHANNEL_EMA20_SHALLOW_PULLBACK"
        if abs(distance_ema20_atr) >= 2.5:
            return "TIGHT_CHANNEL_DO_NOT_CHASE"
        if trend_side_bars >= 5 and same_side:
            return "TIGHT_CHANNEL_EMA20_TREND_FOLLOW"
        return "TIGHT_CHANNEL_TREND_FOLLOW"
    if phase == "BROAD_CHANNEL":
        if cross_count >= 6:
            return "BROAD_CHANNEL_EMA20_CHOP_WAIT"
        if direction in {"long", "short"} and touched_ema20 and ema_reaction:
            return "BROAD_CHANNEL_EMA20_REACTION"
        if abs(distance_ema20_atr) <= 1.0 and same_side:
            return "BROAD_CHANNEL_WITH_TREND_EMA20_PULLBACK"
        return "BROAD_CHANNEL_MIDLINE_WAIT"
    return STRATEGY_BY_PHASE[phase]


def load_ml_daily(root: Path) -> pd.DataFrame:
    frames = []
    for path in sorted((root / "ml" / "raw" / "fut_daily").glob("*/*.csv")):
        df = pd.read_csv(path, dtype={"ts_code": str, "trade_date": str})
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    data = pd.concat(frames, ignore_index=True, sort=False)
    data = data[data["ts_code"].astype(str).str.match(REAL_CONTRACT)].copy()
    data["fut_code"] = data["ts_code"].str.extract(r"^([A-Za-z]+)\d", expand=False)
    for col in ["open", "high", "low", "close", "settle", "pre_close", "pre_settle", "vol", "amount", "oi", "oi_chg"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data[data.get("price_valid", True).astype(str).str.lower().isin(["true", "1"])].copy()
    return data.sort_values(["exchange", "fut_code", "trade_date", "vol", "oi", "ts_code"])


def select_liquid_product_series(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data
    ranked = data.sort_values(["exchange", "fut_code", "trade_date", "oi", "vol", "ts_code"], ascending=[True, True, True, False, False, True])
    picked = ranked.groupby(["exchange", "fut_code", "trade_date"], as_index=False).head(1).copy()
    picked["product_code"] = picked["fut_code"] + "." + picked["exchange"]
    picked["product_code"] = picked["product_code"].replace({f".{src}": f".{dst}" for src, dst in DISPLAY_EXCHANGE.items()}, regex=True)
    return picked.sort_values(["product_code", "trade_date"]).reset_index(drop=True)


def _history_code_from_path(path: Path) -> str:
    code = path.stem
    return code.replace("_", ".")


def load_dashboard_history_series(root: Path) -> pd.DataFrame:
    candidates = [
        Path(root) / "updates" / "20260930" / "processed" / "history",
        Path(root) / "snapshots" / "20260930",
    ]
    snapshot_root = candidates[-1]
    if snapshot_root.exists():
        versions = sorted([path for path in snapshot_root.iterdir() if path.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
        candidates.extend(path / "processed" / "history" for path in versions)
    frames = []
    seen = set()
    for folder in candidates:
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.csv")):
            if path.name.endswith(".rolls.csv"):
                continue
            product_code = _history_code_from_path(path)
            if product_code in seen:
                continue
            df = pd.read_csv(path, dtype={"ts_code": str, "trade_date": str})
            if df.empty:
                continue
            df["product_code"] = product_code
            if "exchange" not in df:
                df["exchange"] = product_code.split(".")[-1]
            for col in ["open", "high", "low", "close", "settle", "pre_close", "pre_settle", "vol", "amount", "oi", "oi_chg"]:
                if col not in df:
                    df[col] = pd.NA
                df[col] = pd.to_numeric(df[col], errors="coerce")
            frames.append(df)
            seen.add(product_code)
        if frames:
            break
    if not frames:
        return pd.DataFrame()
    data = pd.concat(frames, ignore_index=True, sort=False)
    data["price_valid"] = data[["open", "high", "low", "close"]].gt(0).all(axis=1)
    return data[data["price_valid"]].sort_values(["product_code", "trade_date"]).reset_index(drop=True)


def load_market_daily(root: Path) -> pd.DataFrame:
    frames = []
    for path in sorted((root / "ml" / "raw" / "market_daily").glob("*/*.csv")):
        df = pd.read_csv(path, dtype={"ts_code": str, "trade_date": str})
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    data = pd.concat(frames, ignore_index=True, sort=False)
    for col in ["open", "high", "low", "close", "settle", "pre_close", "pre_settle", "vol", "amount", "oi", "oi_chg"]:
        if col not in data:
            data[col] = pd.NA
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data[data.get("price_valid", True).astype(str).str.lower().isin(["true", "1"])].copy()
    data["product_code"] = data["ts_code"].astype(str)
    return data.sort_values(["product_code", "trade_date"]).reset_index(drop=True)


def load_mixed_training_series(root: Path) -> pd.DataFrame:
    futures = load_dashboard_history_series(root)
    if futures.empty:
        futures = select_liquid_product_series(load_ml_daily(root))
    markets = load_market_daily(root)
    if futures.empty:
        return markets
    if markets.empty:
        return futures
    columns = sorted(set(futures.columns) | set(markets.columns))
    return pd.concat([futures.reindex(columns=columns), markets.reindex(columns=columns)], ignore_index=True, sort=False)


def _zscore(series: pd.Series, window: int) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    mean = numeric.rolling(window, min_periods=5).mean()
    std = numeric.rolling(window, min_periods=5).std()
    return (numeric - mean) / std.replace(0, pd.NA)


def _rolling_overlap_ratio(high: pd.Series, low: pd.Series, window: int) -> pd.Series:
    overlaps_prev = high.shift(1).ge(low) & low.shift(1).le(high)
    return overlaps_prev.astype(float).rolling(window, min_periods=5).mean()


def _rolling_failed_breakout_count(close: pd.Series, high: pd.Series, low: pd.Series, window: int = 20) -> pd.Series:
    prior_high = high.shift(1).rolling(window, min_periods=5).max()
    prior_low = low.shift(1).rolling(window, min_periods=5).min()
    broke_up = high > prior_high
    broke_down = low < prior_low
    failed_up = broke_up & close.le(prior_high)
    failed_down = broke_down & close.ge(prior_low)
    return (failed_up | failed_down).astype(float).rolling(window, min_periods=5).sum()


def _count_since_last_side_change(side: pd.Series) -> pd.Series:
    run_id = side.ne(side.shift()).cumsum()
    return side.groupby(run_id).cumcount() + 1


def _contract_month(ts_code: str) -> float | None:
    match = re.match(r"^[A-Za-z]+(\d{3,4})\.", str(ts_code))
    if not match:
        return None
    raw = match.group(1)
    if len(raw) == 3:
        year = 2020 + int(raw[0])
        month = int(raw[1:])
    else:
        year = 2000 + int(raw[:2])
        month = int(raw[2:])
    if month < 1 or month > 12:
        return None
    return year * 12 + month


def add_available_features(group: pd.DataFrame) -> pd.DataFrame:
    data = group.copy()
    open_ = pd.to_numeric(data["open"], errors="coerce")
    high = pd.to_numeric(data["high"], errors="coerce")
    low = pd.to_numeric(data["low"], errors="coerce")
    close = pd.to_numeric(data["close"], errors="coerce")
    settle = pd.to_numeric(data.get("settle"), errors="coerce")
    pre_close = pd.to_numeric(data.get("pre_close"), errors="coerce")
    pre_settle = pd.to_numeric(data.get("pre_settle"), errors="coerce")
    vol = pd.to_numeric(data.get("vol"), errors="coerce")
    amount = pd.to_numeric(data.get("amount"), errors="coerce")
    oi = pd.to_numeric(data.get("oi"), errors="coerce")
    oi_chg = pd.to_numeric(data.get("oi_chg"), errors="coerce")
    atr = pd.to_numeric(data.get("atr14"), errors="coerce")
    body = (close - open_).abs()
    close_pos = (close - low) / (high - low).replace(0, pd.NA)
    bull_trend_bar = (close > open_) & ((body / atr.replace(0, pd.NA)) >= 0.7) & (close_pos >= 0.65)
    bear_trend_bar = (close < open_) & ((body / atr.replace(0, pd.NA)) >= 0.7) & (close_pos <= 0.35)
    direction_side = pd.Series(0, index=data.index, dtype="int64")
    direction_side = direction_side.mask(close > data["ema20"], 1).mask(close < data["ema20"], -1)
    data["vol_zscore20"] = _zscore(vol, 20)
    data["amount_zscore20"] = _zscore(amount, 20)
    data["oi_chg_1"] = oi_chg.fillna(oi.diff())
    data["oi_chg_5"] = oi - oi.shift(5)
    data["oi_chg_pct_1"] = data["oi_chg_1"] / oi.shift(1).replace(0, pd.NA)
    data["oi_chg_pct_5"] = data["oi_chg_5"] / oi.shift(5).replace(0, pd.NA)
    data["settle_close_atr"] = (settle - close) / atr.replace(0, pd.NA)
    data["open_gap_preclose_atr"] = (pd.to_numeric(data["open"], errors="coerce") - pre_close) / atr.replace(0, pd.NA)
    data["open_gap_prepair_atr"] = (pd.to_numeric(data["open"], errors="coerce") - pre_settle) / atr.replace(0, pd.NA)
    data["close_vs_pre_settle_atr"] = (close - pre_settle) / atr.replace(0, pd.NA)
    data["higher_high_count10"] = high.gt(high.shift(1)).astype(float).rolling(10, min_periods=3).sum()
    data["higher_low_count10"] = low.gt(low.shift(1)).astype(float).rolling(10, min_periods=3).sum()
    data["lower_high_count10"] = high.lt(high.shift(1)).astype(float).rolling(10, min_periods=3).sum()
    data["lower_low_count10"] = low.lt(low.shift(1)).astype(float).rolling(10, min_periods=3).sum()
    data["bull_trend_bar_count10"] = bull_trend_bar.astype(float).rolling(10, min_periods=3).sum()
    data["bear_trend_bar_count10"] = bear_trend_bar.astype(float).rolling(10, min_periods=3).sum()
    data["trend_bar_count10"] = (bull_trend_bar | bear_trend_bar).astype(float).rolling(10, min_periods=3).sum()
    data["counter_trend_bar_ratio10"] = (
        ((direction_side.eq(1) & bear_trend_bar) | (direction_side.eq(-1) & bull_trend_bar)).astype(float)
        .rolling(10, min_periods=3)
        .mean()
    )
    data["overlap_ratio20"] = _rolling_overlap_ratio(high, low, 20)
    range_high20 = high.shift(1).rolling(20, min_periods=5).max()
    range_low20 = low.shift(1).rolling(20, min_periods=5).min()
    data["range_width_atr20"] = (range_high20 - range_low20) / atr.replace(0, pd.NA)
    data["range_position20"] = (close - range_low20) / (range_high20 - range_low20).replace(0, pd.NA)
    data["failed_breakout_count20"] = _rolling_failed_breakout_count(close, high, low, 20)
    breakout_up = close > range_high20
    breakout_down = close < range_low20
    data["breakout_close_back_inside"] = ((high > range_high20) & close.le(range_high20) | ((low < range_low20) & close.ge(range_low20))).astype(int)
    data["breakout_follow_through_2"] = (
        (breakout_up.shift(2) & close.gt(close.shift(2)) & close.shift(1).gt(close.shift(2)))
        | (breakout_down.shift(2) & close.lt(close.shift(2)) & close.shift(1).lt(close.shift(2)))
    ).astype(int)
    trend_side = direction_side.astype(float).replace(0, math.nan).ffill().fillna(0).astype(int)
    data["trend_side_bars_context"] = _count_since_last_side_change(trend_side)
    swing_high10 = high.shift(1).rolling(10, min_periods=3).max()
    swing_low10 = low.shift(1).rolling(10, min_periods=3).min()
    long_leg = (swing_high10 - swing_low10).where(close >= data["ema20"])
    short_leg = (swing_high10 - swing_low10).where(close < data["ema20"])
    data["leg1_size_atr10"] = (swing_high10 - swing_low10) / atr.replace(0, pd.NA)
    data["pullback_depth_atr10"] = ((swing_high10 - low).where(close >= data["ema20"], high - swing_low10)) / atr.replace(0, pd.NA)
    data["pullback_ratio10"] = (
        (data["pullback_depth_atr10"] * atr) / (long_leg.fillna(short_leg)).replace(0, pd.NA)
    )
    data["pullback_to_ema20"] = data["touched_ema20"]
    data["second_entry_proxy"] = (
        (data["pullback_to_ema20"].shift(1).eq(1) & ((close > high.shift(1)) | (close < low.shift(1))))
    ).astype(int)
    mm_base = range_high20 - range_low20
    mm_target_long = range_high20 + mm_base
    mm_target_short = range_low20 - mm_base
    mm_target = mm_target_long.where(close >= data["ema20"], mm_target_short)
    sign = pd.Series(1, index=data.index).where(close >= data["ema20"], -1)
    structure_stop = swing_low10.where(sign.eq(1), swing_high10)
    reward = sign * (mm_target - close)
    risk = sign * (close - structure_stop)
    data["measured_move_target_price"] = mm_target
    data["distance_to_mm_target_atr"] = reward / atr.replace(0, pd.NA)
    data["measured_move_rr"] = reward / risk.where(risk > 0).replace(0, pd.NA)
    data["mm_progress"] = ((close - range_high20) / mm_base).where(sign.eq(1), (range_low20 - close) / mm_base)
    data["ema20_stop_distance_atr"] = (close - data["ema20"]).abs() / atr.replace(0, pd.NA)
    data["structure_stop_distance_atr"] = risk / atr.replace(0, pd.NA)
    trade_month = pd.to_datetime(data["trade_date"], format="%Y%m%d", errors="coerce").dt.year * 12 + pd.to_datetime(data["trade_date"], format="%Y%m%d", errors="coerce").dt.month
    contract_month = data["ts_code"].map(_contract_month)
    data["months_to_contract"] = contract_month - trade_month
    data["is_near_contract_month"] = (data["months_to_contract"] <= 1).astype("Int64")
    return data


def _future_path(group: pd.DataFrame, idx: int, direction: str, horizon: int, target_atr=2.0, stop_atr=1.0) -> dict | None:
    if direction not in {"long", "short"}:
        return None
    if idx + 1 >= len(group):
        return None
    row = group.iloc[idx]
    atr = row.get("atr14")
    if not (pd.notna(atr) and math.isfinite(float(atr)) and float(atr) > 0):
        return None
    entry = group.iloc[idx + 1].open
    if not (pd.notna(entry) and math.isfinite(float(entry)) and float(entry) > 0):
        return None
    sign = 1 if direction == "long" else -1
    target = entry + sign * target_atr * float(atr)
    stop = entry - sign * stop_atr * float(atr)
    window = group.iloc[idx + 1: idx + 1 + horizon]
    if window.empty:
        return None
    hit_target_first = False
    hit_stop_first = False
    exit_price = window.iloc[-1].close
    for bar in window.itertuples():
        target_hit = bar.high >= target if direction == "long" else bar.low <= target
        stop_hit = bar.low <= stop if direction == "long" else bar.high >= stop
        if target_hit and stop_hit:
            hit_stop_first = True
            exit_price = stop
            break
        if target_hit:
            hit_target_first = True
            exit_price = target
            break
        if stop_hit:
            hit_stop_first = True
            exit_price = stop
            break
    favorable = ((window.high.max() - entry) if direction == "long" else (entry - window.low.min())) / float(atr)
    adverse = ((entry - window.low.min()) if direction == "long" else (window.high.max() - entry)) / float(atr)
    realized_r = sign * (exit_price - entry) / (stop_atr * float(atr))
    signal_close = float(row.close)
    gap_atr = (float(entry) - signal_close) / float(atr)
    return {
        "entry_open": float(entry),
        "target_price": float(target),
        "stop_price": float(stop),
        "hit_target_first": int(hit_target_first),
        "hit_stop_first": int(hit_stop_first),
        "mfe_atr": round(float(favorable), 4),
        "mae_atr": round(float(adverse), 4),
        "realized_r": round(float(realized_r), 4),
        "gap_atr": round(float(gap_atr), 4),
        "gap_with_trend": int(sign * gap_atr > 0),
    }


def build_strategy_dataset(root: Path, horizon=5, min_rows=40) -> pd.DataFrame:
    selected = load_mixed_training_series(root)
    rows = []
    for product, group in selected.groupby("product_code"):
        group = add_indicators(group).reset_index(drop=True)
        group = add_available_features(group).reset_index(drop=True)
        if len(group) < min_rows:
            continue
        for idx in range(25, len(group) - horizon):
            cycle = classify_cycle_row(group, idx)
            path = _future_path(group, idx, cycle["direction"], horizon)
            if path is None:
                continue
            row = group.iloc[idx]
            phase = cycle["market_cycle_phase"]
            rows.append({
                "product_code": product,
                "trade_date": row.trade_date,
                "ts_code": row.ts_code,
                "exchange": row.exchange,
                "market_cycle_phase": phase,
                "market_cycle_label": cycle["market_cycle_label"],
                "direction": cycle["direction"],
                "signal_bar": cycle["signal_bar"],
                "strategy": strategy_for_sample(cycle),
                "ema20_slope5_atr": cycle["ema20_slope5_atr"],
                "ema20_slope10_atr": cycle["ema20_slope10_atr"],
                "distance_ema20_atr": cycle["distance_ema20_atr"],
                "close_above_ema20": cycle["close_above_ema20"],
                "ema20_cross_count20": cycle["ema20_cross_count20"],
                "bars_above_ema20": cycle["bars_above_ema20"],
                "bars_below_ema20": cycle["bars_below_ema20"],
                "touched_ema20": cycle["touched_ema20"],
                "ema20_support_reaction": cycle["ema20_support_reaction"],
                "ema20_resistance_reaction": cycle["ema20_resistance_reaction"],
                "atr14": cycle["atr14"],
                "close": float(row.close),
                "vol": float(row.vol) if pd.notna(row.vol) else None,
                "amount": float(row.amount) if pd.notna(row.amount) else None,
                "oi": float(row.oi) if pd.notna(row.oi) else None,
                "oi_chg": float(row.oi_chg) if pd.notna(row.oi_chg) else None,
                "vol_zscore20": row.vol_zscore20,
                "amount_zscore20": row.amount_zscore20,
                "oi_chg_1": row.oi_chg_1,
                "oi_chg_5": row.oi_chg_5,
                "oi_chg_pct_1": row.oi_chg_pct_1,
                "oi_chg_pct_5": row.oi_chg_pct_5,
                "settle_close_atr": row.settle_close_atr,
                "open_gap_preclose_atr": row.open_gap_preclose_atr,
                "open_gap_prepair_atr": row.open_gap_prepair_atr,
                "close_vs_pre_settle_atr": row.close_vs_pre_settle_atr,
                "months_to_contract": row.months_to_contract,
                "is_near_contract_month": row.is_near_contract_month,
                "higher_high_count10": row.higher_high_count10,
                "higher_low_count10": row.higher_low_count10,
                "lower_high_count10": row.lower_high_count10,
                "lower_low_count10": row.lower_low_count10,
                "bull_trend_bar_count10": row.bull_trend_bar_count10,
                "bear_trend_bar_count10": row.bear_trend_bar_count10,
                "trend_bar_count10": row.trend_bar_count10,
                "counter_trend_bar_ratio10": row.counter_trend_bar_ratio10,
                "overlap_ratio20": row.overlap_ratio20,
                "range_width_atr20": row.range_width_atr20,
                "range_position20": row.range_position20,
                "failed_breakout_count20": row.failed_breakout_count20,
                "breakout_close_back_inside": row.breakout_close_back_inside,
                "breakout_follow_through_2": row.breakout_follow_through_2,
                "trend_side_bars_context": row.trend_side_bars_context,
                "leg1_size_atr10": row.leg1_size_atr10,
                "pullback_depth_atr10": row.pullback_depth_atr10,
                "pullback_ratio10": row.pullback_ratio10,
                "pullback_to_ema20": row.pullback_to_ema20,
                "second_entry_proxy": row.second_entry_proxy,
                "distance_to_mm_target_atr": row.distance_to_mm_target_atr,
                "measured_move_rr": row.measured_move_rr,
                "mm_progress": row.mm_progress,
                "ema20_stop_distance_atr": row.ema20_stop_distance_atr,
                "structure_stop_distance_atr": row.structure_stop_distance_atr,
                **path,
            })
    return pd.DataFrame(rows)


def summarize_strategy(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        return pd.DataFrame()
    grouped = dataset.groupby(["market_cycle_phase", "market_cycle_label", "signal_bar", "strategy"], dropna=False)
    summary = grouped.agg(
        samples=("hit_target_first", "size"),
        win_rate=("hit_target_first", "mean"),
        stop_rate=("hit_stop_first", "mean"),
        avg_r=("realized_r", "mean"),
        median_r=("realized_r", "median"),
        avg_mfe_atr=("mfe_atr", "mean"),
        avg_mae_atr=("mae_atr", "mean"),
        avg_gap_atr=("gap_atr", "mean"),
    ).reset_index()
    for col in ["win_rate", "stop_rate", "avg_r", "median_r", "avg_mfe_atr", "avg_mae_atr", "avg_gap_atr"]:
        summary[col] = summary[col].round(4)
    return summary.sort_values(["avg_r", "win_rate", "samples"], ascending=[False, False, False])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Brooks-cycle strategy stats from ML futures daily data.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--horizon", type=int, default=5)
    args = parser.parse_args()
    dataset = build_strategy_dataset(args.data_dir, args.horizon)
    out_dir = args.data_dir / "ml" / "processed"
    atomic_csv(dataset, out_dir / f"cycle_strategy_dataset_h{args.horizon}.csv")
    summary = summarize_strategy(dataset)
    atomic_csv(summary, out_dir / f"cycle_strategy_summary_h{args.horizon}.csv")
    report = {
        "horizon": args.horizon,
        "samples": len(dataset),
        "products": int(dataset.product_code.nunique()) if not dataset.empty else 0,
        "summary_rows": len(summary),
        "dataset": str(out_dir / f"cycle_strategy_dataset_h{args.horizon}.csv"),
        "summary": str(out_dir / f"cycle_strategy_summary_h{args.horizon}.csv"),
    }
    atomic_json(report, args.data_dir / "ml" / "quality" / f"cycle_strategy_h{args.horizon}.json")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if len(dataset) else 1


if __name__ == "__main__":
    raise SystemExit(main())
