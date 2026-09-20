# -*- coding: utf-8 -*-
import unittest
import pandas as pd
from term_structure import (parse_month, month_gap, annualized_carry, structure_label,
    carry_momentum, curvature, real_curve, tradable_curve, curve_metrics)
from option_scanner import scan_one

def snapshot_row(code, settle, vol, oi):
    return dict(ts_code=code, settle=settle, vol=vol, oi=oi, close=settle)

class TermStructureTests(unittest.TestCase):
    def test_parse_month_handles_four_digit_and_czce_cycle(self):
        self.assertEqual(parse_month('LC2611.GFE', 2026), 202611)
        self.assertEqual(parse_month('TA611.ZCE', 2026), 202611)
        self.assertEqual(parse_month('TA501.ZCE', 2026), 202501)
        self.assertEqual(parse_month('TA001.ZCE', 2026), 203001)
        with self.assertRaises(ValueError):
            parse_month('LC.GFE', 2026)
        with self.assertRaises(ValueError):
            parse_month('LC2613.GFE', 2026)

    def test_annualized_carry_matches_manual_example(self):
        # 碳酸锂：近月75000 / 远月72800，相差3个月 → 年化约12.1%（用户示例口径≈12.25%）。
        carry = annualized_carry(75000, 72800, 202610, 202701)
        self.assertAlmostEqual(carry, (75000 / 72800 - 1) * 365 / (3 * 365 / 12), places=10)
        self.assertGreater(carry, 0.11)
        self.assertLess(carry, 0.13)
        self.assertEqual(month_gap(202610, 202701), 3)
        # 反向：近月低于远月 → 负Carry（Contango）。
        self.assertLess(annualized_carry(72800, 75000, 202610, 202701), 0)
        self.assertIsNone(annualized_carry(75000, 0, 202610, 202701))
        self.assertIsNone(annualized_carry(75000, 72800, 202611, 202611))

    def test_structure_label_with_flat_band(self):
        self.assertEqual(structure_label(0.12), 'Backwardation')
        self.assertEqual(structure_label(-0.02), 'Contango')
        self.assertEqual(structure_label(0.0005), '平坦')
        self.assertIsNone(structure_label(None))

    def test_carry_momentum_detects_flip_within_five_days(self):
        rising = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
        momentum = carry_momentum(rising)
        self.assertFalse(momentum['flip5'])
        self.assertAlmostEqual(momentum['change5'], 0.05, places=10)
        collapsing = [0.082, 0.061, 0.038, 0.014, -0.01, -0.02]
        self.assertTrue(carry_momentum(collapsing)['flip5'])
        self.assertIsNone(carry_momentum([0.01])['change20'])
        self.assertIsNone(carry_momentum([None, None])['carry'])

    def test_curvature_sign(self):
        # 中间月被压低 → 正曲率；中间月凸起 → 负曲率。
        self.assertGreater(curvature(100, 95, 110), 0)
        self.assertLess(curvature(100, 106, 110), 0)
        self.assertIsNone(curvature(100, None, 110))

    def test_real_curve_filters_dormant_and_near_delivery(self):
        asof = '20260911'
        frame = pd.DataFrame([
            snapshot_row('LC2610.GFE', 75000, 80000, 60000),   # 202610：距交割>5天，有效
            snapshot_row('LC2701.GFE', 72800, 300000, 250000),
            snapshot_row('LC2703.GFE', 71500, 80000, 70000),
            snapshot_row('LC2609.GFE', 76000, 100, 0),         # 临近交割且无持仓：剔除
            snapshot_row('LC2705.GFE', 0, 5000, 5000),         # 零价休眠：剔除
            snapshot_row('LC2707.GFE', 70000, 0, 90000),       # 无成交：剔除
        ])
        liquid = real_curve(frame, asof)
        self.assertEqual(sorted(liquid.ts_code), ['LC2610.GFE', 'LC2701.GFE', 'LC2703.GFE'])
        rows = tradable_curve(liquid)
        # 角色=流动性（OI）排名；输出顺序=期限升序。2701的OI最大→主力，即使它不是最近月。
        roles = {r['ts_code']: r['role'] for r in rows}
        self.assertEqual(roles, {'LC2701.GFE': '主力', 'LC2703.GFE': '次主力', 'LC2610.GFE': '第三活跃'})
        self.assertEqual([r['delivery_month'] for r in rows], sorted(r['delivery_month'] for r in rows))
        metrics = curve_metrics(rows)
        self.assertEqual(metrics['structure'], 'Backwardation')  # 75000>72800（近2610为期限首档）
        self.assertIsNotNone(metrics['curvature'])

    def test_scanner_term_item_graded_and_resonance(self):
        base = dict(ts_code='LC.GFEX', name='碳酸锂', sector='新能源金属', main_code='LC2611.GFE',
            direction='short', phase='趋势启动', directional_rps20=92, rps20=8.0, rps20_prev5=22.0,
            adx=22, adx_slope=4, plus_di=15, minus_di=25, break20_up=False, break20_down=True,
            break55_up=False, break55_down=True, signal_base_breakout=True,
            oi_change5=0.05, oi_change20=0.1, volume_ratio=1.5, return5=-0.03,
            spot_change5=None, basis_change5=None, extension_atr=1.0, atr_percentile=50)
        short_aligned = dict(base, carry_annualized=-12.0, carry_change5=-3.0, carry_change20=-6.0,
            structure='Contango', structure_flip5=False, spread_change5=None)
        result = scan_one(short_aligned, 'short', [])
        self.assertEqual(result['items']['term']['score'], 10)  # 对齐6 + 显著2 + 动量2
        momentum_against = dict(short_aligned, carry_change5=2.0)
        self.assertEqual(scan_one(momentum_against, 'short', [])['items']['term']['score'], 8)
        plain = dict(short_aligned, carry_annualized=-0.5, carry_change5=0.0)
        self.assertEqual(scan_one(plain, 'short', [])['items']['term']['score'], 6)
        # 缺Carry时回退到旧spread_change5二值口径。
        legacy = dict(base, spread_change5=-100.0)
        self.assertEqual(scan_one(legacy, 'short', [])['items']['term']['score'], 10)
        missing = scan_one(base, 'short', [])
        self.assertEqual(missing['items']['term']['status'], 'missing')
        self.assertEqual(missing['signals']['term'], None)
        # 四重共振：RPS拐点+ADX拐头+OI增加+期限拐点 全部成立（空头）。
        resonant = scan_one(short_aligned, 'short', [])
        self.assertTrue(resonant['resonance'])
        self.assertEqual(set(resonant['resonance_parts']), {'rps拐点', 'ADX拐头', 'OI增加', '期限拐点'})
        broken = scan_one(dict(short_aligned, carry_change5=3.0), 'short', [])
        self.assertFalse(broken['resonance'])
        self.assertEqual(broken['metrics']['structure'], 'Contango')
        self.assertEqual(broken['curve'], [])

if __name__ == '__main__':
    unittest.main()
