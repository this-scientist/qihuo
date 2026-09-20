# -*- coding: utf-8 -*-
"""Run explicit small-batch/history downloads; importing causes no network or writes."""
import argparse
import logging
from pathlib import Path

from collector import Collector, DataError
from config import (TUSHARE_TOKEN, TUSHARE_HTTP_URL, DATA_DIR,
                    COMMODITY_EXCHANGES, REQUEST_INTERVAL, REQUEST_TIMEOUT)
from transport import TushareHTTP
from focused import run_focused


def make_collector(exchanges=None, root=DATA_DIR):
    return Collector(TushareHTTP(TUSHARE_TOKEN, TUSHARE_HTTP_URL, REQUEST_TIMEOUT),
                     root, exchanges or COMMODITY_EXCHANGES, REQUEST_INTERVAL)


def download_history(start_date, end_date, force=False):
    return run_focused(make_collector(), start_date, end_date, force)


def update_one_day(trade_date, force=True):
    return run_focused(make_collector(), trade_date, trade_date, force)


def main():
    parser = argparse.ArgumentParser(description='商品期货采集：通过校验才发布数据，失败重跑补采')
    parser.add_argument('--start', required=True, help='YYYYMMDD')
    parser.add_argument('--end', required=True, help='YYYYMMDD')
    parser.add_argument('--exchanges', nargs='+', choices=COMMODITY_EXCHANGES, default=COMMODITY_EXCHANGES)
    parser.add_argument('--force', action='store_true', help='刷新已验证分区；适合当日补充/供应商修订')
    parser.add_argument('--data-dir', type=Path, default=DATA_DIR)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    try:
        report = run_focused(make_collector(args.exchanges, args.data_dir), args.start, args.end, args.force)
    except (DataError, ValueError) as exc:
        logging.error('%s', exc)
        return 1
    print(f'校验结果：{"成功" if report["success"] else "有失败任务"}；失败数：{len(report["failures"])}')
    print(f'质量报告：{args.data_dir / "quality/latest_run.json"}')
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
