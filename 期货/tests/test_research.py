import unittest
import pandas as pd
from trend_phases import phase_for_row
from historical_validation import event_outcome


class ResearchTests(unittest.TestCase):
    def row(self,**extra):
        value=dict(close=130,ma20=120,ma60=110,ma120=115,slope20=.01,slope60=.01,adx=35,
            plus_di=35,minus_di=10,rps20=95,rps60=85,atr14=5,adx_prev5=30,adx_slope=5,
            rps20_prev5=92,recent_break20=True,fresh_break=False)
        return value|extra

    def test_strong_oil_is_not_range_when_long_ma_lags(self):
        result=phase_for_row(self.row())
        self.assertEqual(result['phase'],'中短期强势')
        self.assertEqual(result['trend_direction'],'long')

    def test_ethylene_glycol_does_not_need_new_breakout_to_be_trend(self):
        self.assertEqual(phase_for_row(self.row(ma120=105,recent_break20=False))['phase'],'持续趋势')

    def test_extension_does_not_cancel_direction(self):
        result=phase_for_row(self.row(close=145))
        self.assertEqual(result['phase'],'过度延伸')
        self.assertEqual(result['trend_direction'],'long')

    def test_technical_start_requires_prior_low_adx_and_fresh_break(self):
        row=self.row(adx=23,adx_prev5=18,adx_slope=5,rps20_prev5=70,fresh_break=True)
        self.assertEqual(phase_for_row(row)['phase'],'趋势启动')
        self.assertNotEqual(phase_for_row(row|{'fresh_break':False})['phase'],'趋势启动')

    def test_next_open_entry_no_same_close_execution(self):
        d=pd.DataFrame([dict(trade_date='20260908',open=90,close=100,high=101,low=89),
            dict(trade_date='20260909',open=110,close=112,high=115,low=105),
            dict(trade_date='20260910',open=112,close=121,high=125,low=109)])
        r=event_outcome(d,0,'long',2,10)
        self.assertEqual(r['entry_date'],'20260909')
        self.assertAlmostEqual(r['gross_return'],10)
        self.assertAlmostEqual(r['net_return'],9.9)
        self.assertAlmostEqual(r['mae'],(105/110-1)*100,places=6)
        self.assertEqual(event_outcome(d,1,'long',2,0)['status'],'pending')


if __name__=='__main__': unittest.main()
