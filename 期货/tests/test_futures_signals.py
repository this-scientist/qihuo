import unittest
import pandas as pd

from futures_signals import signal_for_history


def frame(closes):
    rows = []
    for index, close in enumerate(closes, start=1):
        rows.append(dict(
            trade_date=f'202609{index:02d}',
            open=float(close) - 0.5,
            high=float(close) + 1,
            low=float(close) - 1,
            close=float(close),
        ))
    return pd.DataFrame(rows)


class FuturesSignalTests(unittest.TestCase):
    def test_down_to_up_reversal_is_first_buy(self):
        signal = signal_for_history(frame([10, 9, 8, 11]))
        self.assertEqual(signal['signal_code'], 'BUY1')
        self.assertEqual(signal['signal_label'], '一买')
        self.assertEqual(signal['signal_side'], 'long')

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


if __name__ == '__main__':
    unittest.main()
