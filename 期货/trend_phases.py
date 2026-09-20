"""Causal phase classification, separate from original score/ranking gates."""
import math
from dataclasses import dataclass, asdict
import pandas as pd


@dataclass(frozen=True)
class PhaseSettings:
    adx_min: float=20
    forming_adx: float=15
    strong_rps: float=65
    startup_rps: float=90
    max_extension_atr: float=3
    startup_adx_rise: float=3
    startup_rps_rise: float=10


def phase_for_row(row,settings=None):
    settings=settings or PhaseSettings()
    required=['close','ma20','ma60','ma120','slope20','slope60','adx','plus_di','minus_di','rps20','atr14']
    if any(pd.isna(row.get(k)) or not math.isfinite(float(row[k])) for k in required):
        return dict(phase='数据不足',trend_direction='neutral',phase_reason='关键技术指标缺失',technical_start=False)
    c,m20,m60=row['close'],row['ma20'],row['ma60']
    long=c>m20>m60 and row['slope20']>0 and row['slope60']>0
    short=c<m20<m60 and row['slope20']<0 and row['slope60']<0
    d=1 if long else -1 if short else 1 if c>m20 and row['slope20']>0 and row['plus_di']>row['minus_di'] else -1 if c<m20 and row['slope20']<0 and row['plus_di']<row['minus_di'] else 0
    direction='long' if d==1 else 'short' if d==-1 else 'neutral'
    strength=row['rps20'] if d>=0 else 100-row['rps20']
    di_ok=d*(row['plus_di']-row['minus_di'])>0
    strong=(long or short) and di_ok and row['adx']>=settings.adx_min and strength>=settings.strong_rps
    extension=d*(c-m20)/row['atr14'] if d and row['atr14']>0 else None
    prior=row.get('adx_prev5',float('nan'))
    prev_strength=row.get('rps20_prev5',float('nan'))
    if d<0:prev_strength=100-prev_strength
    adx_rise=12<=prior<=22 and row.get('adx_slope',0)>=settings.startup_adx_rise
    rps_rise=prev_strength<settings.startup_rps and strength-prev_strength>=settings.startup_rps_rise
    fresh=row.get(f'fresh20_{"up" if d==1 else "down"}',row.get('fresh_break',False))
    startup=bool(strong and fresh and adx_rise and rps_rise and strength>=settings.startup_rps)
    if not d:
        phase='震荡' if row['adx']<settings.adx_min else '趋势减弱'
        reason='中短期价格、均线和DI方向不一致'
    elif not strong:
        phase='方向形成' if row['adx']>=settings.forming_adx and di_ok else '趋势减弱'
        reason='价格出现方向，但均线斜率、ADX或相对强度尚未全部确认'
    elif extension is not None and extension>settings.max_extension_atr:
        phase='过度延伸';reason=f'方向已确认，偏离MA20 {extension:.2f} ATR'
    elif startup:
        phase='趋势启动';reason='新基底突破、低位ADX抬升、RPS跃升，且未过度偏离'
    elif d*(m60-row['ma120'])>0:
        phase='持续趋势';reason='中长期均线、斜率、ADX、DI及方向RPS一致，不要求近期再次突破'
    else:
        phase='中短期强势';reason='中短期趋势已确认，MA60与MA120完整排列尚未完成'
    return dict(phase=phase,trend_direction=direction,phase_reason=reason,
        technical_start=bool(startup and phase!='过度延伸'),phase_extension_atr=round(extension,3) if extension is not None else None)


def enrich_technical(data,direction):
    d=1 if direction=='long' else -1
    df=data.copy()
    for n in [20,60,120]:df[f'directional_rps{n}']=df[f'rps{n}'] if d==1 else 100-df[f'rps{n}']
    df['adx_prev5']=df.adx.shift(5)
    for side in ['up','down']:
        df[f'recent20_{side}']=df[f'break20_{side}'].rolling(5,min_periods=1).max().astype(bool)
        df[f'fresh20_{side}']=df[f'recent20_{side}'] & df[f'break20_{side}'].shift(5).rolling(20,min_periods=20).sum().le(2)
    df['recent_break20']=df[f'recent20_{"up" if d==1 else "down"}']
    df['fresh_break']=df[f'fresh20_{"up" if d==1 else "down"}']
    df['extension_atr']=d*(df.close-df.ma20)/df.atr14.replace(0,float('nan'))
    return df
