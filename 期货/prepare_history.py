"""Prepare focused snapshot and the history needed by the trend screener."""
import argparse
import logging
from pathlib import Path
from collector import read_csv
from fetch_futures_data import make_collector
from focused import run_focused
from history import prepare_history
from config import DATA_DIR, COMMODITY_EXCHANGES


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--asof',required=True)
    parser.add_argument('--data-dir',type=Path,default=DATA_DIR)
    parser.add_argument('--days',type=int,default=550)
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--exchanges',nargs='+',choices=COMMODITY_EXCHANGES,default=COMMODITY_EXCHANGES)
    args=parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    collector=make_collector(args.exchanges,args.data_dir)
    report=run_focused(collector,args.asof,args.asof,args.force)
    if not report['success'] or args.asof not in report['published_days']:
        print('Snapshot incomplete or date closed; inspect quality/latest_run.json')
        return 1
    selected=read_csv(args.data_dir/f'raw/selected/{args.asof}.csv')
    result=prepare_history(collector,selected,args.asof,args.days,force=args.force)
    print(f'Prepared {len(result["prepared"])}; excluded {len(result["exclusions"])}',flush=True)
    return 0 if result['prepared'] else 1


if __name__=='__main__':
    raise SystemExit(main())
