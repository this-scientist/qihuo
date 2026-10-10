import unittest

import pandas as pd

from ml_cycle_labels import classify_cycle_row, signal_bar_for_row


def frame(closes, opens=None, highs=None, lows=None):
    opens = opens or closes
    highs = highs or [max(o, c) + 1 for o, c in zip(opens, closes)]
    lows = lows or [min(o, c) - 1 for o, c in zip(opens, closes)]
    df = pd.DataFrame(dict(open=opens, high=highs, low=lows, close=closes, vol=[100] * len(closes), oi=[1000] * len(closes)))
    df["trade_date"] = [f"202601{i+1:02d}" for i in range(len(df))]
    return df


class CycleLabelTests(unittest.TestCase):
    def test_breakout_spike_after_range_expansion(self):
        df = frame([100, 101, 100.5, 101.2, 100.8, 106], opens=[100, 100.5, 101, 100.8, 101, 102], highs=[101, 102, 101.5, 102, 101.8, 107], lows=[99, 100, 99.8, 100, 100.2, 101.5])
        result = classify_cycle_row(df, len(df) - 1)

        self.assertEqual(result["market_cycle_phase"], "BREAKOUT_SPIKE")
        self.assertEqual(result["direction"], "long")

    def test_tight_channel_for_orderly_trend(self):
        df = frame([100, 102, 104, 106, 108, 110, 112], opens=[99, 101, 103, 105, 107, 109, 111])
        result = classify_cycle_row(df, len(df) - 1)

        self.assertEqual(result["market_cycle_phase"], "TIGHT_CHANNEL")
        self.assertEqual(result["direction"], "long")

    def test_trading_range_when_overlap_dominates(self):
        df = frame([100, 101, 99.8, 100.7, 100.2, 101.1, 100.4], opens=[100, 100.5, 100.2, 100, 100.8, 100.3, 100.9])
        result = classify_cycle_row(df, len(df) - 1)

        self.assertEqual(result["market_cycle_phase"], "TRADING_RANGE")
        self.assertEqual(result["direction"], "neutral")

    def test_signal_bar_identifies_trend_and_reversal_bars(self):
        trend = signal_bar_for_row(pd.Series(dict(open=100, high=108, low=99, close=107, ema20=101, atr14=4)))
        reversal = signal_bar_for_row(pd.Series(dict(open=106, high=108, low=99, close=100, ema20=104, atr14=4)))

        self.assertEqual(trend, "BULL_TREND_BAR")
        self.assertEqual(reversal, "BEAR_REVERSAL_BAR")


if __name__ == "__main__":
    unittest.main()
