import unittest

import pandas as pd

from measured_move import detect_measured_moves, find_swings, measured_move_summary


def frame(prices, dates=None):
    dates = dates or [f'2026{index:04d}' for index in range(1, len(prices) + 1)]
    return pd.DataFrame({
        'trade_date': dates,
        'open': prices,
        'high': [price + 1 for price in prices],
        'low': [price - 1 for price in prices],
        'close': prices,
    })


# A=低点99(idx2) → B=高点131(idx6) → C=低点117(idx8)，随后第三段涨到 140
LONG_SHAPE = [120, 110, 100, 105, 110, 115, 130, 125, 118, 122, 128, 132, 135, 140]


class FindSwingsTests(unittest.TestCase):
    def test_alternating_extremes_only(self):
        swings = find_swings(frame([100, 90, 120, 105, 130]), 1)
        self.assertEqual([(point.kind, point.price) for point in swings],
                         [('low', 89), ('high', 121), ('low', 104)])

    def test_pivots_without_a_counter_pivot_between_them_keep_the_extreme(self):
        # idx2 与 idx6 都是低点且中间没有枢轴高点，合并后只保留更低的 97
        swings = find_swings(frame([130, 120, 100, 110, 112, 115, 98, 120, 125, 130, 135]), 2)
        self.assertEqual([point.price for point in swings if point.kind == 'low'], [97])

    def test_series_shorter_than_the_pivot_window_returns_empty(self):
        self.assertEqual(find_swings(frame([100, 101, 102]), 2), [])


class DetectMeasuredMovesTests(unittest.TestCase):
    def test_long_move_projects_leg1_from_the_pullback_low(self):
        moves = detect_measured_moves(frame(LONG_SHAPE), pivot_strength=1)
        self.assertEqual(len(moves), 1)
        move = moves[0]
        self.assertEqual(move.direction, 'long')
        self.assertEqual((move.leg1_start_price, move.leg1_end_price, move.pullback_end_price),
                         (99.0, 131.0, 117.0))
        self.assertAlmostEqual(move.pullback_depth_pct, 43.8, places=1)
        # 目标 = C + (B - A)
        self.assertAlmostEqual(move.target_price, 117 + (131 - 99), places=4)
        self.assertAlmostEqual(move.leg3_progress_pct, 71.9, places=1)

    def test_short_move_is_the_mirror_image(self):
        moves = detect_measured_moves(frame([300 - price for price in LONG_SHAPE]), pivot_strength=1)
        self.assertEqual(len(moves), 1)
        move = moves[0]
        self.assertEqual(move.direction, 'short')
        self.assertEqual((move.leg1_start_price, move.leg1_end_price, move.pullback_end_price),
                         (201.0, 169.0, 183.0))
        # 目标 = C - (A - B)
        self.assertAlmostEqual(move.target_price, 183 - (201 - 169), places=4)

    def test_leg3_not_started_yet_is_ignored(self):
        self.assertEqual(detect_measured_moves(frame(LONG_SHAPE + [112, 111]), pivot_strength=1), [])

    def test_target_already_overshot_is_ignored(self):
        self.assertEqual(detect_measured_moves(frame(LONG_SHAPE + [200]), pivot_strength=1), [])

    def test_pullback_deeper_than_62_percent_is_ignored(self):
        broken = [120, 110, 100, 105, 110, 115, 130, 125, 104, 108, 114, 120, 124, 128]
        self.assertEqual(detect_measured_moves(frame(broken), pivot_strength=1), [])

    def test_stale_pattern_outside_the_recency_window_is_ignored(self):
        prices = LONG_SHAPE + [140 + index * .1 for index in range(1, 61)]
        self.assertEqual(detect_measured_moves(frame(prices), pivot_strength=1), [])
        self.assertEqual(len(detect_measured_moves(frame(prices), pivot_strength=1, max_pullback_age_bars=999)), 1)

    def test_at_most_one_move_per_direction(self):
        moves = detect_measured_moves(frame(LONG_SHAPE), pivot_strength=1)
        self.assertEqual(len({move.direction for move in moves}), len(moves))

    def test_empty_and_insufficient_data_are_safe(self):
        self.assertEqual(detect_measured_moves(pd.DataFrame()), [])
        self.assertEqual(detect_measured_moves(frame([100, 101])), [])
        self.assertEqual(detect_measured_moves(frame([100, 101, 102, 103])), [])


class SummaryTests(unittest.TestCase):
    def test_summary_serialises_moves(self):
        summary = measured_move_summary(frame(LONG_SHAPE))
        self.assertTrue(summary['has_move'])
        self.assertEqual(len(summary['moves']), 1)
        self.assertEqual(summary['moves'][0]['direction'], 'long')
        self.assertEqual(summary['moves'][0]['leg1_start_date'], '20260003')

    def test_summary_without_move(self):
        summary = measured_move_summary(frame([100, 101, 102, 103]))
        self.assertFalse(summary['has_move'])
        self.assertEqual(summary['moves'], [])


if __name__ == '__main__':
    unittest.main()
