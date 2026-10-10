import unittest
import pandas as pd

from futures_signals import signal_for_history


def frame(closes, close_on_high=False):
    rows = []
    for index, close in enumerate(closes, start=1):
        high = float(close) if close_on_high else float(close) + 1
        low = float(close) - 2 if close_on_high else float(close) - 1
        rows.append(dict(
            trade_date=f'202609{index:02d}',
            open=float(close) - 0.5,
            high=high,
            low=low,
            close=float(close),
            vol=1000 + index,
        ))
    return pd.DataFrame(rows)


class FuturesSignalTests(unittest.TestCase):
    def test_down_to_up_reversal_is_first_buy(self):
        signal = signal_for_history(frame([10, 9, 8, 11]))
        self.assertEqual(signal['signal_code'], 'BUY1')
        self.assertEqual(signal['signal_label'], '一买')
        self.assertEqual(signal['signal_side'], 'long')

    def test_first_buy_below_falling_ema_is_downtrend_rebound(self):
        signal = signal_for_history(frame([30, 29, 28, 27, 26, 25, 24, 23, 22, 21,
                                           20, 19, 18, 17, 16, 15, 14, 12, 11, 13]))
        self.assertEqual(signal['signal_code'], 'BUY1')
        self.assertEqual(signal['signal_context'], 'downtrend_rebound')
        self.assertEqual(signal['signal_context_label'], '下跌趋势反弹一买')

    def test_first_buy_above_rising_ema_is_cycle_reversal(self):
        signal = signal_for_history(frame([10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
                                           20, 21, 22, 23, 24, 25, 24, 23, 22, 26]))
        self.assertEqual(signal['signal_code'], 'BUY1')
        self.assertEqual(signal['signal_context'], 'cycle_reversal')
        self.assertEqual(signal['signal_context_label'], '大周期反转一买')

    def test_up_to_down_reversal_is_first_sell(self):
        signal = signal_for_history(frame([8, 9, 10, 7]))
        self.assertEqual(signal['signal_code'], 'SELL1')
        self.assertEqual(signal['signal_label'], '一卖')
        self.assertEqual(signal['signal_side'], 'short')

    def test_second_buy_confirms_next_long_bar(self):
        signal = signal_for_history(frame([10, 9, 8, 11, 12]))
        self.assertEqual(signal['signal_code'], 'BUY2')
        self.assertEqual(signal['signal_label'], '二买')
        self.assertEqual(signal['signal_side'], 'long')

    def test_second_sell_confirms_next_short_bar(self):
        signal = signal_for_history(frame([8, 9, 10, 7, 6]))
        self.assertEqual(signal['signal_code'], 'SELL2')
        self.assertEqual(signal['signal_label'], '二卖')
        self.assertEqual(signal['signal_side'], 'short')

    def test_pivot_levels_follow_original_formula(self):
        signal = signal_for_history(frame([10, 9, 8, 11]))
        self.assertAlmostEqual(signal['today_resistance'], 8.8)
        self.assertAlmostEqual(signal['today_support'], 6.8)
        self.assertAlmostEqual(signal['tomorrow_breakout'], 12.9)
        self.assertAlmostEqual(signal['tomorrow_reversal'], 8.9)

    def test_signal_exposes_price_action_summary(self):
        signal = signal_for_history(frame([100.0] * 60 + [103.0], close_on_high=True))
        self.assertIn('price_action', signal)
        self.assertEqual(signal['price_action']['event_type'], 'breakout')
        self.assertEqual(signal['price_action']['trade_model'], 'A')
        self.assertEqual(signal['structure_side'], 'bullish')
        self.assertEqual(signal['event_type'], 'breakout')
        self.assertTrue(signal['eligible_for_option_eval'])


if __name__ == '__main__':
    unittest.main()
