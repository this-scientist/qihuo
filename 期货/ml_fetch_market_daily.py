# -*- coding: utf-8 -*-
"""Fetch non-futures OHLCV series for mixed-market ML experiments."""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd

from collector import atomic_csv, atomic_json
from config import DATA_DIR
from fetch_futures_data import make_collector


CN_INDEX_CODES = ["000300.SH", "000905.SH", "000852.SH", "000016.SH", "399006.SZ", "000688.SH"]
GLOBAL_INDEX_CODES = ["SPX", "IXIC", "DJI", "RUT", "HSI", "HKTECH", "N225", "GDAXI", "FTSE"]
SGE_CODES = ["Au99.99", "Au(T+D)", "Ag(T+D)"]


def _receipt_matches(path: Path, api: str, params: dict) -> bool:
    receipt = path.with_suffix(".json")
    if not path.exists() or not receipt.exists():
        return False
    try:
        import json

        info = json.loads(receipt.read_text(encoding="utf-8"))
        return (
            info.get("version") == 1
            and info.get("api") == api
            and info.get("params") == params
            and info.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest()
        )
    except (OSError, ValueError):
        return False


def _standardize(df: pd.DataFrame, source: str, ts_code: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    data = df.copy()
    data["ts_code"] = data.get("ts_code", ts_code).astype(str)
    data = data[data["ts_code"].eq(ts_code)].copy()
    for col in ["open", "high", "low", "close", "pre_close", "vol", "amount", "oi"]:
        if col not in data:
            data[col] = pd.NA
        data[col] = pd.to_numeric(data[col], errors="coerce")
    if "price_avg" in data and "settle" not in data:
        data["settle"] = pd.to_numeric(data["price_avg"], errors="coerce")
    if "settle" not in data:
        data["settle"] = data["close"]
    data["settle"] = pd.to_numeric(data["settle"], errors="coerce")
    data["pre_settle"] = data["settle"].shift(-1)
    data["oi_chg"] = data["oi"] - data["oi"].shift(-1)
    data["exchange"] = source
    data["price_valid"] = data[["open", "high", "low", "close"]].gt(0).all(axis=1)
    data = data[data["price_valid"]].copy()
    keep = [
        "ts_code", "trade_date", "pre_close", "pre_settle", "open", "high", "low", "close",
        "settle", "vol", "amount", "oi", "oi_chg", "exchange", "price_valid",
    ]
    return data[keep].sort_values("trade_date").reset_index(drop=True)


def _save_series(df: pd.DataFrame, path: Path, api: str, params: dict) -> dict:
    atomic_csv(df, path)
    atomic_json(
        {
            "version": 1,
            "api": api,
            "params": params,
            "rows": len(df),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "validated_at": datetime.now().isoformat(),
        },
        path.with_suffix(".json"),
    )
    return {"path": str(path), "rows": len(df), "cached": False}


def _futures_trade_dates(data_dir: Path, start: str, end: str) -> list[str]:
    dates = []
    for path in (data_dir / "ml" / "raw" / "fut_daily").glob("*/*.csv"):
        date = path.stem
        if start <= date <= end:
            dates.append(date)
    return sorted(set(dates))


def fetch_market_daily(start: str, end: str, data_dir: Path = DATA_DIR, force: bool = False) -> dict:
    datetime.strptime(start, "%Y%m%d")
    datetime.strptime(end, "%Y%m%d")
    if start > end:
        raise ValueError("start must be <= end")
    collector = make_collector(root=data_dir)
    root = Path(data_dir) / "ml" / "raw" / "market_daily"
    saved, failures = [], []

    for ts_code in CN_INDEX_CODES:
        path = root / "cn_index" / f"{ts_code.replace('.', '_')}.csv"
        params = {"ts_code": ts_code, "start_date": start, "end_date": end, "scope": "ml_market_daily_v1"}
        if not force and _receipt_matches(path, "index_daily", params):
            saved.append({"path": str(path), "rows": None, "cached": True})
            continue
        try:
            df = collector.call("index_daily", ts_code=ts_code, start_date=start, end_date=end)
            df = _standardize(df, "CN_INDEX", ts_code)
            saved.append(_save_series(df, path, "index_daily", params))
            print(f"cn_index {ts_code} rows={len(df)}", flush=True)
        except Exception as exc:
            failures.append({"api": "index_daily", "ts_code": ts_code, "error": str(exc)})

    for ts_code in SGE_CODES:
        path = root / "sge" / f"{ts_code.replace('/', '_').replace('(', '').replace(')', '')}.csv"
        params = {"ts_code": ts_code, "start_date": start, "end_date": end, "scope": "ml_market_daily_v1"}
        if not force and _receipt_matches(path, "sge_daily", params):
            saved.append({"path": str(path), "rows": None, "cached": True})
            continue
        try:
            df = collector.call("sge_daily", ts_code=ts_code, start_date=start, end_date=end)
            df = _standardize(df, "SGE", ts_code)
            saved.append(_save_series(df, path, "sge_daily", params))
            print(f"sge {ts_code} rows={len(df)}", flush=True)
        except Exception as exc:
            failures.append({"api": "sge_daily", "ts_code": ts_code, "error": str(exc)})

    frames = []
    dates = _futures_trade_dates(data_dir, start, end)
    global_path = root / "global_index" / "global_indices.csv"
    params = {"start_date": start, "end_date": end, "codes": GLOBAL_INDEX_CODES, "scope": "ml_market_daily_v1"}
    if not force and _receipt_matches(global_path, "index_global", params):
        saved.append({"path": str(global_path), "rows": None, "cached": True})
    else:
        for trade_date in dates:
            try:
                df = collector.call("index_global", trade_date=trade_date)
                df = df[df["ts_code"].astype(str).isin(GLOBAL_INDEX_CODES)].copy()
                frames.append(df)
                print(f"global_index {trade_date} rows={len(df)}", flush=True)
            except Exception as exc:
                failures.append({"api": "index_global", "trade_date": trade_date, "error": str(exc)})
        if frames:
            merged = pd.concat(frames, ignore_index=True, sort=False)
            standardized = []
            for ts_code in GLOBAL_INDEX_CODES:
                standardized.append(_standardize(merged, "GLOBAL_INDEX", ts_code))
            out = pd.concat(standardized, ignore_index=True, sort=False)
            saved.append(_save_series(out, global_path, "index_global", params))

    report = {
        "start_date": start,
        "end_date": end,
        "saved": saved,
        "failures": failures,
        "success": not failures,
        "finished_at": datetime.now().isoformat(),
    }
    atomic_json(report, Path(data_dir) / "ml" / "quality" / "market_daily_run.json")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch non-futures daily bars for mixed-market ML training.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = fetch_market_daily(args.start, args.end, args.data_dir, args.force)
    print(f"saved={len(report['saved'])} failures={len(report['failures'])} success={report['success']}")
    if report["failures"]:
        print(report["failures"][:8])
    return 0 if report["saved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
