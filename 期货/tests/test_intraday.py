import unittest

from intraday import (direction_quality, evaluate, position_band, price_scale, progress_of, rank)


def row_of(**overrides):
    base = dict(ts_code='CU.SHF', main_code='CU2610.SHF', name='铜', sector='有色与新能源',
                decision_side='long', state_v2='START', dir_score=60.0,
                close=100.0, raw_close=100.0,
                tomorrow_support=100.0, tomorrow_resistance=200.0,
                tomorrow_breakout=210.0, tomorrow_reversal=90.0)
    base.update(overrides)
    return base


def quote_of(last, **overrides):
    base = dict(last=last, bid=last - 5, ask=last + 5, pre_settle=last, change_pct=0.0,
                spread=10.0, time='11:02:24', age_seconds=12.0)
    base.update(overrides)
    return base


class PositionBandTests(unittest.TestCase):
    def test_bands_are_ordered_by_how_far_price_already_ran(self):
        self.assertEqual(position_band(-0.8)['key'], 'broken')
        self.assertEqual(position_band(-0.1)['key'], 'crossed')
        self.assertEqual(position_band(0.0)['key'], 'edge')
        self.assertEqual(position_band(0.3)['key'], 'edge')
        self.assertEqual(position_band(0.5)['key'], 'middle')
        self.assertEqual(position_band(0.9)['key'], 'far')
        self.assertEqual(position_band(1.0)['key'], 'far')
        self.assertEqual(position_band(1.2)['key'], 'broke')
        self.assertEqual(position_band(2.0)['key'], 'runaway')
        self.assertIsNone(position_band(None)['score'])

    def test_the_near_edge_outranks_a_fresh_breakout(self):
        self.assertGreater(position_band(0.1)['score'], position_band(1.1)['score'])
        self.assertGreater(position_band(1.1)['score'], position_band(1.6)['score'])


class ProgressTests(unittest.TestCase):
    def test_long_and_short_are_mirrored(self):
        self.assertAlmostEqual(progress_of('long', 100.0, 100.0, 200.0), 0.0)
        self.assertAlmostEqual(progress_of('long', 200.0, 100.0, 200.0), 1.0)
        self.assertAlmostEqual(progress_of('short', 200.0, 100.0, 200.0), 0.0)
        self.assertAlmostEqual(progress_of('short', 100.0, 100.0, 200.0), 1.0)

    def test_rejects_degenerate_inputs(self):
        self.assertIsNone(progress_of('neutral', 150.0, 100.0, 200.0))
        self.assertIsNone(progress_of('long', None, 100.0, 200.0))
        self.assertIsNone(progress_of('long', 150.0, None, 200.0))
        self.assertIsNone(progress_of('long', 150.0, 100.0, None))
        self.assertIsNone(progress_of('long', 0.0, 100.0, 200.0))

    def test_doji_box_has_no_meaningful_position(self):
        self.assertIsNone(progress_of('long', 100.0, 100.0, 100.0))
        self.assertIsNone(progress_of('long', 100.0, 100.0, 100.01))


class DirectionQualityTests(unittest.TestCase):
    def test_side_absent_in_the_daily_judgement_scores_zero(self):
        self.assertEqual(direction_quality(row_of(decision_side='neutral'))['score'], 0)
        self.assertEqual(direction_quality(row_of(decision_side=None))['score'], 0)

    def test_start_outranks_trend_and_exhaust(self):
        scores = [direction_quality(row_of(state_v2=state))['score']
                  for state in ['START', 'TREND', 'PREPARE', 'EXHAUST', 'WAIT']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_unknown_state_falls_back_instead_of_zero(self):
        self.assertEqual(direction_quality(row_of(state_v2='SOMETHING'))['score'], 40)


class EvaluateTests(unittest.TestCase):
    def test_combines_position_and_direction_with_the_declared_weights(self):
        entry = evaluate(row_of(), quote_of(100.0))
        self.assertEqual(entry['stance'], 'edge')
        self.assertEqual(entry['position_score'], 90)
        self.assertEqual(entry['direction_score'], 100)
        self.assertEqual(entry['exec_score'], 94)

    def test_reads_tomorrow_levels_not_the_expired_today_levels(self):
        row = row_of(today_support=1.0, today_resistance=2.0)
        entry = evaluate(row, quote_of(150.0))
        self.assertEqual(entry['support'], 100.0)
        self.assertEqual(entry['resistance'], 200.0)
        self.assertAlmostEqual(entry['progress'], 0.5)

    def test_missing_quote_keeps_the_row_but_leaves_no_score(self):
        entry = evaluate(row_of(), None)
        self.assertIsNone(entry['exec_score'])
        self.assertIsNone(entry['last'])
        self.assertEqual(entry['name'], '铜')
        self.assertEqual(entry['support'], 100.0)

    def test_neutral_direction_has_no_position_and_drops_out_of_the_ranking(self):
        """日线没有方向时，不该伪造一个位置分把它顶上排名。"""
        entry = evaluate(row_of(decision_side='neutral', state_v2=None), quote_of(100.0))
        self.assertEqual(entry['stance'], 'unknown')
        self.assertIsNone(entry['position_score'])
        self.assertIsNone(entry['exec_score'])
        self.assertEqual(entry['last'], 100.0)
        self.assertEqual(entry['direction_score'], 0)

    def test_short_side_scores_a_rally_into_resistance_as_the_good_entry(self):
        entry = evaluate(row_of(decision_side='short', state_v2='TREND'), quote_of(200.0))
        self.assertEqual(entry['stance'], 'edge')
        self.assertEqual(entry['position_score'], 90)

    def test_broken_long_ranks_below_a_clean_pullback(self):
        broken = evaluate(row_of(), quote_of(40.0))
        pullback = evaluate(row_of(), quote_of(100.0))
        self.assertEqual(broken['stance'], 'broken')
        self.assertLess(broken['exec_score'], pullback['exec_score'])


class PriceScaleTests(unittest.TestCase):
    def test_factor_is_real_over_adjusted_close(self):
        self.assertAlmostEqual(price_scale(row_of(close=923.39, raw_close=1503.0)), 1503.0 / 923.39)
        self.assertEqual(price_scale(row_of(close=100.0, raw_close=100.0)), 1.0)

    def test_missing_or_invalid_close_yields_no_factor(self):
        for close, raw in [(None, 100.0), (100.0, None), (0.0, 100.0), (100.0, 0.0), (-1.0, 100.0)]:
            self.assertIsNone(price_scale(row_of(close=close, raw_close=raw)))


class AdjustedLevelTests(unittest.TestCase):
    """日线价位是复权口径、盘中报价是真实口径；不换算会把位置分算成荒谬值。"""

    def test_levels_are_scaled_into_real_contract_terms(self):
        row = row_of(close=100.0, raw_close=160.0)
        entry = evaluate(row, quote_of(150.0))
        self.assertAlmostEqual(entry['price_scale'], 1.6)
        self.assertAlmostEqual(entry['support'], 160.0)
        self.assertAlmostEqual(entry['resistance'], 320.0)
        self.assertAlmostEqual(entry['progress'], (150.0 - 160.0) / 160.0)

    def test_real_pullback_to_support_is_recognised_after_scaling(self):
        row = row_of(close=100.0, raw_close=150.0)
        entry = evaluate(row, quote_of(150.0))
        self.assertEqual(entry['stance'], 'edge')
        self.assertEqual(entry['position_score'], 90)

    def test_regression_container_shipping_no_longer_produces_absurd_progress(self):
        """曾经算出推进度 -11：复权价 3406.58、真实价 2225.5，箱体被等比放大了 1/0.6533。"""
        row = row_of(close=3406.58, raw_close=2225.5,
                     tomorrow_support=3369.08, tomorrow_resistance=3477.76, decision_side='long')
        entry = evaluate(row, quote_of(2162.5))
        self.assertAlmostEqual(entry['support'], 2201.0, places=1)
        self.assertGreater(entry['progress'], -1.5)
        self.assertLess(entry['progress'], 0)
        self.assertEqual(entry['stance'], 'broken')

    def test_unknown_factor_refuses_to_score_instead_of_guessing(self):
        entry = evaluate(row_of(close=None, raw_close=None), quote_of(150.0))
        self.assertIsNone(entry['price_scale'])
        self.assertIsNone(entry['support'])
        self.assertIsNone(entry['progress'])
        self.assertIsNone(entry['exec_score'])


class RankTests(unittest.TestCase):
    def test_orders_by_executability_and_keeps_unscored_rows_last(self):
        rows = [row_of(ts_code='A.SHF', main_code='A0001.SHF', name='甲'),
                row_of(ts_code='B.SHF', main_code='B0001.SHF', name='乙'),
                row_of(ts_code='C.SHF', main_code='C0001.SHF', name='丙')]
        quotes = {'A0001.SHF': quote_of(40.0), 'B0001.SHF': quote_of(100.0)}
        ranked = rank(rows, quotes)
        self.assertEqual([item['name'] for item in ranked], ['乙', '甲', '丙'])
        self.assertIsNone(ranked[-1]['exec_score'])

    def test_ties_break_on_the_daily_trend_score(self):
        rows = [row_of(ts_code='A.SHF', main_code='A0001.SHF', name='弱', dir_score=10.0),
                row_of(ts_code='B.SHF', main_code='B0001.SHF', name='强', dir_score=90.0)]
        quotes = {'A0001.SHF': quote_of(100.0), 'B0001.SHF': quote_of(100.0)}
        self.assertEqual([item['name'] for item in rank(rows, quotes)], ['强', '弱'])


if __name__ == '__main__':
    unittest.main()
