import unittest

import pandas as pd

from strategy import indicators, rps_panel
from decision_v2 import build_decisions


class UnifiedFactorsTests(unittest.TestCase):
    def test_rps5_is_raw_cross_sectional_rank_and_ties_match(self):
        rows = [dict(ts_code=code, trade_date=f'{day:03}', close=100 + step * day)
                for code, step in [('A', 1), ('B', -1), ('C', 1)] for day in range(12)]
        latest = rps_panel(pd.DataFrame(rows)).groupby('ts_code').tail(1).set_index('ts_code')
        self.assertIn('rps5', latest)
        self.assertEqual(latest.loc['A', 'rps5'], latest.loc['C', 'rps5'])
        self.assertEqual(latest.loc['B', 'rps5'], 0)

    def test_daily_close_return_is_causal(self):
        data = pd.DataFrame([dict(trade_date=str(i), open=p, high=p+1, low=p-1, close=p)
                             for i, p in enumerate([100, 110, 99])])
        result = indicators(data)
        self.assertIn('return1', result)
        self.assertAlmostEqual(result.return1.iloc[-1], -.1)

    def test_missing_prices_do_not_manufacture_direction(self):
        result = build_decisions([dict(ts_code='X', direction='long')])[0]
        self.assertEqual(result['decision_side'], 'neutral')
        self.assertEqual(result.get('trend_model_status'), 'missing')
        scored = build_decisions([dict(ts_code='X', direction='long', score_ma=20,
                                       score_rps=20, score_quality=15)])[0]
        self.assertEqual(scored['decision_side'], 'neutral')

    def test_structure_keeps_own_direction(self):
        from option_scanner import structure_radar
        row = dict(return5=-5, oi_change5=-3, oi_change20=-6,
                   spread=100, spread_change5=50, carry_annualized=3,
                   carry_change5=1, structure='Backwardation', trend_direction='short')
        result = structure_radar(row)
        self.assertEqual(result['dominant'], 'long')
        self.assertEqual(result.get('effective_groups'), 2)

    def test_price_direction_is_independent_of_relative_rank_and_oi(self):
        from trend_model import price_trend
        row = dict(close=90, ma20=95, ma60=100, atr14=2, slope20=-2,
                   return5=-3, return20=-8, plus_di=10, minus_di=30, adx=30)
        result = price_trend(row)
        self.assertEqual(result['side'], 'short')
        self.assertEqual(result, price_trend(row | dict(rps20=99, oi_change5=100,
                                                       carry_annualized=30)))
        self.assertEqual(price_trend(row | {'close': None})['status'], 'missing')

    def test_burst_does_not_credit_countertrend_oi(self):
        from trend_model import burst_index
        result = burst_index(dict(oi_change5=10, return5=3), 'short')
        self.assertEqual(result['burst_components']['oi'], 0)

    def test_oi_flat_is_not_reported_as_unwinding(self):
        from option_scanner import structure_radar
        result = structure_radar(dict(return5=-5, oi_change5=0))
        self.assertIsNone(result['oi']['direction'])

    def test_legacy_cache_rebuilds_and_scanner_shares_conclusions(self):
        from research_server import ensure_decision_payload
        from option_scanner import build_scanner
        row = dict(ts_code='X', close=90, ma20=95, ma60=100, atr14=2,
                   slope20=-2, return5=-3, return20=-8, plus_di=10,
                   minus_di=30, adx=30, rps20=0, rps20_prev5=10,
                   carry_annualized=5, spread_change5=10, spread=20)
        records = [row | {'direction': side} for side in ['long', 'short']]
        payload = ensure_decision_payload(dict(records=records, decisions=[{'decision_side':'long'}]))
        self.assertEqual(payload['decisions'][0]['decision_side'], 'short')
        self.assertTrue(all(r['trend_direction']=='short' for r in payload['records']))
        structure = build_scanner(payload, {'records':[]})['structure'][0]
        self.assertEqual(structure['trend_direction'], 'short')
        self.assertEqual(structure['dominant'], 'long')

    def test_volume_rank_ties_receive_identical_scores(self):
        records = [dict(ts_code=code, direction='long', volume_ratio=1, oi_change5=2)
                   for code in ['A', 'B', 'C']]
        decisions = build_decisions(records)
        self.assertEqual({r['vol_rps'] for r in decisions}, {50})
        self.assertEqual({r['oi_change_rps'] for r in decisions}, {50})


if __name__ == '__main__':
    unittest.main()
