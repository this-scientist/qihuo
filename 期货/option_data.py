"""Fetch ONLY option chains on the selected real main and secondary futures."""
import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
import pandas as pd
from collector import DataError, required, unique, read_csv, atomic_csv, atomic_json, SUFFIX
from fetch_futures_data import make_collector
from config import DATA_DIR
from option_analysis import option_metrics


def paged_query(collector,name,params,path,cap=1000,force=False):
    cached=None if force else collector.cached(path,name,params)
    if cached is not None:return cached
    pages=[];seen=set()
    for offset in range(0,cap*50,cap):
        page=collector.call(name,**params,limit=cap,offset=offset)
        if page.empty:break
        required(page,['ts_code']);ids=set(page.ts_code.astype(str))
        if seen&ids:raise DataError(f'{name} pagination repeats identities')
        seen|=ids;pages.append(page)
        if len(page)<cap:break
    else:raise DataError(f'{name} pagination exceeded safety bound')
    result=pd.concat(pages,ignore_index=True) if pages else pd.DataFrame()
    atomic_csv(result,path);atomic_json(dict(version=1,api=name,params=params,sha256=hashlib.sha256(path.read_bytes()).hexdigest()),path.with_suffix('.json'))
    return result


def fetch_options(root,asof,force=False,progress=None,selected_root=None):
    root=Path(root);c=make_collector(root=root);c.retries=1
    selected=read_csv(Path(selected_root or root)/f'raw/selected/{asof}.csv');required(selected,['ts_code','close','exchange','main_code','role'])
    metadata=[];records=[];coverage=[];failures=[];units={};basic_refs={}
    units_path=root/'raw/reference/quote_units.json'
    if units_path.exists():units=json.loads(units_path.read_text(encoding='utf-8'))
    for exchange,group in selected.groupby('exchange'):
        try:
            daily=paged_query(c,'opt_daily',dict(exchange=exchange,trade_date=asof),root/f'raw/options/daily/{exchange}_{asof}.csv',15000,force)
            if daily.empty:raise DataError('Empty option daily snapshot')
            daily=unique(daily,['ts_code','trade_date']);required(daily,['trade_date','exchange','close','vol','oi'])
            if not daily.trade_date.astype(str).eq(asof).all() or not daily.exchange.eq(exchange).all() or not daily.ts_code.str.endswith('.'+SUFFIX[exchange]).all():raise DataError('Wrong option snapshot date/exchange')
            for key in ['close','vol','oi']:
                daily[key]=pd.to_numeric(daily[key],errors='coerce')
                if not daily[key].map(lambda v:pd.notna(v) and math.isfinite(v) and v>=0).all():raise DataError('Invalid option quote numeric value')
            quotes=daily.set_index('ts_code');matched_count=0
            for idx,row in enumerate(group.itertuples(),1):
                message=f'Options {exchange} {idx}/{len(group)} {row.ts_code}';print(message,flush=True)
                if progress:progress(message)
                try:
                    params=dict(exchange=exchange,opt_code='OP'+row.ts_code)
                    basic=paged_query(c,'opt_basic',params,root/f'raw/options/basic/{row.ts_code.replace(".","_")}_{asof}.csv',1000,force)
                    if basic.empty:coverage.append(dict(underlying_code=row.ts_code,exchange=exchange,count=0,reason='无对应期权元数据'));continue
                    required(basic,['opt_code','call_put','exercise_price','exercise_type','list_date','delist_date','maturity_date'])
                    if not basic.opt_code.eq('OP'+row.ts_code).all():raise DataError('Wrong option underlying metadata')
                    basic=unique(basic,['ts_code'])
                    active=basic.list_date.notna()&basic.delist_date.notna()&basic.maturity_date.notna()
                    basic=basic[active&basic.list_date.astype(str).le(asof)&basic.delist_date.astype(str).ge(asof)&basic.maturity_date.astype(str).ge(asof)].copy()
                    basic['underlying_code'],basic['main_code'],basic['role']=row.ts_code,row.main_code,row.role
                    basic['exercise_price']=pd.to_numeric(basic.exercise_price,errors='coerce')
                    if not basic.call_put.isin(['C','P']).all() or not basic.exercise_price.gt(0).all():raise DataError('Invalid option metadata')
                    # Verify futures quote units from actual contract reference data.
                    if row.ts_code not in units:
                        key=(exchange,row.fut_code)
                        if key not in basic_refs:
                            try:
                                ref=c.call('fut_basic',exchange=exchange,fut_type='1',fut_code=row.fut_code,fields='ts_code,quote_unit')
                                if 'ts_code' in ref and 'quote_unit' in ref:basic_refs[key]=ref.set_index('ts_code').quote_unit.to_dict()
                                else:basic_refs[key]={}
                            except DataError:basic_refs[key]={}
                        unit=basic_refs[key].get(row.ts_code)
                        if isinstance(unit,str) and unit:units[row.ts_code]=unit
                    count=0
                    for meta in basic.to_dict('records'):
                        if meta['ts_code'] not in quotes.index:continue
                        quote=quotes.loc[meta['ts_code']].to_dict()
                        if quote['close']<=0:continue
                        result=option_metrics(meta,quote,asof,float(row.close));result.update(main_code=row.main_code,role=row.role,exchange=exchange)
                        records.append(result);count+=1
                    metadata.append(basic);matched_count+=count
                    coverage.append(dict(underlying_code=row.ts_code,exchange=exchange,count=count,reason=None if count else '无有效当日报价'))
                except (DataError,ValueError) as exc:
                    failures.append(dict(underlying_code=row.ts_code,exchange=exchange,reason=str(exc) if isinstance(exc,DataError) else type(exc).__name__))
            coverage.append(dict(exchange=exchange,count=matched_count,reason='交易所采集完成'))
        except DataError as exc:failures.append(dict(exchange=exchange,reason=str(exc)))
    atomic_json(units,units_path)
    if metadata:atomic_csv(pd.concat(metadata,ignore_index=True),root/f'processed/options/{asof}/metadata.csv')
    atomic_csv(pd.DataFrame(records),root/f'processed/options/{asof}/chain.csv')
    report=dict(asof=asof,records=records,coverage=coverage,failures=failures,success=bool(records) and not failures,
        limitations=['日线收盘不代表可执行买卖盘口；本页仅期权观察','Black76参考IV不是接口直接提供的IV；美式期权存在模型近似',
            '只覆盖当日已选主力/次主力合约对应期权；未下载全月份期权历史'])
    atomic_json(report,root/f'processed/options/{asof}/report.json')
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--asof',required=True);parser.add_argument('--force',action='store_true');args=parser.parse_args()
    report=fetch_options(DATA_DIR,args.asof,args.force)
    print(f'Options records {len(report["records"])}; failures {len(report["failures"])}',flush=True)
    return 0 if report['success'] else 1


if __name__=='__main__':raise SystemExit(main())
