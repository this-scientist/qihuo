"""External fundamentals: explicit source/availability/underlying/unit; no invented values."""
import math
import pandas as pd
from collector import DataError, required, unique, read_csv, atomic_csv

FIELDS=['ts_code','trade_date','available_date','underlying_code','quote_unit','source','spot_price','commodity_oi']


def validate_supplements(frame):
    required(frame,FIELDS)
    frame=unique(frame,['ts_code','trade_date'])
    for key in ['trade_date','available_date']:
        frame[key]=frame[key].astype(str)
        if not frame[key].str.fullmatch(r'\d{8}').all():raise DataError('Invalid supplemental date')
    if (frame.available_date<frame.trade_date).any():raise DataError('Availability precedes observation date')
    for key in ['ts_code','underlying_code','quote_unit','source']:
        if frame[key].isna().any() or frame[key].astype(str).str.strip().eq('').any():raise DataError(f'Missing supplemental {key}')
    for key in ['spot_price','commodity_oi']:
        frame[key]=pd.to_numeric(frame[key],errors='raise')
        if not frame[key].map(lambda v:pd.isna(v) or math.isfinite(v) and v>=0).all():raise DataError('Invalid supplemental numeric value')
    return frame.sort_values(['ts_code','trade_date'])


def supplement_context(root,code,asof,record,dates):
    path=root/'supplemental/fundamentals.csv'
    status=dict(spot=False,basis=False,commodity_oi=False,reason='尚未导入外部现货和全品种OI',source=None)
    if not path.exists():return {},status
    df=validate_supplements(read_csv(path));df=df[df.ts_code.eq(code)&df.trade_date.le(asof)&df.available_date.le(asof)].set_index('trade_date')
    if asof not in df.index:return {},status|{'reason':'当前日期没有已可用的补充数据'}
    current=df.loc[asof];status['source']=str(current.source);context={}
    if len(dates)>=21:
        for n in [5,20]:
            expected=dates[-(n+1):]
            if set(expected)<=set(df.index):
                values=df.loc[expected,'commodity_oi']
                if values.notna().all() and values.iloc[0]>0:context[f'commodity_oi_change{n}']=(float(values.iloc[-1])/float(values.iloc[0])-1)*100
        status['commodity_oi']='commodity_oi_change5' in context and 'commodity_oi_change20' in context
    expected=dates[-6:]
    if len(expected)==6 and set(expected)<=set(df.index):
        frame=df.loc[expected]
        # Compare the same currently selected REAL contract, never adjusted continuous price.
        pair=root/f'processed/pair_history/{code.replace(".","_")}.csv'
        units_path=root/'raw/reference/quote_units.json'
        if pair.exists() and units_path.exists():
            import json
            units=json.loads(units_path.read_text(encoding='utf-8'))
            real=record.get('main_code');unit=units.get(real)
            normalize=lambda value:str(value).replace('人民币','').replace('千克','公斤').replace(' ','')
            matched=frame.underlying_code.eq(real).all() and unit and frame.quote_unit.map(normalize).eq(normalize(unit)).all()
            history=read_csv(pair);history=history[history.ts_code.eq(real)].set_index('trade_date')
            if matched and set(expected)<=set(history.index) and frame.spot_price.notna().all() and frame.spot_price.iloc[0]>0:
                basis=history.loc[expected,'close']-frame.spot_price
                context.update(spot_price=float(frame.spot_price.iloc[-1]),basis=float(basis.iloc[-1]),
                    basis_change5=float(basis.iloc[-1]-basis.iloc[0]),spot_change5=(float(frame.spot_price.iloc[-1])/float(frame.spot_price.iloc[0])-1)*100)
                status.update(spot=True,basis=True)
    status['reason']='外部数据已导入；未覆盖项保持缺失，基差要求真实主力身份和供应商报价单位匹配'
    return context,status


def import_supplements(root,records):
    incoming=validate_supplements(pd.DataFrame(records))
    path=root/'supplemental/fundamentals.csv'
    if path.exists():
        existing=read_csv(path);keys=set(zip(incoming.ts_code,incoming.trade_date))
        existing=existing[[key not in keys for key in zip(existing.ts_code,existing.trade_date)]]
        incoming=validate_supplements(pd.concat([existing,incoming],ignore_index=True))
    atomic_csv(incoming,path)
    return dict(rows=len(incoming),path='data/supplemental/fundamentals.csv')
