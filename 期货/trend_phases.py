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
    ema_medium_slope_atr: float=.25


def phase_for_row(row,settings=None):
    settings=settings or PhaseSettings()
    required=['close','ema20','ema20_slope5_atr','ema20_distance_atr','adx','plus_di','minus_di','rps20','atr14']
    if any(pd.isna(row.get(k)) or not math.isfinite(float(row[k])) for k in required):
        return dict(phase='数据不足',trend_direction='neutral',phase_reason='关键技术指标缺失',technical_start=False)
    long=row['ema20_distance_atr']>=0 and row['ema20_slope5_atr']>=settings.ema_medium_slope_atr
    short=row['ema20_distance_atr']<=0 and row['ema20_slope5_atr']<=-settings.ema_medium_slope_atr
    d=1 if long and row['plus_di']>row['minus_di'] else -1 if short and row['plus_di']<row['minus_di'] else 0
    direction='long' if d==1 else 'short' if d==-1 else 'neutral'
    strength=row['rps20'] if d>=0 else 100-row['rps20']
    di_ok=d*(row['plus_di']-row['minus_di'])>0
    strong=bool(d and di_ok and row['adx']>=settings.adx_min and strength>=settings.strong_rps)
    extension=d*row['ema20_distance_atr'] if d else None
    prior=row.get('adx_prev5',float('nan'))
    prev_strength=row.get('rps20_prev5',float('nan'))
    if d<0:prev_strength=100-prev_strength
    adx_rise=12<=prior<=22 and row.get('adx_slope',0)>=settings.startup_adx_rise
    rps_rise=prev_strength<settings.startup_rps and strength-prev_strength>=settings.startup_rps_rise
    fresh=row.get(f'fresh20_{"up" if d==1 else "down"}',row.get('fresh_break',False))
    startup=bool(strong and fresh and adx_rise and rps_rise and strength>=settings.startup_rps)
    if not d:
        phase='震荡' if row['adx']<settings.adx_min else '趋势减弱'
        reason='价格位置、EMA20趋势强度与DI方向不一致'
    elif not strong:
        phase='方向形成' if row['adx']>=settings.forming_adx and di_ok else '趋势减弱'
        reason='价格与EMA20出现方向，但EMA20强度、ADX或相对强度尚未全部确认'
    elif extension is not None and extension>settings.max_extension_atr:
        phase='过度延伸';reason=f'方向已确认，偏离EMA20 {extension:.2f} ATR'
    elif startup:
        phase='趋势启动';reason='新基底突破、低位ADX抬升、RPS跃升，且未过度偏离'
    else:
        phase='持续趋势';reason='价格位置、EMA20趋势强度、ADX、DI及方向RPS一致，不要求近期再次突破'
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
    df['extension_atr']=d*df.ema20_distance_atr
    return df
