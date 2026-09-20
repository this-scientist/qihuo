import unittest

from decision_v2 import build_decisions


def side_row(direction, **overrides):
    base = dict(
        ts_code='JM.DCE',
        name='焦煤',
        sector='黑色',
        main_code='JM2701.DCE',
        direction=direction,
        trend_score=20.0,
        startup_score=10.0,
        score_ma=0.0,
        score_quality=0.0,
        score_rps=0.0,
        score_breakout=0.0,
        directional_rps20=50.0,
        adx_slope=0.0,
        atr_change5=0.0,
        volume_ratio=1.0,
        oi_change5=0.0,
        return5=0.0,
        spread_change5=None,
        carry_change5=None,
        confirmed=False,
        startup_eligible=False,
        overextended=False,
        volatility_extreme=False,
        phase='震荡',
        trend_direction='neutral',
        technical_start=False,
        signal_base_breakout=False,
        signal_mild_volume=False,
        signal_oi_growth=False,
        signal_adx_rising=False,
        signal_atr_expansion=False,
    )
    base.update(overrides)
    return base


class DecisionV2Tests(unittest.TestCase):
    def test_strong_long_allows_only_call(self):
        long = side_row('long', trend_score=84, score_ma=20, score_quality=15, score_rps=20,
            directional_rps20=92, return5=3.2, oi_change5=7.5, spread_change5=12,
            confirmed=True, phase='持续趋势', trend_direction='long')
        short = side_row('short', trend_score=18, score_ma=0, score_quality=2, score_rps=0,
            directional_rps20=8, return5=3.2, oi_change5=7.5, spread_change5=12)

        decision = build_decisions([long, short])[0]

        self.assertGreaterEqual(decision['dir_score'], 50)
        self.assertEqual(decision['decision_side'], 'long')
        self.assertEqual(decision['state_v2'], 'TREND')
        self.assertEqual(decision['trend_state'], 'T4')
        self.assertEqual(decision['trend_option_gate'], 'CONDITIONAL')
        self.assertEqual(decision['option_action'], 'Call')

    def test_strong_short_allows_only_put(self):
        long = side_row('long', trend_score=16, score_ma=0, score_quality=1, score_rps=0,
            directional_rps20=9, return5=-4.0, oi_change5=8.0, spread_change5=-18)
        short = side_row('short', trend_score=86, score_ma=20, score_quality=15, score_rps=20,
            directional_rps20=91, return5=-4.0, oi_change5=8.0, spread_change5=-18,
            confirmed=True, phase='持续趋势', trend_direction='short')

        decision = build_decisions([long, short])[0]

        self.assertLessEqual(decision['dir_score'], -50)
        self.assertEqual(decision['decision_side'], 'short')
        self.assertEqual(decision['trend_state'], 'T4')
        self.assertEqual(decision['option_action'], 'Put')

    def test_neutral_direction_waits_without_option(self):
        long = side_row('long', trend_score=35, score_ma=6, score_quality=5, score_rps=4,
            directional_rps20=55, return5=.2, oi_change5=1.0)
        short = side_row('short', trend_score=33, score_ma=5, score_quality=5, score_rps=4,
            directional_rps20=53, return5=.2, oi_change5=1.0)

        decision = build_decisions([long, short])[0]

        self.assertEqual(decision['decision_side'], 'neutral')
        self.assertEqual(decision['state_v2'], 'WAIT')
        self.assertEqual(decision['trend_state'], 'T0')
        self.assertEqual(decision['trend_option_gate'], 'BLOCK')
        self.assertEqual(decision['option_action'], '不做')

    def test_breakout_volume_oi_and_adx_switch_prepare_to_start(self):
        long = side_row('long', trend_score=76, score_ma=18, score_quality=13, score_rps=17,
            directional_rps20=88, return5=2.5, oi_change5=6.0, volume_ratio=1.8,
            signal_base_breakout=True, signal_mild_volume=True, signal_oi_growth=True,
            signal_adx_rising=True, signal_atr_expansion=True, startup_eligible=True,
            phase='趋势启动', trend_direction='long')
        short = side_row('short', trend_score=12, score_ma=0, score_quality=1, score_rps=0,
            directional_rps20=12, return5=2.5, oi_change5=6.0, volume_ratio=1.8)

        decision = build_decisions([long, short])[0]

        self.assertGreaterEqual(decision['start_score'], 70)
        self.assertEqual(decision['state_v2'], 'START')
        self.assertEqual(decision['trend_state'], 'T2')
        self.assertEqual(decision['trend_transition'], 'T1→T2')
        self.assertEqual(decision['candidate_tier'], 'ACTIVE')

    def test_exhaustion_does_not_flip_into_reverse_trade(self):
        long = side_row('long', trend_score=82, score_ma=20, score_quality=13, score_rps=18,
            directional_rps20=90, return5=5.0, oi_change5=-3.0,
            confirmed=True, overextended=True, phase='过度延伸', trend_direction='long')
        short = side_row('short', trend_score=28, score_ma=4, score_quality=4, score_rps=2,
            directional_rps20=10, return5=5.0, oi_change5=-3.0)

        decision = build_decisions([long, short])[0]

        self.assertEqual(decision['decision_side'], 'long')
        self.assertEqual(decision['state_v2'], 'EXHAUST')
        self.assertEqual(decision['trend_state'], 'T5')
        self.assertEqual(decision['trend_option_gate'], 'BLOCK')
        self.assertEqual(decision['option_action'], '不做')


if __name__ == '__main__':
    unittest.main()
