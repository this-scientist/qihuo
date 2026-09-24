"""Black76 REFERENCE analytics on real futures prices; not executable quotes."""
import math
from datetime import datetime


def black76(future,strike,time,rate,volatility,side):
    if future<=0 or strike<=0 or time<=0 or volatility<=0:return None
    sigma=volatility*math.sqrt(time);d1=(math.log(future/strike)+.5*sigma*sigma)/sigma;d2=d1-sigma
    cdf=lambda x:.5*(1+math.erf(x/math.sqrt(2)))
    discount=math.exp(-rate*time)
    return discount*(future*cdf(d1)-strike*cdf(d2)) if side=='C' else discount*(strike*cdf(-d2)-future*cdf(-d1))


def implied_vol(premium,future,strike,time,rate,side):
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in [premium,future,strike,time,rate]) or min(premium,future,strike,time)<=0 or side not in ['C','P']:return None
    discount=math.exp(-rate*time);lower=discount*max(0,future-strike if side=='C' else strike-future);upper=discount*(future if side=='C' else strike)
    if premium<=lower or premium>=upper:return None
    low,high=1e-6,5.
    if black76(future,strike,time,rate,high,side)<premium:return None
    for _ in range(60):
        mid=(low+high)/2
        if black76(future,strike,time,rate,mid,side)>premium:high=mid
        else:low=mid
    return (low+high)/2


def greeks(future,strike,time,rate,volatility,side):
    """Black76 REFERENCE greeks; vega per 1 vol point, theta per calendar day."""
    if future<=0 or strike<=0 or time<=0 or volatility<=0 or side not in ['C','P']:return None
    sigma=volatility*math.sqrt(time);d1=(math.log(future/strike)+.5*sigma*sigma)/sigma;d2=d1-sigma
    pdf=math.exp(-.5*d1*d1)/math.sqrt(2*math.pi);discount=math.exp(-rate*time)
    cdf=lambda x:.5*(1+math.erf(x/math.sqrt(2)))
    delta=discount*cdf(d1) if side=='C' else -discount*cdf(-d1)
    gamma=discount*pdf/(future*sigma)
    vega=discount*future*pdf*math.sqrt(time)/100
    theta=(discount*(-future*pdf*volatility/(2*math.sqrt(time))-rate*future*cdf(d1)) if side=='C'
        else discount*(-future*pdf*volatility/(2*math.sqrt(time))+rate*strike*cdf(-d2)))/365
    return dict(delta=delta,gamma=gamma,vega=vega,theta=theta)


def numeric(value):
    try:
        result=float(value);return result if math.isfinite(result) else None
    except (TypeError,ValueError):return None


def option_metrics(meta,quote,asof,future,rate=.02):
    maturity=str(meta.get('maturity_date',''));days=(datetime.strptime(maturity,'%Y%m%d')-datetime.strptime(asof,'%Y%m%d')).days
    strike=numeric(meta.get('exercise_price'));price=numeric(quote.get('close'));multiplier=numeric(meta.get('opt_multiplier'))
    if multiplier is None:multiplier=numeric(meta.get('per_unit'))
    if multiplier is not None and multiplier<=0:multiplier=None
    call_put=meta.get('call_put');iv=implied_vol(price,future,strike,days/365,rate,call_put) if strike else None
    greek=greeks(future,strike,days/365,rate,iv,call_put) if iv is not None else None
    exercise=str(meta.get('exercise_type','未知'))
    return dict(ts_code=meta['ts_code'],name=meta.get('name'),underlying_code=meta.get('underlying_code'),
        exercise_price=strike,call_put=call_put,exercise_type=exercise,maturity_date=maturity,days_to_expiry=days,
        underlying_close=future,premium=price,multiplier=multiplier,premium_per_lot=price*multiplier if price is not None and multiplier else None,
        vol=numeric(quote.get('vol')),oi=numeric(quote.get('oi')),moneyness_pct=(strike/future-1)*100 if strike and future>0 else None,
        iv_reference=iv*100 if iv is not None else None,rate=rate,model='Black76日线参考',model_approximation='欧式' not in exercise,
        iv_status='参考值；美式/未知行权方式为欧洲模型近似' if iv is not None and '欧式' not in exercise else '参考值' if iv is not None else '无法由该日线价格反推',
        delta=greek['delta'] if greek else None,gamma=greek['gamma'] if greek else None,
        vega=greek['vega'] if greek else None,theta=greek['theta'] if greek else None,
        quote_date=asof,bid=None,ask=None,bid_ask_spread_pct=None,executable=False,
        status='日线观察，待核实实时盘口',break_even=strike+price if call_put=='C' else strike-price)
