# -*- coding: utf-8 -*-
"""本地支撑/压力位：窗口极值、方向归属、合并强度、ATR 通道、无未来函数、数据不足降级。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from price_levels import compute_levels, normalize_rows, wilder_atr


def flat_rows(count=60, price=100.0, low=99.0, high=101.0, vol=1000.0, start=1):
    return [dict(trade_date='2026%04d' % (start + index), open=price, high=high, low=low,
                 close=price, vol=vol, main_code='X2701.TEST') for index in range(count)]


class PriceLevelTests(unittest.TestCase):
    def test_supports_below_and_resistance_above(self):
        rows = flat_rows(60)
        result = compute_levels(rows, last=100.0, atr14=2.0)
        self.assertTrue(result['support'], '应有支撑位')
        self.assertTrue(result['resistance'], '应有压力位')
        for item in result['support']:
            self.assertLess(item['price'], 100.0)
            self.assertIn(item['strength'], ['强', '中', '弱'])
        for item in result['resistance']:
            self.assertGreater(item['price'], 100.0)

    def test_window_extremes_reported_with_source(self):
        rows = flat_rows(60)
        rows[-1].update(low=98.0, high=102.0)
        result = compute_levels(rows, last=100.0, atr14=2.0)
        sources = [source for item in result['support'] + result['resistance'] for source in item['sources']]
        self.assertIn('近20日低点', sources)
        self.assertIn('近55日高点', sources)

    def test_atr_bands_present(self):
        rows = flat_rows(60)
        result = compute_levels(rows, last=100.0, atr14=3.0)
        prices = [item['price'] for item in result['support']]
        self.assertIn(97.0, [round(price, 4) for price in prices])

    def test_coincident_levels_merge_and_upgrade_strength(self):
        # 40 根在 90 附近反复触及，使近20/55日低点、整数关口与密集区重合。
        rows = flat_rows(60, price=100.0, low=90.0, high=101.0, vol=5000.0)
        result = compute_levels(rows, last=100.0, atr14=2.0)
        merged = [item for item in result['support'] if len(item['sources']) >= 2]
        self.assertTrue(merged, '重合价位应合并并记录多个来源')
        self.assertIn(merged[0]['strength'], ['强', '中'])

    def test_no_lookahead_ignores_last_bar_crash(self):
        rows = flat_rows(60, price=100.0, low=99.0, high=101.0)
        rows[-1].update(close=50.0, low=49.0, high=51.0)
        result = compute_levels(rows, last=100.0, atr14=2.0)
        self.assertNotIn(49.0, [round(item['price'], 2) for item in result['support']])

    def test_insufficient_history_degrades_with_note(self):
        result = compute_levels(flat_rows(10), last=100.0, atr14=1.0)
        self.assertEqual(result['support'], [])
        self.assertEqual(result['resistance'], [])
        self.assertEqual(result['coverage'], 0)
        self.assertTrue(result['notes'])

    def test_missing_long_window_is_noted(self):
        result = compute_levels(flat_rows(60), last=100.0, atr14=2.0)
        self.assertTrue(any('250' in note for note in result['notes']))

    def test_dataframe_and_list_inputs_agree(self):
        import pandas as pd
        rows = flat_rows(60)
        frame = pd.DataFrame(rows)
        from_list = compute_levels(rows, last=100.0, atr14=2.0)
        from_frame = compute_levels(frame, last=100.0, atr14=2.0)
        self.assertEqual([item['price'] for item in from_list['support']],
                         [item['price'] for item in from_frame['support']])

    def test_invalid_rows_are_dropped(self):
        rows = flat_rows(40) + [dict(trade_date='20261231', high=None, low=1.0, close=1.0, vol=1.0)]
        cleaned = normalize_rows(rows)
        self.assertEqual(len(cleaned), 40)

    def test_wilder_atr_requires_enough_bars(self):
        self.assertIsNone(wilder_atr(flat_rows(5)))
        self.assertIsNotNone(wilder_atr(flat_rows(30)))

    def test_main_code_switch_is_noted(self):
        rows = flat_rows(40)
        for row in rows[:10]:
            row['main_code'] = 'X2601.TEST'
        result = compute_levels(rows, last=100.0, atr14=2.0)
        self.assertTrue(any('换月' in note for note in result['notes']))


if __name__ == '__main__':
    unittest.main()
