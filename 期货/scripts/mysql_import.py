# -*- coding: utf-8 -*-
"""Create MySQL tables and import the current dashboard snapshot."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector import read_csv
from config import DATA_DIR
from mysql_store import connect, ensure_schema, json_dumps, cache_set
from option_scanner import build_scanner
from research_server import ResearchStore, valid_date
from snapshot_store import read_snapshot, snapshot_source


def none_if_nan(value):
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return None
    except TypeError:
        pass
    return value


def product_code(ts_code: str | None) -> str:
    if not ts_code:
        return ""
    return ts_code.split(".")[0]


def exchange_code(ts_code: str | None) -> str:
    if not ts_code or "." not in ts_code:
        return ""
    return ts_code.split(".")[-1]


def scalar(row: dict, key: str):
    return none_if_nan(row.get(key))


def insert_many(cur, sql: str, rows: list[tuple], chunk: int = 500) -> int:
    total = 0
    for i in range(0, len(rows), chunk):
        part = rows[i : i + chunk]
        if part:
            cur.executemany(sql, part)
            total += len(part)
    return total


def import_payload(conn, payload: dict) -> dict[str, int]:
    asof = payload["asof"]
    counts = {}
    records = payload.get("records", [])
    decisions = payload.get("decisions", [])
    names = payload.get("names", {})

    instruments = {}
    for row in records:
        code = row["ts_code"]
        instruments[code] = (
            code,
            product_code(code),
            exchange_code(code),
            row.get("name") or names.get(code),
            row.get("sector"),
            "commodity",
            1,
        )
        for contract in [row.get("main_code"), row.get("secondary_code")]:
            if contract:
                instruments.setdefault(
                    contract,
                    (
                        contract,
                        product_code(code),
                        exchange_code(contract),
                        None,
                        row.get("sector"),
                        "future",
                        1,
                    ),
                )

    with conn.cursor() as cur:
        counts["instruments"] = insert_many(
            cur,
            """
            REPLACE INTO instruments
              (ts_code, product_code, exchange, name, sector, instrument_type, active)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            list(instruments.values()),
        )
        counts["futures_selected_daily"] = insert_many(
            cur,
            """
            REPLACE INTO futures_selected_daily
              (trade_date, commodity_code, main_code, secondary_code, close_adj, raw_close, vol, oi, payload_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    asof,
                    row["ts_code"],
                    scalar(row, "main_code"),
                    scalar(row, "secondary_code"),
                    scalar(row, "close"),
                    scalar(row, "raw_close"),
                    scalar(row, "vol"),
                    scalar(row, "oi"),
                    json_dumps(row),
                )
                for row in records
            ],
        )
        curve_rows = []
        for row in records:
            for rank, item in enumerate(row.get("curve") or [], 1):
                curve_rows.append(
                    (
                        asof,
                        row["ts_code"],
                        item.get("ts_code"),
                        item.get("delivery_month"),
                        item.get("days_to_delivery"),
                        item.get("settle"),
                        item.get("vol"),
                        item.get("oi"),
                        rank,
                        json_dumps(item),
                    )
                )
        counts["futures_curve_daily"] = insert_many(
            cur,
            """
            REPLACE INTO futures_curve_daily
              (trade_date, commodity_code, contract_code, delivery_month, days_to_delivery, settle, vol, oi, liquidity_rank, payload_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            curve_rows,
        )
        counts["commodity_metrics_daily"] = insert_many(
            cur,
            """
            REPLACE INTO commodity_metrics_daily
              (trade_date, commodity_code, name, sector, trend_direction, phase, close_adj, ma20, ma60, ma120,
               return5, return20, rps20, directional_rps20, adx, atr14, oi_change5, volume_ratio,
               carry_annualized, carry_change5, structure, payload_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    asof,
                    row["ts_code"],
                    scalar(row, "name"),
                    scalar(row, "sector"),
                    scalar(row, "trend_direction"),
                    scalar(row, "phase"),
                    scalar(row, "close"),
                    scalar(row, "ma20"),
                    scalar(row, "ma60"),
                    scalar(row, "ma120"),
                    scalar(row, "return5"),
                    scalar(row, "return20"),
                    scalar(row, "rps20"),
                    scalar(row, "directional_rps20"),
                    scalar(row, "adx"),
                    scalar(row, "atr14"),
                    scalar(row, "oi_change5"),
                    scalar(row, "volume_ratio"),
                    scalar(row, "carry_annualized"),
                    scalar(row, "carry_change5"),
                    scalar(row, "structure"),
                    json_dumps(row),
                )
                for row in records
            ],
        )
        counts["commodity_decision_daily"] = insert_many(
            cur,
            """
            REPLACE INTO commodity_decision_daily
              (trade_date, commodity_code, name, sector, main_code, decision_direction, decision_side, state_v2,
               trend_state, trend_state_label, trend_state_score, trend_transition, trend_option_gate,
               dir_score, start_score, price_rps, vol_rps, oi_change_rps, oi_behavior, structure_confirm,
               option_action, v2_rank, payload_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    asof,
                    row["ts_code"],
                    scalar(row, "name"),
                    scalar(row, "sector"),
                    scalar(row, "main_code"),
                    scalar(row, "decision_direction"),
                    scalar(row, "decision_side"),
                    scalar(row, "state_v2"),
                    scalar(row, "trend_state"),
                    scalar(row, "trend_state_label"),
                    scalar(row, "trend_state_score"),
                    scalar(row, "trend_transition"),
                    scalar(row, "trend_option_gate"),
                    scalar(row, "dir_score"),
                    scalar(row, "start_score"),
                    scalar(row, "price_rps"),
                    scalar(row, "vol_rps"),
                    scalar(row, "oi_change_rps"),
                    scalar(row, "oi_behavior"),
                    scalar(row, "structure_confirm"),
                    scalar(row, "option_action"),
                    scalar(row, "v2_rank"),
                    json_dumps(row),
                )
                for row in decisions
            ],
        )
    return counts


def import_options(conn, asof: str, option_payload: dict) -> dict[str, int]:
    counts = {}
    records = option_payload.get("records", [])
    instruments = {}
    for row in records:
        code = row.get("ts_code")
        if code:
            instruments[code] = (
                code,
                product_code(row.get("underlying_code") or code),
                exchange_code(code),
                None,
                None,
                "option",
                1,
            )
    with conn.cursor() as cur:
        counts["option_instruments"] = insert_many(
            cur,
            """
            REPLACE INTO instruments
              (ts_code, product_code, exchange, name, sector, instrument_type, active)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            list(instruments.values()),
        )
        counts["option_contracts"] = insert_many(
            cur,
            """
            REPLACE INTO option_contracts
              (option_code, underlying_code, exchange, call_put, exercise_price, maturity_date, list_date,
               delist_date, exercise_type, multiplier, payload_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    row.get("ts_code"),
                    row.get("underlying_code"),
                    row.get("exchange"),
                    row.get("call_put"),
                    row.get("exercise_price"),
                    row.get("maturity_date"),
                    row.get("list_date"),
                    row.get("delist_date"),
                    row.get("exercise_type"),
                    row.get("multiplier"),
                    json_dumps(row),
                )
                for row in records
                if row.get("ts_code")
            ],
        )
        counts["option_daily"] = insert_many(
            cur,
            """
            REPLACE INTO option_daily
              (trade_date, option_code, underlying_code, commodity_code, close, premium, vol, oi,
               delta_value, gamma_value, theta_value, vega_value, iv_reference, days_to_expiry,
               moneyness_pct, break_even, payload_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    asof,
                    row.get("ts_code"),
                    row.get("underlying_code"),
                    row.get("main_code"),
                    row.get("close"),
                    row.get("premium"),
                    row.get("vol"),
                    row.get("oi"),
                    row.get("delta"),
                    row.get("gamma"),
                    row.get("theta"),
                    row.get("vega"),
                    row.get("iv_reference"),
                    row.get("days_to_expiry"),
                    row.get("moneyness_pct"),
                    row.get("break_even"),
                    json_dumps(row),
                )
                for row in records
                if row.get("ts_code")
            ],
        )
        counts["option_score_daily"] = insert_many(
            cur,
            """
            REPLACE INTO option_score_daily
              (trade_date, option_code, commodity_code, tradability_score, tradability_grade,
               aligned, counter_trend, iv_premium_pct, depth_value, tags_json, breakdown_json, payload_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            [
                (
                    asof,
                    row.get("ts_code"),
                    row.get("main_code"),
                    (row.get("tradability") or {}).get("score"),
                    (row.get("tradability") or {}).get("grade"),
                    (row.get("tradability") or {}).get("aligned"),
                    (row.get("tradability") or {}).get("counter_trend"),
                    (row.get("tradability") or {}).get("iv_premium_pct"),
                    (row.get("tradability") or {}).get("depth"),
                    json_dumps((row.get("tradability") or {}).get("tags") or []),
                    json_dumps((row.get("tradability") or {}).get("breakdown") or {}),
                    json_dumps(row),
                )
                for row in records
                if row.get("ts_code")
            ],
        )
    return counts


def import_scanner(conn, asof: str, scanner: dict) -> dict[str, int]:
    rows = []
    for direction in ["long", "short", "extended"]:
        for row in scanner.get(direction) or []:
            tb = row.get("tenbagger") or {}
            rows.append(
                (
                    asof,
                    row.get("ts_code"),
                    row.get("direction") or direction,
                    row.get("explosion_score"),
                    row.get("signals_met"),
                    row.get("signals_applicable"),
                    row.get("resonance"),
                    tb.get("score"),
                    tb.get("label"),
                    tb.get("best"),
                    json_dumps(row),
                )
            )
    with conn.cursor() as cur:
        return {
            "option_scanner_daily": insert_many(
                cur,
                """
                REPLACE INTO option_scanner_daily
                  (trade_date, commodity_code, direction, explosion_score, signals_met, signals_applicable,
                   resonance, tenbagger_score, tenbagger_label, best_option_code, payload_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                rows,
            )
        }


def import_caches(conn, store: ResearchStore, asof: str, payload: dict, option_payload: dict) -> dict[str, int]:
    scanner = build_scanner(payload, option_payload, 5)
    cache_set(conn, asof, "api:data", payload)
    cache_set(conn, asof, "api:options:rate:0.02", option_payload)
    cache_set(conn, asof, "api:scanner:top:5", scanner)
    underlyings = sorted({row.get("underlying_code") for row in option_payload.get("records", []) if row.get("underlying_code")})
    for code in underlyings:
        try:
            cache_set(conn, asof, f"api:options:underlying:{code}", store.underlying(asof, code))
        except Exception as exc:
            cache_set(conn, asof, f"api:options:underlying:{code}", dict(code=code, values=[], reason=type(exc).__name__))
    import_scanner(conn, asof, scanner)
    return {"api_cache": 3 + len(underlyings), "underlying_cache": len(underlyings)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asof")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    state = args.data_dir / "quality/dashboard_state.json"
    asof = args.asof
    if not asof:
        if state.exists():
            asof = json.loads(state.read_text(encoding="utf-8"))["active"]
        else:
            asof = json.loads((args.data_dir / "quality/history_run.json").read_text(encoding="utf-8"))["asof"]
    asof = valid_date(asof)

    os.environ["MYSQL_READ_CACHE"] = "0"
    ensure_schema()
    store = ResearchStore(args.data_dir, asof)
    payload = store.get(asof)
    option_payload = store.option_payload(asof)

    conn = connect()
    try:
        counts = {}
        counts.update(import_payload(conn, payload))
        counts.update(import_options(conn, asof, option_payload))
        counts.update(import_caches(conn, store, asof, payload, option_payload))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(json.dumps(dict(asof=asof, counts=counts), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
