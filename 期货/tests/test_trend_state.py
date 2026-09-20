import unittest

from trend_state import classify_trend_state


def row(**overrides):
    base = dict(
        phase='震荡',
        trend_direction='neutral',
        dir_score=0.0,
        directional_rps20=50.0,
        rps20=50.0,
        rps20_prev5=50.0,
        rps60=50.0,
        adx=16.0,
        adx_slope=0.0,
        plus_di=20.0,
        minus_di=20.0,
        oi_change5=0.0,
        return5=0.0,
        volume_ratio=1.0,
        atr_change5=0.0,
        phase_extension_atr=0.0,
        technical_start=False,
        signal_base_breakout=False,
        signal_mild_volume=False,
        signal_oi_growth=False,
        signal_adx_rising=False,
        signal_atr_expansion=False,
        confirmed=False,
        overextended=False,
    )
    base.update(overrides)
    return base


class TrendStateTests(unittest.TestCase):
    def test_neutral_waits_as_t0(self):
        result = classify_trend_state(row(), 'neutral', 'WAIT', 0)

        self.assertEqual(result['trend_state'], 'T0')
        self.assertEqual(result['trend_option_gate'], 'BLOCK')
        self.assertIn('无趋势', result['trend_state_label'])

    def test_forming_direction_is_t1_watch(self):
        result = classify_trend_state(row(
            phase='方向形成', trend_direction='long', directional_rps20=64,
            rps20_prev5=42, adx=18, adx_slope=2.5, plus_di=24, minus_di=18,
            oi_change5=2.0, return5=1.5,
        ), 'long', 'PREPARE', 58)

        self.assertEqual(result['trend_state'], 'T1')
        self.assertEqual(result['trend_transition'], 'T0→T1')
        self.assertEqual(result['trend_option_gate'], 'WATCH')

    def test_breakout_start_is_t2_tradeable(self):
        result = classify_trend_state(row(
            phase='趋势启动', trend_direction='long', directional_rps20=74,
            rps20_prev5=48, adx=23, adx_slope=4.0, plus_di=29, minus_di=17,
            oi_change5=6.0, return5=3.0, volume_ratio=1.7,
            technical_start=True, signal_base_breakout=True, signal_oi_growth=True,
            signal_mild_volume=True, signal_adx_rising=True,
        ), 'long', 'START', 82)

        self.assertEqual(result['trend_state'], 'T2')
        self.assertEqual(result['trend_transition'], 'T1→T2')
        self.assertEqual(result['trend_option_gate'], 'ALLOW')

    def test_acceleration_is_t3_priority(self):
        result = classify_trend_state(row(
            phase='趋势启动', trend_direction='short', directional_rps20=93,
            rps20=8, rps20_prev5=34, adx=33, adx_slope=7.0,
            plus_di=12, minus_di=34, oi_change5=8.0, return5=-5.0,
            volume_ratio=2.1, atr_change5=18.0, signal_atr_expansion=True,
            signal_oi_growth=True, signal_adx_rising=True,
        ), 'short', 'START', 91)

        self.assertEqual(result['trend_state'], 'T3')
        self.assertEqual(result['trend_transition'], 'T2→T3')
        self.assertEqual(result['trend_accel_level'], '增强')
        self.assertEqual(result['trend_option_gate'], 'ALLOW')

    def test_confirmed_continuation_is_t4_conditional(self):
        result = classify_trend_state(row(
            phase='持续趋势', trend_direction='long', directional_rps20=86,
            rps20_prev5=82, adx=31, adx_slope=.2, plus_di=35, minus_di=16,
            oi_change5=1.2, return5=1.0, confirmed=True,
        ), 'long', 'TREND', 48)

        self.assertEqual(result['trend_state'], 'T4')
        self.assertEqual(result['trend_option_gate'], 'CONDITIONAL')

    def test_overextended_or_weakening_is_t5_blocked(self):
        result = classify_trend_state(row(
            phase='过度延伸', trend_direction='long', directional_rps20=94,
            adx=42, adx_slope=-4.0, plus_di=38, minus_di=14,
            oi_change5=-4.5, return5=4.8, overextended=True,
            phase_extension_atr=3.8,
        ), 'long', 'EXHAUST', 30)

        self.assertEqual(result['trend_state'], 'T5')
        self.assertEqual(result['trend_transition'], 'T4→T5')
        self.assertEqual(result['trend_option_gate'], 'BLOCK')


if __name__ == '__main__':
    unittest.main()
