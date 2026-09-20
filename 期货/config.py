# -*- coding: utf-8 -*-
from pathlib import Path
import os

TUSHARE_TOKEN = "50c288537b94ce72a76c047aa37f3d55056445f3e310f5bd5691084a85f1"
TUSHARE_HTTP_URL = "https://tuaremax.top"

# Environment variables override the existing local gateway configuration.
TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN', TUSHARE_TOKEN)
TUSHARE_HTTP_URL = os.getenv('TUSHARE_HTTP_URL', TUSHARE_HTTP_URL)
REQUEST_INTERVAL = float(os.getenv('TUSHARE_REQUEST_INTERVAL', '0.8'))
REQUEST_TIMEOUT = float(os.getenv('TUSHARE_REQUEST_TIMEOUT', '30'))

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
