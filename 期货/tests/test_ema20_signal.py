import unittest

from ema20_signal import Ema20Settings, ema20_assessment


class Ema20SignalTests(unittest.TestCase):
    def row(self, slope=.5, distance=1):
        return dict(ema20=100, ema20_slope5_atr=slope,
                    ema20_distance_atr=distance)

    def test_strength_boundaries_are_explicit(self):
        self.assertEqual(ema20_assessment(self.row(slope=.249), 'long')['ema20_strength'], 'weak')
        self.assertEqual(ema20_assessment(self.row(slope=.25), 'long')['ema20_strength'], 'medium')
        self.assertEqual(ema20_assessment(self.row(slope=.749), 'long')['ema20_strength'], 'medium')
        self.assertEqual(ema20_assessment(self.row(slope=.75), 'long')['ema20_strength'], 'strong')

    def test_distance_boundaries_drive_actionability(self):
        self.assertEqual(ema20_assessment(self.row(distance=2), 'long')['ema20_actionability'], 'actionable')
        self.assertEqual(ema20_assessment(self.row(distance=2.001), 'long')['ema20_actionability'], 'wait_pullback')
        self.assertEqual(ema20_assessment(self.row(distance=3), 'long')['ema20_actionability'], 'wait_pullback')
        self.assertEqual(ema20_assessment(self.row(distance=3.001), 'long')['ema20_actionability'], 'do_not_chase')

    def test_short_side_is_the_exact_directional_mirror(self):
        long = ema20_assessment(self.row(slope=.75, distance=1.5), 'long')
        short = ema20_assessment(self.row(slope=-.75, distance=-1.5), 'short')
        self.assertEqual(long['ema20_actionability'], 'actionable')
        self.assertEqual(short['ema20_actionability'], 'actionable')
        self.assertEqual(long['directional_ema20_slope5_atr'], short['directional_ema20_slope5_atr'])
        self.assertEqual(long['directional_ema20_distance_atr'], short['directional_ema20_distance_atr'])

    def test_wrong_side_weak_slope_missing_data_and_quality_block(self):
        self.assertEqual(ema20_assessment(self.row(distance=-.01), 'long')['ema20_actionability'], 'not_actionable')
        self.assertEqual(ema20_assessment(self.row(slope=.249), 'long')['ema20_actionability'], 'not_actionable')
        self.assertEqual(ema20_assessment(self.row() | {'ema20_distance_atr': None}, 'long')['ema20_actionability'], 'not_actionable')
        blocked = ema20_assessment(self.row(), 'long', quality_ok=False, quality_reason='ADX/DI未确认')
        self.assertEqual(blocked['ema20_actionability'], 'not_actionable')
        self.assertIn('ADX/DI未确认', blocked['ema20_actionability_reasons'])

    def test_thresholds_are_configurable(self):
        settings = Ema20Settings(medium_slope_atr=.5, strong_slope_atr=1,
                                 actionable_distance_atr=1, max_distance_atr=2)
        result = ema20_assessment(self.row(slope=.4, distance=.5), 'long', settings=settings)
        self.assertEqual(result['ema20_strength'], 'weak')
        self.assertEqual(result['ema20_actionability'], 'not_actionable')


if __name__ == '__main__':
    unittest.main()
