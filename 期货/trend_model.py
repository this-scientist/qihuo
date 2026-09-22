"""Price-only swing trend. Public inputs use percent, not fractional returns."""
import math

MODEL_VERSION = 'price-swing-v1'
WEIGHTS = {'price': 40, 'momentum': 35, 'di': 25}


def finite(value):
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def clip(value, low=-1.0, high=1.0):
    return max(low, min(high, float(value)))


def price_trend(row, omit=None):
    fields = ['close', 'ma20', 'ma60', 'atr14', 'slope20', 'return5',
              'return20', 'plus_di', 'minus_di', 'adx']
    if not all(finite(row.get(k)) for k in fields) or min(float(row[k]) for k in fields[:4]) <= 0:
        return dict(side='neutral', score=None, components={}, status='missing')
    c, ma20, ma60, atr = (float(row[k]) for k in fields[:4])
    # Correlated features share a fixed group budget; none gets an extra vote.
    price = (clip((c-ma20)/(2*atr)) + clip((ma20-ma60)/(3*atr))
             + clip(float(row['slope20'])*ma20/(100*atr))) / 3
    atr_pct = atr / c * 100
    momentum = (clip(float(row['return5'])/(atr_pct*math.sqrt(5)))
                + clip(float(row['return20'])/(atr_pct*math.sqrt(20)))) / 2
    plus, minus = float(row['plus_di']), float(row['minus_di'])
    di = clip(2*(plus-minus)/(plus+minus)) if plus+minus > 0 else 0
    di *= clip((float(row['adx'])-10)/20, 0, 1)
    values = dict(price=price, momentum=momentum, di=di)
    weights = {key: weight for key, weight in WEIGHTS.items() if key != omit}
    components = {key: round(values[key]*weight*100/sum(weights.values()), 4)
                  for key, weight in weights.items()}
    score = round(sum(components.values()), 2)
    side = 'long' if score >= 25 else 'short' if score <= -25 else 'neutral'
    return dict(side=side, score=score, components=components, status='ok')


def burst_index(row, side):
    """Underlying expansion evidence, not option return or success probability."""
    sign = 1 if side == 'long' else -1 if side == 'short' else 0
    direction = 'up' if sign > 0 else 'down'
    parts = {}
    breakout = row.get(f'break20_{direction}')
    if sign and breakout is not None:
        parts['breakout'] = (25 if breakout is True else 0, 25)
    for key, weight, value in [
        ('rps_accel', 20, sign*float(row['rps_accel'])/20 if finite(row.get('rps_accel')) else None),
        ('adx', 20, float(row['adx_slope'])/5 if finite(row.get('adx_slope')) else None),
        ('atr', 15, float(row['atr_change5'])/20 if finite(row.get('atr_change5')) else None),
        ('volume', 10, (float(row['volume_ratio'])-1)/1 if finite(row.get('volume_ratio')) else None),
        ('oi', 10, (float(row['oi_change5'])/5 if sign*float(row['return5']) > 0 else 0)
         if finite(row.get('oi_change5')) and finite(row.get('return5')) else None),
    ]:
        if value is not None:
            parts[key] = (round(weight*clip(value, 0, 1), 2), weight)
    coverage = sum(v[1] for v in parts.values())
    earned = sum(v[0] for v in parts.values())
    # Missing evidence never inflates the score by renormalizing it upward.
    return dict(burst_score=round(earned, 2) if sign and coverage else None,
                burst_coverage=coverage, burst_components={k:v[0] for k,v in parts.items()})
