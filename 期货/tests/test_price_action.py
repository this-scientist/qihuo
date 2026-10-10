import unittest

import pandas as pd

from price_action import price_action_summary, structure_rr


def frame(closes):
    rows = []
    for index, close in enumerate(closes, start=1):
        rows.append(dict(
            trade_date=f'202610{index:02d}',
            open=float(close) - 0.5,
            high=float(close),
            low=float(close) - 2,
            close=float(close),
            vol=1000 + index,
        ))
    return pd.DataFrame(rows)


class PriceActionTests(unittest.TestCase):
    def test_upside_60_day_breakout_creates_model_a_signal(self):
        closes = [100.0] * 60 + [103.0]
        result = price_action_summary(frame(closes))
        self.assertEqual(result['structure_side'], 'bullish')
        self.assertEqual(result['lifecycle'], 'start')
        self.assertEqual(result['event_type'], 'breakout')
        self.assertEqual(result['trade_model'], 'A')
        self.assertEqual(result['key_level'], 100.0)
        self.assertEqual(result['entry_reference'], 103.0)
        self.assertGreater(result['breakout_quality']['breakout_atr_multiple'], 0.3)
        self.assertTrue(result['breakout_quality']['close_in_top_quarter'])

    def test_flat_range_without_breakout_has_no_trade_model(self):
        result = price_action_summary(frame([100, 101, 100, 101, 100, 101] * 12))
        self.assertEqual(result['structure_side'], 'range')
        self.assertEqual(result['lifecycle'], 'base')
        self.assertEqual(result['event_type'], 'none')
        self.assertIsNone(result['trade_model'])
        self.assertFalse(result['eligible_for_option_eval'])

    def test_structure_rr_uses_target_entry_and_invalidation(self):
        self.assertAlmostEqual(structure_rr(110000, 101000, 98500), 3.6)
        self.assertIsNone(structure_rr(110000, 101000, 101000))


if __name__ == '__main__':
    unittest.main()
