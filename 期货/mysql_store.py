# -*- coding: utf-8 -*-
"""MySQL persistence and API cache helpers for the dashboard."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _timeout(name: str, default: int) -> int:
    try:
        return max(1, int(float(os.getenv(name, str(default)))))
    except ValueError:
        return default


def mysql_config() -> dict[str, Any]:
    return dict(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "futures"),
        password=os.getenv("MYSQL_PASSWORD", "futures_pwd"),
        database=os.getenv("MYSQL_DATABASE", "futures_quant"),
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=_timeout("MYSQL_CONNECT_TIMEOUT", 2),
        read_timeout=_timeout("MYSQL_READ_TIMEOUT", 5),
        write_timeout=_timeout("MYSQL_WRITE_TIMEOUT", 5),
    )


def connect(database: bool = True):
    cfg = mysql_config()
    if not database:
        cfg.pop("database", None)
    return pymysql.connect(**cfg)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def json_hash(value: Any) -> str:
    return hashlib.sha256(json_dumps(value).encode("utf-8")).hexdigest()


SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS instruments (
      ts_code VARCHAR(40) PRIMARY KEY,
      product_code VARCHAR(20) NOT NULL,
      exchange VARCHAR(16) NOT NULL,
      name VARCHAR(80),
      sector VARCHAR(40),
      instrument_type ENUM('future','option','commodity') NOT NULL,
      active TINYINT(1) NOT NULL DEFAULT 1,
      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      KEY idx_instruments_sector (sector),
      KEY idx_instruments_product (product_code, exchange)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS futures_selected_daily (
      trade_date CHAR(8) NOT NULL,
      commodity_code VARCHAR(40) NOT NULL,
      main_code VARCHAR(40),
      secondary_code VARCHAR(40),
      close_adj DECIMAL(18,6),
      raw_close DECIMAL(18,6),
      vol DECIMAL(24,6),
      oi DECIMAL(24,6),
      payload_json JSON NOT NULL,
      PRIMARY KEY (trade_date, commodity_code),
      KEY idx_fsd_main (trade_date, main_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS futures_curve_daily (
      trade_date CHAR(8) NOT NULL,
      commodity_code VARCHAR(40) NOT NULL,
      contract_code VARCHAR(40) NOT NULL,
      delivery_month VARCHAR(12),
      days_to_delivery INT,
      settle DECIMAL(18,6),
      vol DECIMAL(24,6),
      oi DECIMAL(24,6),
      liquidity_rank INT NOT NULL,
      payload_json JSON NOT NULL,
      PRIMARY KEY (trade_date, commodity_code, contract_code),
      KEY idx_curve_rank (trade_date, commodity_code, liquidity_rank)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS commodity_metrics_daily (
      trade_date CHAR(8) NOT NULL,
      commodity_code VARCHAR(40) NOT NULL,
      name VARCHAR(80),
      sector VARCHAR(40),
      trend_direction VARCHAR(16),
      phase VARCHAR(40),
      close_adj DECIMAL(18,6),
      ma20 DECIMAL(18,6),
      ma60 DECIMAL(18,6),
      ma120 DECIMAL(18,6),
      return5 DECIMAL(12,6),
      return20 DECIMAL(12,6),
      rps20 DECIMAL(12,6),
      directional_rps20 DECIMAL(12,6),
      adx DECIMAL(12,6),
      atr14 DECIMAL(18,6),
      oi_change5 DECIMAL(12,6),
      volume_ratio DECIMAL(12,6),
      carry_annualized DECIMAL(12,6),
      carry_change5 DECIMAL(12,6),
      structure VARCHAR(40),
      payload_json JSON NOT NULL,
      PRIMARY KEY (trade_date, commodity_code),
      KEY idx_metrics_sector (trade_date, sector),
      KEY idx_metrics_phase (trade_date, phase)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS commodity_decision_daily (
      trade_date CHAR(8) NOT NULL,
      commodity_code VARCHAR(40) NOT NULL,
      name VARCHAR(80),
      sector VARCHAR(40),
      main_code VARCHAR(40),
      decision_direction VARCHAR(20),
      decision_side VARCHAR(20),
      state_v2 VARCHAR(20),
      trend_state VARCHAR(8),
      trend_state_label VARCHAR(40),
      trend_state_score DECIMAL(12,6),
      trend_transition VARCHAR(40),
      trend_option_gate VARCHAR(20),
      dir_score DECIMAL(12,6),
      start_score DECIMAL(12,6),
      price_rps DECIMAL(12,6),
      vol_rps DECIMAL(12,6),
      oi_change_rps DECIMAL(12,6),
      oi_behavior VARCHAR(40),
      structure_confirm VARCHAR(40),
      option_action VARCHAR(20),
      v2_rank INT,
      payload_json JSON NOT NULL,
      PRIMARY KEY (trade_date, commodity_code),
      KEY idx_decision_rank (trade_date, state_v2, v2_rank),
      KEY idx_decision_trend_state (trade_date, trend_state),
      KEY idx_decision_sector (trade_date, sector),
      KEY idx_decision_option (trade_date, option_action)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS option_contracts (
      option_code VARCHAR(60) PRIMARY KEY,
      underlying_code VARCHAR(40),
      exchange VARCHAR(16),
      call_put CHAR(1),
      exercise_price DECIMAL(18,6),
      maturity_date CHAR(8),
      list_date CHAR(8),
      delist_date CHAR(8),
      exercise_type VARCHAR(20),
      multiplier DECIMAL(18,6),
      payload_json JSON NOT NULL,
      KEY idx_option_underlying (underlying_code, maturity_date, call_put)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS option_daily (
      trade_date CHAR(8) NOT NULL,
      option_code VARCHAR(60) NOT NULL,
      underlying_code VARCHAR(40),
      commodity_code VARCHAR(40),
      close DECIMAL(18,6),
      premium DECIMAL(18,6),
      vol DECIMAL(24,6),
      oi DECIMAL(24,6),
      delta_value DECIMAL(18,8),
      gamma_value DECIMAL(18,8),
      theta_value DECIMAL(18,8),
      vega_value DECIMAL(18,8),
      iv_reference DECIMAL(12,6),
      days_to_expiry INT,
      moneyness_pct DECIMAL(12,6),
      break_even DECIMAL(18,6),
      payload_json JSON NOT NULL,
      PRIMARY KEY (trade_date, option_code),
      KEY idx_option_daily_underlying (trade_date, underlying_code),
      KEY idx_option_daily_commodity (trade_date, commodity_code)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS option_score_daily (
      trade_date CHAR(8) NOT NULL,
      option_code VARCHAR(60) NOT NULL,
      commodity_code VARCHAR(40),
      tradability_score DECIMAL(12,6),
      tradability_grade VARCHAR(20),
      aligned TINYINT(1),
      counter_trend TINYINT(1),
      iv_premium_pct DECIMAL(12,6),
      depth_value DECIMAL(24,6),
      tags_json JSON,
      breakdown_json JSON,
      payload_json JSON NOT NULL,
      PRIMARY KEY (trade_date, option_code),
      KEY idx_option_score_rank (trade_date, commodity_code, tradability_score)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS option_scanner_daily (
      trade_date CHAR(8) NOT NULL,
      commodity_code VARCHAR(40) NOT NULL,
      direction VARCHAR(16) NOT NULL,
      explosion_score DECIMAL(12,6),
      signals_met INT,
      signals_applicable INT,
      resonance TINYINT(1),
      tenbagger_score DECIMAL(12,6),
      tenbagger_label VARCHAR(20),
      best_option_code VARCHAR(60),
      payload_json JSON NOT NULL,
      PRIMARY KEY (trade_date, commodity_code, direction),
      KEY idx_scanner_rank (trade_date, direction, explosion_score)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS api_cache (
      trade_date CHAR(8) NOT NULL,
      cache_key VARCHAR(160) NOT NULL,
      payload_json JSON NOT NULL,
      payload_hash CHAR(64) NOT NULL,
      generated_at DATETIME NOT NULL,
      PRIMARY KEY (trade_date, cache_key),
      KEY idx_cache_generated (generated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

MIGRATION_SQL = [
    "ALTER TABLE commodity_decision_daily ADD COLUMN trend_state VARCHAR(8) AFTER state_v2",
    "ALTER TABLE commodity_decision_daily ADD COLUMN trend_state_label VARCHAR(40) AFTER trend_state",
    "ALTER TABLE commodity_decision_daily ADD COLUMN trend_state_score DECIMAL(12,6) AFTER trend_state_label",
    "ALTER TABLE commodity_decision_daily ADD COLUMN trend_transition VARCHAR(40) AFTER trend_state_score",
    "ALTER TABLE commodity_decision_daily ADD COLUMN trend_option_gate VARCHAR(20) AFTER trend_transition",
    "ALTER TABLE commodity_decision_daily ADD INDEX idx_decision_trend_state (trade_date, trend_state)",
]


def ensure_database() -> None:
    cfg = mysql_config()
    database = cfg["database"]
    conn = connect(database=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


def ensure_schema() -> None:
    ensure_database()
    conn = connect()
    try:
        with conn.cursor() as cur:
            for sql in SCHEMA_SQL:
                cur.execute(sql)
            for sql in MIGRATION_SQL:
                try:
                    cur.execute(sql)
                except pymysql.err.OperationalError as exc:
                    if exc.args and exc.args[0] in {1060, 1061}:
                        continue
                    raise
        conn.commit()
    finally:
        conn.close()


def cache_set(conn, trade_date: str, cache_key: str, payload: Any) -> None:
    payload_text = json_dumps(payload)
    with conn.cursor() as cur:
        cur.execute(
            """
            REPLACE INTO api_cache
              (trade_date, cache_key, payload_json, payload_hash, generated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (trade_date, cache_key, payload_text, hashlib.sha256(payload_text.encode()).hexdigest(), datetime.now()),
        )


def cache_get(trade_date: str, cache_key: str) -> Any | None:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT payload_json FROM api_cache WHERE trade_date=%s AND cache_key=%s",
                (trade_date, cache_key),
            )
            row = cur.fetchone()
            if not row:
                return None
            value = row["payload_json"]
            return json.loads(value) if isinstance(value, str) else value
    finally:
        conn.close()


def cache_dates(cache_key: str = "api:data") -> list[dict[str, Any]]:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT trade_date, payload_hash, generated_at
                FROM api_cache
                WHERE cache_key=%s
                ORDER BY trade_date DESC
                """,
                (cache_key,),
            )
            return [
                dict(
                    asof=row["trade_date"],
                    data_hash=row["payload_hash"],
                    generated_at=row["generated_at"].isoformat(timespec="seconds")
                    if hasattr(row["generated_at"], "isoformat")
                    else str(row["generated_at"]),
                )
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def cache_latest_date(cache_key: str = "api:data") -> str | None:
    dates = cache_dates(cache_key)
    return dates[0]["asof"] if dates else None


def mysql_ready() -> bool:
    try:
        ensure_schema()
        return True
    except Exception:
        return False
