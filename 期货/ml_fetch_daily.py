# -*- coding: utf-8 -*-
"""Fetch raw futures daily bars for ML experiments.

This collector is deliberately looser than the production dashboard pipeline:
it saves validated `fut_daily` rows by exchange and trade date without requiring
the contracts to exist in the current `fut_basic` universe. Historical ML data
can then decide how to filter far-month, dormant, or newly listed contracts.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime
from pathlib import Path

import math

import pandas as pd

from collector import DataError, FIELDS, SUFFIX, atomic_csv, atomic_json, required, unique
from config import COMMODITY_EXCHANGES, DATA_DIR
from fetch_futures_data import make_collector


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


def validate_ml_daily(df, date: str, exchange: str):
    """Validate raw ML daily rows while allowing optional amount gaps."""
    if df.empty:
        raise DataError(f"Empty daily data: {date} {exchange}")
    df = unique(df, ["ts_code", "trade_date"])
    required(df, ["open", "high", "low", "close", "settle", "vol", "oi"])
    if not df.trade_date.astype(str).eq(date).all():
        raise DataError("Wrong trade_date in response")
    if not df.ts_code.astype(str).str.endswith("." + SUFFIX[exchange]).all():
        raise DataError("Wrong exchange in response")
    for col in ["open", "high", "low", "close", "settle"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["vol"]:
        raw = df[col]
        df[col] = pd.to_numeric(df[col], errors="coerce")
        valid = df[col].map(lambda x: pd.notna(x) and math.isfinite(x) and x >= 0)
        if not valid.all() or (raw.notna() & df[col].isna()).any():
            raise DataError(f"Invalid numeric data: {col}")
    df["oi"] = pd.to_numeric(df["oi"], errors="coerce")
    df["oi_valid"] = df["oi"].map(lambda x: pd.notna(x) and math.isfinite(x) and x >= 0)
    df.loc[~df["oi_valid"], "oi"] = pd.NA
    if "amount" in df:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        df.loc[df["amount"].map(lambda x: not (pd.notna(x) and math.isfinite(x) and x >= 0)), "amount"] = pd.NA
    priced = df[["open", "high", "low", "close"]].map(lambda x: pd.notna(x) and math.isfinite(x) and x > 0).all(axis=1)
    df["price_anomaly"] = (df.vol > 0) & (df.close.le(0) | df.close.isna())
    priced = priced & ~df["price_anomaly"]
    rows = df.loc[priced]
    if (rows.high < rows[["open", "low", "close"]].max(axis=1)).any() or (
        rows.low > rows[["open", "high", "close"]].min(axis=1)
    ).any():
        raise DataError("Invalid OHLC relationship")
    df["exchange"] = exchange
    df["price_valid"] = priced
    return df.sort_values(["trade_date", "ts_code"]).reset_index(drop=True)


def fetch_ml_daily(start: str, end: str, data_dir: Path = DATA_DIR, exchanges=None, force: bool = False) -> dict:
    datetime.strptime(start, "%Y%m%d")
    datetime.strptime(end, "%Y%m%d")
    if start > end:
        raise ValueError("start must be <= end")
    exchanges = exchanges or COMMODITY_EXCHANGES
    collector = make_collector(exchanges, data_dir)
    root = Path(data_dir) / "ml" / "raw" / "fut_daily"
    failures, saved = [], []
    for exchange in exchanges:
        try:
            dates = collector.calendar(exchange, start, end)
        except DataError as exc:
            failures.append(dict(exchange=exchange, trade_date=None, error=str(exc)))
            continue
        for trade_date in dates:
            path = root / exchange / f"{trade_date}.csv"
            params = dict(trade_date=trade_date, exchange=exchange, fields=FIELDS, scope="ml_raw_daily_v1")
            if not force and _receipt_matches(path, "fut_daily", params):
                saved.append(dict(exchange=exchange, trade_date=trade_date, rows=None, cached=True))
                print(f"{exchange} {trade_date} cached", flush=True)
                continue
            try:
                df = collector.call("fut_daily", trade_date=trade_date, exchange=exchange, fields=FIELDS)
                df = validate_ml_daily(df, trade_date, exchange)
                atomic_csv(df, path)
                atomic_json(
                    dict(
                        version=1,
                        api="fut_daily",
                        params=params,
                        rows=len(df),
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        validated_at=datetime.now().isoformat(),
                    ),
                    path.with_suffix(".json"),
                )
                saved.append(dict(exchange=exchange, trade_date=trade_date, rows=len(df), cached=False))
                print(f"{exchange} {trade_date} saved rows={len(df)}", flush=True)
            except DataError as exc:
                failures.append(dict(exchange=exchange, trade_date=trade_date, error=str(exc)))
                print(f"{exchange} {trade_date} failed: {exc}", flush=True)
    report = dict(
        start_date=start,
        end_date=end,
        exchanges=list(exchanges),
        saved=saved,
        failures=failures,
        success=not failures,
        finished_at=datetime.now().isoformat(),
        note="Raw fut_daily partitions for ML. Main-series, gap, and strategy labels are built later.",
    )
    atomic_json(report, Path(data_dir) / "ml" / "quality" / "fut_daily_run.json")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch raw fut_daily partitions for ML training datasets.")
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYYMMDD")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--exchanges", nargs="+", choices=COMMODITY_EXCHANGES, default=COMMODITY_EXCHANGES)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = fetch_ml_daily(args.start, args.end, args.data_dir, args.exchanges, args.force)
    print(f"saved={len(report['saved'])} failures={len(report['failures'])} success={report['success']}")
    if report["failures"]:
        print(report["failures"][:5])
    print(args.data_dir / "ml" / "quality" / "fut_daily_run.json")
    return 0 if report["saved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
