"""Causal indicators and transparent directional trend/startup scores."""
from dataclasses import dataclass
import json

import numpy as np
import pandas as pd

from collector import DataError, required, unique


@dataclass(frozen=True)
class Settings:
    min_history: int = 280
    min_universe: int = 20
    top: int = 5
    adx_min: float = 20
    startup_rps: float = 90
    trend_min: float = 70
    startup_min: float = 65
    startup_hits: int = 6
    max_extension_atr: float = 3
    min_coverage: float = 90

    @classmethod
    def load(cls, path=None):
        values = json.loads(path.read_text(encoding='utf-8')) if path else {}
        result = cls(**values)
        if result.min_history < 280 or result.min_universe < 2 or result.top < 1 or not 1 <= result.startup_hits <= 9:
            raise ValueError('Invalid history/universe/top/hits settings')
        if not all(0 <= x <= 100 for x in [result.adx_min,result.startup_rps,result.trend_min,result.startup_min,result.min_coverage]) or result.max_extension_atr <= 0:
            raise ValueError('Invalid scoring thresholds')
        return result


def wilder(values, period=14):
    array = np.asarray(values, dtype=float)
    out = np.full(len(array),np.nan)
    seed = []
    state = None
    for i,value in enumerate(array):
        if not np.isfinite(value):
            seed, state = [],None
            continue
        if state is None:
            seed.append(value)
            if len(seed)==period:
                state = sum(seed)/period
                out[i] = state
        else:
            state = (state*(period-1)+value)/period
            out[i] = state
    return pd.Series(out,index=values.index)


def indicators(data):
    required(data,['trade_date','open','high','low','close'])
    df = data.sort_values('trade_date').reset_index(drop=True).copy()
    if df.trade_date.duplicated().any():
        raise DataError('Duplicate indicator dates')
    for field in ['open','high','low','close']:
        df[field]=pd.to_numeric(df[field],errors='coerce')
        if not np.isfinite(df[field]).all() or not df[field].gt(0).all():
            raise DataError(f'Invalid indicator price: {field}')
    c,h,l = df.close,df.high,df.low
    for n in [20,60,120]:
        df[f'ma{n}']=c.rolling(n).mean()
        df[f'return{n}']=c/c.shift(n)-1
        df[f'slope{n}']=df[f'ma{n}']/df[f'ma{n}'].shift(5)-1
    df['return1']=c/c.shift(1)-1
    df['return5']=c/c.shift(5)-1
    df['trend_spread']=(df.ma20-df.ma120)/df.ma120
    df['trend_spread_change5']=df.trend_spread-df.trend_spread.shift(5)
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    df['atr14']=wilder(tr)
    df['ma_spread_atr']=(df.ma20-df.ma120)/df.atr14.replace(0,np.nan)
    df['ma_spread_atr_change5']=df.ma_spread_atr-df.ma_spread_atr.shift(5)
    up,down=h.diff(),-l.diff()
    plus=up.where((up>down)&(up>0),0.0)
    minus=down.where((down>up)&(down>0),0.0)
    denom=df.atr14.replace(0,np.nan)
    df['plus_di']=(100*wilder(plus)/denom).fillna(0)
    df['minus_di']=(100*wilder(minus)/denom).fillna(0)
    total=(df.plus_di+df.minus_di).replace(0,np.nan)
    dx=(100*(df.plus_di-df.minus_di).abs()/total).fillna(0)
    dx.loc[df.atr14.isna()]=np.nan
    df['adx']=wilder(dx)
    df['adx_slope']=df.adx-df.adx.shift(5)
    df['atr_pct']=df.atr14/c*100
    df['atr_ratio']=df.atr14/df.atr14.rolling(60).mean()
    df['atr_change5']=df.atr14/df.atr14.shift(5)-1
    df['atr_percentile']=df.atr_pct.rolling(252).apply(lambda a: 100*(np.sum(a<a[-1])+0.5*np.sum(a==a[-1]))/len(a),raw=True)
    for n in [20,55]:
        df[f'high{n}']=h.shift(1).rolling(n).max()
        df[f'low{n}']=l.shift(1).rolling(n).min()
        df[f'break{n}_up']=c>df[f'high{n}']
        df[f'break{n}_down']=c<df[f'low{n}']
    return df


def rps_panel(data):
    required(data,['ts_code','trade_date','close'])
    df=unique(data,['ts_code','trade_date']).sort_values(['ts_code','trade_date']).copy()
    for n in [5,20,60,120]:
        returns=df.groupby('ts_code').close.transform(lambda c: c/c.shift(n)-1)
        group=returns.groupby(df.trade_date)
        rank=group.rank(method='average')
        count=group.transform('count')
        df[f'rps{n}']=((rank-1)/(count-1)*100).where(count>1,50).where(returns.notna())
        df[f'rps{n}_count']=count
        df[f'rps{n}_prev5']=df.groupby('ts_code')[f'rps{n}'].shift(5)
    return df


def number(value):
    return float(value) if value is not None and pd.notna(value) and np.isfinite(value) else None


def pair_context(data, asof, trading_dates=None):
    """Compare the SAME current two contracts through time; never roles across rolls."""
    if data is None or data.empty:
        return {}
    df=data[data.trade_date.astype(str).le(asof)].copy()
    roles=df.groupby('role').ts_code.nunique()
    if (roles>1).any():
        raise DataError('Pair history changes contract identity')
    codes=df.groupby('role').ts_code.first().to_dict()
    scope='main_secondary_fixed_pair' if 'secondary' in codes else 'main_only'
    if 'main' not in codes:
        return {}
    df=unique(df,['ts_code','trade_date'])
    for field in ['oi','vol','close','settle']:
        required(df,[field])
        df[field]=pd.to_numeric(df[field],errors='coerce')
        if field in ['oi','vol']:
            present=df[field].dropna()
            if not np.isfinite(present).all() or (present<0).any():
                raise DataError(f'Invalid individual contract {field}; cannot aggregate')
    # Inner intersection ensures both contracts participate on every compared day.
    count=df.groupby('trade_date').ts_code.nunique()
    valid_dates=count[count.eq(len(codes))].index
    matched=df[df.trade_date.isin(valid_dates)]
    summed=matched.groupby('trade_date')[['oi','vol']].agg(lambda x: x.sum(min_count=len(codes))).sort_index()
    result={'oi_scope':scope,'main_code':codes['main'],'secondary_code':codes.get('secondary')}
    if not summed.empty and summed.index[-1] == asof:
        result['pair_oi'] = number(summed.oi.iloc[-1])
        today = matched[matched.trade_date.eq(asof)].set_index('role')
        result['main_oi'] = number(today.loc['main', 'oi'])
        result['secondary_oi'] = number(today.loc['secondary', 'oi']) if 'secondary' in today.index else None
    required21=list(trading_dates)[-21:] if trading_dates is not None else None
    complete21=required21 is None or (len(required21)==21 and summed.index[-21:].tolist()==required21)
    if len(summed)>=21 and summed.index[-1]==asof and complete21:
        oi=summed.oi
        vol=summed.vol
        if oi.iloc[-21:].notna().all() and (oi.iloc[-21:]>0).all() and vol.iloc[-21:].notna().all() and (vol.iloc[-21:]>=0).all():
            result.update(oi_change5=oi.iloc[-1]/oi.iloc[-6]-1,oi_change20=oi.iloc[-1]/oi.iloc[-21]-1,
                volume_ratio=number(vol.iloc[-1]/vol.iloc[-21:-1].mean()) if vol.iloc[-21:-1].mean()>0 else None)
            by_role=matched.pivot(index='trade_date',columns='role',values='oi').sort_index()
            if {'main','secondary'}.issubset(by_role.columns) and by_role[['main','secondary']].iloc[-21:].notna().all().all() and (by_role[['main','secondary']].iloc[-21:]>0).all().all():
                main_now,main_5,main_20=by_role.main.iloc[-1],by_role.main.iloc[-6],by_role.main.iloc[-21]
                secondary_now,secondary_5,secondary_20=by_role.secondary.iloc[-1],by_role.secondary.iloc[-6],by_role.secondary.iloc[-21]
                main_drop5=max(0,main_5-main_now)
                secondary_gain5=max(0,secondary_now-secondary_5)
                absorption=secondary_gain5/main_drop5 if main_drop5>0 else None
                result.update(main_oi_change5=main_now/main_5-1,main_oi_change20=main_now/main_20-1,
                    secondary_oi_change5=secondary_now/secondary_5-1,secondary_oi_change20=secondary_now/secondary_20-1,
                    rollover_absorption5=number(absorption),
                    rollover_transfer=bool(main_now<main_5 and secondary_now>secondary_5 and (secondary_gain5/main_drop5 if main_drop5>0 else 0)>=.5 and oi.iloc[-1]/oi.iloc[-6]-1>=-.02))
    if 'secondary' in codes:
        # Product prefix may contain letters; final month digits determine ordering.
        def month(code):
            import re
            digits=re.search(r'(\d{3,4})\.',code).group(1)
            year=int(asof[:4]); m=int(digits[-2:])
            if len(digits)==4:
                y=2000+int(digits[:2])
            else:
                choices=[y for y in range(year-1,year+6) if y%10==int(digits[0])]
                if not choices:
                    raise DataError('Ambiguous contract delivery year')
                y=choices[0]
            if not 1<=m<=12:
                raise DataError('Invalid contract month')
            return y*100+m
        ordered=sorted(codes.values(),key=month)
        prices=matched.pivot(index='trade_date',columns='ts_code',values='settle').sort_index()
        required6=list(trading_dates)[-6:] if trading_dates is not None else None
        complete6=required6 is None or (len(required6)==6 and prices.index[-6:].tolist()==required6)
        if len(prices)>=6 and prices.index[-1]==asof and complete6 and prices[ordered].iloc[-6:].notna().all().all() and (prices[ordered].iloc[-6:]>0).all().all():
            spread=prices[ordered[0]]-prices[ordered[1]]
            result.update(near_code=ordered[0],far_code=ordered[1],spread=spread.iloc[-1],spread_change5=spread.iloc[-1]-spread.iloc[-6])
            # 期限结构动量：真实月合约结算价的年化Carry序列；两合约身份固定，跨日可比。
            from term_structure import annualized_carry, carry_momentum, structure_label
            try:
                near_month,far_month=month(ordered[0]),month(ordered[1])
            except DataError:
                near_month=far_month=None
            if near_month is not None:
                series=[annualized_carry(prices.loc[day,ordered[0]],prices.loc[day,ordered[1]],near_month,far_month) for day in prices.index]
                momentum=carry_momentum(series)
                result.update(carry_annualized=momentum['carry'],carry_change5=momentum['change5'],carry_change20=momentum['change20'],
                    structure=structure_label(momentum['carry']),structure_flip5=momentum['flip5'])
    return result


def evaluate(data, direction, context, settings):
    if direction not in [-1,1]:
        raise ValueError('Direction must be +1 or -1')
    row=data.iloc[-1]
    d=direction
    side='up' if d==1 else 'down'
    rps={n:row[f'rps{n}'] if d==1 else 100-row[f'rps{n}'] for n in [20,60,120]}
    rps_prev5=row.rps20_prev5 if d==1 else 100-row.rps20_prev5
    oriented=lambda a,b: d*(a-b)>0
    cross=((data.ma20-data.ma60)*d>0)&((data.ma20.shift(1)-data.ma60.shift(1))*d<=0)
    recent20=bool(data[f'break20_{side}'].tail(5).any())
    recent55=bool(data[f'break55_{side}'].tail(5).any())
    fresh_break=recent20 and int(data[f'break20_{side}'].iloc[-25:-5].sum())<=2
    ma_parts=[(oriented(row.close,row.ma20),4),(oriented(row.ma20,row.ma60),5),
        (oriented(row.ma60,row.ma120),5),(d*row.slope20>0,2),(d*row.slope60>0,2),(d*row.ma_spread_atr_change5>0,2)]
    score_ma=sum(w for ok,w in ma_parts if ok)
    rps120_prev=row.rps120_prev5 if d==1 else 100-row.rps120_prev5
    score_rps=8*np.clip((rps[20]-50)/40,0,1)+7*np.clip((rps[60]-50)/30,0,1)+3*np.clip((rps[120]-50)/30,0,1)+2*(rps[120]>rps120_prev)
    score_breakout=6*recent20+10*recent55+4*fresh_break
    di_ok=oriented(row.plus_di,row.minus_di)
    score_quality=5*np.clip((row.adx-15)/15,0,1)+4*(row.adx_slope>0)+3*di_ok+3*(row.atr_change5>0 and row.atr_percentile<95)
    funding=None
    if all(number(context.get(k)) is not None for k in ['oi_change5','oi_change20','volume_ratio']):
        funding=5*(context['oi_change5']>0)+5*(context['oi_change20']>0)+5*(1.2<=context['volume_ratio']<=3)
    structure=None
    if number(context.get('spread_change5')) is not None:
        structure=5*(d*context['spread_change5']>0)
    # Basis needs both spot and basis changes; absent in default futures-only data.
    basis=None
    if all(number(context.get(k)) is not None for k in ['spot_change5','basis_change5']):
        basis=5*(d*context['spot_change5']>0 and d*context['basis_change5']>0)
    earned=score_ma+score_rps+score_breakout+score_quality+(funding or 0)+(structure or 0)+(basis or 0)
    available=75+(15 if funding is not None else 0)+(5 if structure is not None else 0)+(5 if basis is not None else 0)
    prior_atr=data.atr_ratio.iloc[-25:-5]
    hits={
        'ma_cross':bool(cross.tail(10).any()),
        'rps_jump':bool(rps[20]>=settings.startup_rps and rps_prev5<settings.startup_rps and rps[20]-rps_prev5>=10),
        'rps_lead':bool(rps[20]-rps[120]>=15 and rps[120]<90),
        'base_breakout':bool(fresh_break),
        'adx_rising':bool(12<=data.adx.iloc[-6]<=22 and row.adx>=settings.adx_min and row.adx_slope>=3),
        'atr_expansion':bool(prior_atr.lt(0.7).sum()>=5 and row.atr_ratio>1 and row.atr_change5>0.1),
        'oi_growth':bool(context['oi_change5']>0 and context['oi_change20']>0) if funding is not None else None,
        'mild_volume':bool(1.2<=context['volume_ratio']<=3) if funding is not None else None,
        'curve_strength':bool(d*context['spread_change5']>0) if structure is not None else None,
    }
    weights=dict(ma_cross=10,rps_jump=15,rps_lead=10,base_breakout=15,adx_rising=15,atr_expansion=15,oi_growth=10,mild_volume=5,curve_strength=5)
    startup_earned=sum(weights[k] for k,v in hits.items() if v is True)
    startup_available=sum(weights[k] for k,v in hits.items() if v is not None)
    startup_score=startup_earned/startup_available*100
    trend_score=earned/available*100
    hit_count=sum(v is True for v in hits.values())
    price_ok=oriented(row.close,row.ma20) and oriented(row.ma20,row.ma60) and d*row.slope20>0 and d*row.slope60>0
    quality_ok=row.adx>=settings.adx_min and di_ok
    confirmed=bool(price_ok and oriented(row.ma60,row.ma120) and quality_ok and rps[20]>=80 and rps[60]>=65)
    extension=d*(row.close-row.ma20)/row.atr14 if row.atr14>0 else float('inf')
    startup_gate=bool(price_ok and quality_ok and rps[20]>=settings.startup_rps and recent20)
    eligible=bool(startup_gate and hit_count>=settings.startup_hits and startup_score>=settings.startup_min
        and trend_score>=settings.trend_min and extension<=settings.max_extension_atr
        and available>=settings.min_coverage and startup_available>=settings.min_coverage)
    missing=[]
    if funding is None: missing.append('comparable_fixed_contract_funding')
    if structure is None: missing.append('fixed_pair_term_structure')
    if basis is None: missing.append('spot_basis')
    state='启动观察' if eligible else ('成熟/已确认趋势' if confirmed else '震荡/未确认')
    result=dict(direction='long' if d==1 else 'short',trend_earned=round(earned,2),trend_available=available,
        trend_score=round(trend_score,2),trend_coverage=available, startup_earned=startup_earned,
        startup_available=startup_available,startup_score=round(startup_score,2),startup_coverage=startup_available,
        startup_hits=hit_count,confirmed=confirmed,startup_eligible=eligible,state=state,
        extension_atr=round(extension,3),score_ma=score_ma,score_rps=round(score_rps,2),score_breakout=score_breakout,
        score_quality=round(score_quality,2),score_funding=funding,score_structure=structure,score_basis=basis,
        missing_modules=';'.join(missing),overextended=bool(extension>settings.max_extension_atr),
        volatility_extreme=bool(row.atr_percentile>=95),oi_scope=context.get('oi_scope','unavailable'))
    result.update({f'directional_rps{n}':round(float(rps[n]),2) for n in [20,60,120]})
    result.update({f'signal_{k}':v for k,v in hits.items()})
    return result


def rank_candidates(scores, category, settings):
    if scores.empty:
        return scores.copy()
    if category=='startup':
        eligible=scores[scores.startup_eligible.eq(True)]
        sort=['startup_score','trend_score','startup_hits']
    elif category=='trend':
        eligible=scores[scores.confirmed.eq(True)&scores.trend_score.ge(settings.trend_min)&scores.trend_coverage.ge(settings.min_coverage)]
        sort=['trend_score','startup_score']
    else:
        raise ValueError('category must be startup or trend')
    return eligible.sort_values(sort,ascending=False).head(settings.top).reset_index(drop=True)
