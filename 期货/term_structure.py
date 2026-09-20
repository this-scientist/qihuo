# -*- coding: utf-8 -*-
"""期限结构：只用 fut_daily 真实月合约未复权价格，绝不能用复权主连（fut_daily_adj）。

真实曲线 = 当日全部有流动性的月份合约；可交易曲线 = 剔除临近交割与异常价格后
按 OI 排序的主力/次主力/第三活跃。年化 Carry 使不同商品、不同价差可横向比较；
Carry 五日/二十日变化与符号翻转即"期限结构拐点"。
"""
import math
import re

DAYS_PER_MONTH = 365 / 12  # 月间隔换算自然日，跨商品可比
NEAR_DELIVERY_DAYS = 5  # 进入交割月前5个自然日内的合约不可用于可交易曲线
FLAT_EPSILON = 0.001  # 年化Carry绝对值0.1%以内视为平坦
MONTH_GAP_ERROR = 'Invalid contract delivery month'


def parse_month(code, reference_year):
    """LC2611→202611；郑商所三位码 '611'→202611、'001'→203001（年位循环 1-9,0）。"""
    match = re.search(r'(\d{3,4})\.', code)
    if not match:
        raise ValueError(MONTH_GAP_ERROR)
    digits = match.group(1)
    month = int(digits[-2:])
    if len(digits) == 4:
        year = 2000 + int(digits[:2])
    else:
        choices = [y for y in range(reference_year - 1, reference_year + 6) if y % 10 == int(digits[0])]
        if not choices:
            raise ValueError(MONTH_GAP_ERROR)
        year = choices[0]
    if not 1 <= month <= 12:
        raise ValueError(MONTH_GAP_ERROR)
    return year * 100 + month


def month_gap(near_month, far_month):
    gap = (far_month // 100 - near_month // 100) * 12 + (far_month % 100 - near_month % 100)
    if gap <= 0:
        raise ValueError(MONTH_GAP_ERROR)
    return gap


def annualized_carry(near_settle, far_settle, near_month, far_month):
    """Spread=近/远-1；Carry=Spread×365/月间隔天数。近>远为正（Backwardation）。"""
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in [near_settle, far_settle]):
        return None
    try:
        days = month_gap(near_month, far_month) * DAYS_PER_MONTH
    except ValueError:
        return None
    if far_settle <= 0:
        return None
    return (near_settle / far_settle - 1) * 365 / days


def structure_label(carry):
    if not isinstance(carry, (int, float)) or math.isfinite(carry) is False:
        return None
    if carry > FLAT_EPSILON:
        return 'Backwardation'
    if carry < -FLAT_EPSILON:
        return 'Contango'
    return '平坦'


def carry_momentum(series):
    """series 为按交易日升序的年化Carry列表（None跳过但保留位置意义）。

    flip5：最近5个有效值内符号翻转（含穿过平坦区）→ 期限结构拐点。
    """
    values = [v for v in series if isinstance(v, (int, float)) and math.isfinite(v)]
    if not values:
        return dict(carry=None, change5=None, change20=None, flip5=None)
    carry = values[-1]
    change5 = carry - values[-6] if len(values) >= 6 else None
    change20 = carry - values[-21] if len(values) >= 21 else None
    flip5 = None
    window = values[-5:]
    if len(window) >= 2:
        signs = ['+' if v > FLAT_EPSILON else ('-' if v < -FLAT_EPSILON else '0') for v in window]
        flip5 = len(set(signs)) > 1
    return dict(carry=carry, change5=change5, change20=change20, flip5=flip5)


def curvature(near_settle, mid_settle, far_settle):
    """蝶式曲率 (近+远-2×中)/中：正值=中间月被压低（两端高），负值=中间月凸起。"""
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in [near_settle, mid_settle, far_settle]):
        return None
    return (near_settle + far_settle - 2 * mid_settle) / mid_settle


def _numeric(frame, field):
    import pandas as pd
    values = pd.to_numeric(frame[field], errors='coerce')
    return values


def real_curve(snapshot, asof):
    """真实曲线：有成交、持仓与有效结算价的全部月份合约，剔除临近交割与零价休眠。"""
    import pandas as pd
    frame = snapshot.copy()
    if frame.empty:
        return frame
    for field in ['vol', 'oi', 'settle']:
        if field not in frame:
            raise ValueError(f'Missing field: {field}')
        frame[field] = _numeric(frame, field)
    frame['delivery_month'] = [parse_month(code, int(str(asof)[:4])) for code in frame.ts_code.astype(str)]
    frame['days_to_delivery'] = [
        (pd.Timestamp(str(m)[:4] + '-' + str(m)[4:6] + '-' + '01') - pd.Timestamp(str(asof)[:4] + '-' + str(asof)[4:6] + '-' + str(asof)[6:])).days
        for m in frame.delivery_month]
    liquid = frame[(frame.vol > 0) & (frame.oi > 0) & (frame.settle > 0)
        & (frame.days_to_delivery > NEAR_DELIVERY_DAYS)
        & (frame.settle.map(lambda v: isinstance(v, (int, float)) and math.isfinite(v)))]
    return liquid.sort_values(['delivery_month', 'ts_code']).reset_index(drop=True)


def tradable_curve(liquid, top=3):
    """可交易曲线：按 OI 降序选主力/次主力/第三活跃（角色=流动性排名），输出按期限升序。

    Carry/曲率计算取期限首尾（curve_metrics），与角色无关——近月未必是主力。
    """
    roles = ['主力', '次主力', '第三活跃']
    picked = liquid.sort_values(['oi', 'vol'], ascending=False).head(top)
    entries = []
    for index, row in picked.iterrows():
        entries.append(dict(role=roles[len(entries)], ts_code=row.ts_code, delivery_month=int(row.delivery_month),
            days_to_delivery=int(row.days_to_delivery), settle=round(float(row.settle), 4),
            vol=int(row.vol), oi=int(row.oi)))
    return sorted(entries, key=lambda r: r['delivery_month'])


def curve_metrics(rows):
    """从可交易曲线（≥2档）派生：近远年化Carry、结构标签、三档曲率。"""
    if len(rows) < 2:
        return dict(carry=None, structure=None, curvature=None, near_code=rows[0]['ts_code'] if rows else None, far_code=None)
    near, far = rows[0], rows[-1]
    mid = rows[1] if len(rows) >= 3 else None
    carry = annualized_carry(near['settle'], far['settle'], near['delivery_month'], far['delivery_month'])
    return dict(carry=carry, structure=structure_label(carry),
        curvature=curvature(near['settle'], mid['settle'], far['settle']) if mid else None,
        near_code=near['ts_code'], far_code=far['ts_code'])
