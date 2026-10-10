# -*- coding: utf-8 -*-
"""Train first-pass probability models for Brooks-cycle futures strategies."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from collector import atomic_json


CATEGORICAL = ["market_cycle_phase", "signal_bar", "strategy", "direction"]
NUMERIC = [
    "ema20_slope5_atr",
    "ema20_slope10_atr",
    "distance_ema20_atr",
    "close_above_ema20",
    "ema20_cross_count20",
    "bars_above_ema20",
    "bars_below_ema20",
    "touched_ema20",
    "ema20_support_reaction",
    "ema20_resistance_reaction",
    "atr14",
    "vol",
    "amount",
    "oi",
    "oi_chg",
    "vol_zscore20",
    "amount_zscore20",
    "oi_chg_1",
    "oi_chg_5",
    "oi_chg_pct_1",
    "oi_chg_pct_5",
    "settle_close_atr",
    "open_gap_preclose_atr",
    "open_gap_prepair_atr",
    "close_vs_pre_settle_atr",
    "is_near_contract_month",
    "higher_high_count10",
    "higher_low_count10",
    "lower_high_count10",
    "lower_low_count10",
    "bull_trend_bar_count10",
    "bear_trend_bar_count10",
    "trend_bar_count10",
    "counter_trend_bar_ratio10",
    "overlap_ratio20",
    "range_width_atr20",
    "range_position20",
    "failed_breakout_count20",
    "breakout_close_back_inside",
    "breakout_follow_through_2",
    "trend_side_bars_context",
    "leg1_size_atr10",
    "pullback_depth_atr10",
    "pullback_ratio10",
    "pullback_to_ema20",
    "second_entry_proxy",
    "distance_to_mm_target_atr",
    "measured_move_rr",
    "mm_progress",
    "ema20_stop_distance_atr",
    "structure_stop_distance_atr",
    "gap_atr",
    "gap_with_trend",
]


def _metrics(y_true, prob):
    result = {"brier": round(float(brier_score_loss(y_true, prob)), 6)}
    if len(set(y_true)) > 1:
        result["auc"] = round(float(roc_auc_score(y_true, prob)), 6)
    else:
        result["auc"] = None
    return result


def _bucket_table(frame: pd.DataFrame, prob_col: str) -> list[dict]:
    data = frame.copy()
    data["bucket"] = pd.qcut(data[prob_col], q=5, duplicates="drop")
    rows = []
    for bucket, group in data.groupby("bucket", observed=True):
        rows.append({
            "bucket": str(bucket),
            "samples": int(len(group)),
            "avg_probability": round(float(group[prob_col].mean()), 4),
            "win_rate": round(float(group["hit_target_first"].mean()), 4),
            "avg_r": round(float(group["realized_r"].mean()), 4),
        })
    return rows


def _split_dataset(data: pd.DataFrame, mode: str, train_ratio: float, purge_days: int, random_state: int):
    if mode == "random":
        train, test = train_test_split(
            data,
            train_size=train_ratio,
            random_state=random_state,
            shuffle=True,
            stratify=data["hit_target_first"] if data["hit_target_first"].nunique() > 1 else None,
        )
        return train.copy(), test.copy(), "random_stratified_70_30"
    if mode not in {"time", "purged_time"}:
        raise ValueError("split_mode must be one of: time, purged_time, random")
    split_idx = int(len(data) * train_ratio)
    train = data.iloc[:split_idx].copy()
    test = data.iloc[split_idx:].copy()
    if mode == "purged_time" and len(train) and len(test) and purge_days > 0:
        cutoff = pd.to_datetime(str(test.trade_date.min()), format="%Y%m%d") - pd.Timedelta(days=purge_days)
        train_dates = pd.to_datetime(train.trade_date.astype(str), format="%Y%m%d")
        train = train[train_dates <= cutoff].copy()
    return train, test, f"{mode}_{int(train_ratio * 100)}_{int((1 - train_ratio) * 100)}_purge{purge_days if mode == 'purged_time' else 0}"


def train_models(dataset_path: Path, output_path: Path, split_mode: str = "purged_time", train_ratio: float = 0.7, purge_days: int = 7, random_state: int = 7) -> dict:
    data = pd.read_csv(dataset_path, dtype={"trade_date": str})
    data = data.dropna(subset=["hit_target_first"]).copy()
    data = data.sort_values("trade_date").reset_index(drop=True)
    train, test, split_name = _split_dataset(data, split_mode, train_ratio, purge_days, random_state)
    preprocess = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), NUMERIC),
    ])
    models = {
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(n_estimators=200, min_samples_leaf=25, random_state=7, class_weight="balanced_subsample"),
    }
    report = {
        "dataset": str(dataset_path),
        "samples": int(len(data)),
        "train_samples": int(len(train)),
        "test_samples": int(len(test)),
        "train_start": str(train.trade_date.min()) if len(train) else None,
        "train_end": str(train.trade_date.max()) if len(train) else None,
        "test_start": str(test.trade_date.min()) if len(test) else None,
        "test_end": str(test.trade_date.max()) if len(test) else None,
        "split": split_name,
        "split_mode": split_mode,
        "train_ratio": train_ratio,
        "purge_days": purge_days if split_mode == "purged_time" else 0,
        "models": {},
    }
    for name, estimator in models.items():
        pipe = Pipeline([("prep", preprocess), ("model", estimator)])
        pipe.fit(train[CATEGORICAL + NUMERIC], train["hit_target_first"])
        train_prob = pipe.predict_proba(train[CATEGORICAL + NUMERIC])[:, 1]
        test_prob = pipe.predict_proba(test[CATEGORICAL + NUMERIC])[:, 1]
        scored_test = test.copy()
        scored_test[f"{name}_prob"] = test_prob
        report["models"][name] = {
            "train": _metrics(train["hit_target_first"], train_prob),
            "test": _metrics(test["hit_target_first"], test_prob),
            "test_buckets": _bucket_table(scored_test, f"{name}_prob"),
        }
    atomic_json(report, output_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Train first-pass ML models for futures cycle strategies.")
    parser.add_argument("--dataset", type=Path, default=Path("data/ml/processed/cycle_strategy_dataset_h5.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/ml/model_outputs/cycle_strategy_h5_models.json"))
    parser.add_argument("--split-mode", choices=["time", "purged_time", "random"], default="purged_time")
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--purge-days", type=int, default=7)
    parser.add_argument("--random-state", type=int, default=7)
    args = parser.parse_args()
    report = train_models(args.dataset, args.output, args.split_mode, args.train_ratio, args.purge_days, args.random_state)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
