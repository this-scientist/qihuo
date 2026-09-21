# -*- coding: utf-8 -*-
import os
from pathlib import Path

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TUSHARE_HTTP_URL = "https://tuaremax.top"


def load_tushare_config(env_path=PROJECT_ROOT / ".env"):
    file_values = dotenv_values(env_path)
    token = (
        os.environ.get("OAR_TUSHARE_TOKEN")
        or file_values.get("OAR_TUSHARE_TOKEN")
    )
    http_url = (
        os.environ.get("OAR_TUSHARE_HTTP_URL")
        or file_values.get("OAR_TUSHARE_HTTP_URL")
        or DEFAULT_TUSHARE_HTTP_URL
    )

    if not token:
        raise RuntimeError(
            "Missing OAR_TUSHARE_TOKEN. Set it in the project .env file "
            "or in the process environment."
        )

    return token, http_url


TUSHARE_TOKEN, TUSHARE_HTTP_URL = load_tushare_config()
REQUEST_INTERVAL = float(os.getenv("TUSHARE_REQUEST_INTERVAL", "0.8"))
REQUEST_TIMEOUT = float(os.getenv("TUSHARE_REQUEST_TIMEOUT", "30"))

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LOG_DIR = BASE_DIR / "logs"

BASIC_DIR = RAW_DIR / "basic"
DAILY_DIR = RAW_DIR / "daily"
CONTINUOUS_DIR = RAW_DIR / "continuous"
MAPPING_DIR = RAW_DIR / "mapping"
HOLDING_DIR = RAW_DIR / "holding"
WAREHOUSE_DIR = RAW_DIR / "warehouse"
SETTLE_DIR = RAW_DIR / "settle"
OPTION_DIR = RAW_DIR / "option"

FUTURE_EXCHANGES = ["DCE", "CZCE", "SHFE", "INE", "GFEX", "CFFEX"]
COMMODITY_EXCHANGES = ["DCE", "CZCE", "SHFE", "INE", "GFEX"]


def create_dirs():
    dirs = [
        DATA_DIR, RAW_DIR, PROCESSED_DIR, LOG_DIR,
        BASIC_DIR, DAILY_DIR, CONTINUOUS_DIR, MAPPING_DIR,
        HOLDING_DIR, WAREHOUSE_DIR, SETTLE_DIR, OPTION_DIR,
        OPTION_DIR / "daily",
    ]
    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)
