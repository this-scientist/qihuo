import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from strategy import indicators, rps_panel, pair_context, evaluate, rank_candidates, Settings
from history import adjust_rolls
from collector import DataError


def bars(prices):
    prices = np.asarray(prices, dtype=float)
    return pd.DataFrame(dict(trade_date=pd.bdate_range('2024-01-01', periods=len(prices)).strftime('%Y%m%d'),
        open=prices, high=prices+1, low=prices-1, close=prices, vol=1000, oi=10000))


class StrategyTests(unittest.TestCase):
    def test_atr_wilder_seed_and_update(self):
        data = bars([100]*30)
        data.loc[14, 'high'] = 114
        result = indicators(data)
        self.assertEqual(result.atr14.iloc[13], 2)
        self.assertAlmostEqual(result.atr14.iloc[14], (2*13+15)/14)

    def test_breakout_excludes_today(self):
        data = bars([100]*60+[110])
        result = indicators(data)
        self.assertEqual(result.high20.iloc[-1], 101)
        self.assertTrue(result.break20_up.iloc[-1])
        self.assertTrue(result.break55_up.iloc[-1])

    def test_flat_market_has_zero_adx_and_no_breakout(self):
        result = indicators(bars([100]*300))
        self.assertAlmostEqual(result.adx.iloc[-1], 0)
        self.assertFalse(result.break20_up.iloc[-1])

    def test_future_data_does_not_change_past_indicators(self):
        data = bars(np.arange(300)+100)
        before = indicators(data.iloc[:280]).iloc[-1]
        data.loc[280:, ['high','low','open','close']] *= 4
        after = indicators(data).iloc[279]
        for field in ['ma20','ma60','ma120','adx','atr14','high55','atr_percentile']:
            self.assertEqual(before[field], after[field])

    def test_rps_extremes_and_ties(self):
        a = bars(np.linspace(100,200,300)); a['ts_code']='A.DCE'
        b = bars(np.linspace(200,100,300)); b['ts_code']='B.DCE'
        c = b.copy(); c['ts_code']='C.DCE'
        result = rps_panel(pd.concat([a,b,c], ignore_index=True))
        last = result[result.trade_date.eq(a.trade_date.iloc[-1])].set_index('ts_code')
        self.assertEqual(last.loc['A.DCE','rps20'],100)
        self.assertEqual(last.loc['B.DCE','rps20'],25)
        self.assertEqual(last.loc['C.DCE','rps20'],25)

    def test_roll_spread_does_not_create_false_return(self):
        data = pd.DataFrame(dict(trade_date=['20260907','20260908'],open=[100.,150.],high=[101.,151.],low=[99.,149.],close=[100.,150.],mapping_ts_code=['M2609.DCE','M2701.DCE']))
        result = adjust_rolls(data, {('20260907','M2609.DCE','M2701.DCE'):(100.,150.)})
        self.assertAlmostEqual(result.close.iloc[-1],100)
        self.assertAlmostEqual(result.adj_factor.iloc[-1],2/3)
        self.assertEqual(result.raw_close.iloc[-1],150)

    def test_missing_roll_overlap_rejected(self):
        data = bars([100,150]); data['mapping_ts_code']=['M2609.DCE','M2701.DCE']
        with self.assertRaises(DataError):
            adjust_rolls(data,{})

    def test_flat_market_cannot_enter_any_list(self):
        result = indicators(bars([100]*300))
        for field in ['rps20','rps60','rps120','rps20_prev5','rps120_prev5']:
            result[field] = 50
        rows = [evaluate(result, 1, {}, Settings()), evaluate(result, -1, {}, Settings())]
        self.assertFalse(any(r['confirmed'] or r['startup_eligible'] for r in rows))
        self.assertEqual(len(rank_candidates(pd.DataFrame(rows), 'startup', Settings())),0)

    def test_missing_basis_does_not_receive_zero_quality(self):
        result = indicators(bars(np.arange(300)+100))
        for field in ['rps20','rps60','rps120','rps20_prev5','rps120_prev5']:
            result[field] = 99
        row = evaluate(result,1,{},Settings())
        self.assertEqual(row['trend_available'],75)
        self.assertIsNone(row['score_funding'])
        self.assertIsNone(row['score_structure'])
        self.assertAlmostEqual(row['trend_score'],row['trend_earned']/75*100,places=2)

    def test_continuous_strong_trend_is_not_automatically_startup(self):
        data=indicators(bars(np.arange(300)+100))
        for field in ['rps20','rps60','rps120','rps20_prev5','rps120_prev5']:
            data[field]=99
        context=dict(oi_change5=.05,oi_change20=.1,volume_ratio=1.5,spread_change5=5)
        row=evaluate(data,1,context,Settings())
        self.assertTrue(row['confirmed'])
        self.assertFalse(row['startup_eligible'])

    def test_long_and_short_structure_are_symmetric(self):
        long=indicators(bars(np.arange(300)+100))
        short=indicators(bars(500-np.arange(300)))
        for field in ['rps20','rps60','rps120','rps20_prev5','rps120_prev5']:
            long[field]=99; short[field]=1
        context=dict(oi_change5=.05,oi_change20=.1,volume_ratio=1.5,spread_change5=5)
        a=evaluate(long,1,context,Settings())
        b=evaluate(short,-1,dict(context,spread_change5=-5),Settings())
        self.assertTrue(a['confirmed'] and b['confirmed'])
        self.assertEqual(a['score_ma'],b['score_ma'])
        self.assertEqual(a['score_rps'],b['score_rps'])
        self.assertFalse(evaluate(long,-1,context,Settings())['confirmed'])

    def test_pair_growth_compares_same_two_contracts(self):
        dates=pd.bdate_range('2026-08-01',periods=25).strftime('%Y%m%d')
        data=[]
        for i,date in enumerate(dates):
            for role,code in [('main','M2701.DCE'),('secondary','M2705.DCE')]:
                data.append(dict(trade_date=date,role=role,ts_code=code,oi=100+i,vol=100,close=100,settle=100))
        context=pair_context(pd.DataFrame(data),dates[-1],dates)
        self.assertAlmostEqual(context['oi_change5'],248/238-1)
        self.assertAlmostEqual(context['oi_change20'],248/208-1)
        self.assertEqual(context['oi_scope'],'main_secondary_fixed_pair')

    def test_pair_context_identifies_rollover_absorption(self):
        dates=pd.bdate_range('2026-08-01',periods=25).strftime('%Y%m%d')
        data=[]
        for i,date in enumerate(dates):
            main_oi=1000 - max(0,i-19)*40
            secondary_oi=500 + max(0,i-19)*50
            for role,code,oi in [('main','M2701.DCE',main_oi),('secondary','M2705.DCE',secondary_oi)]:
                data.append(dict(trade_date=date,role=role,ts_code=code,oi=oi,vol=100,close=100,settle=100))
        context=pair_context(pd.DataFrame(data),dates[-1],dates)
        self.assertLess(context['main_oi_change5'],0)
        self.assertGreater(context['secondary_oi_change5'],0)
        self.assertGreater(context['oi_change5'],0)
        self.assertTrue(context['rollover_transfer'])
        self.assertAlmostEqual(context['rollover_absorption5'],250/200)

    def test_pair_missing_trading_day_does_not_compare_wrong_period(self):
        dates=pd.bdate_range('2026-08-01',periods=25).strftime('%Y%m%d')
        data=pd.DataFrame([dict(trade_date=date,role='main',ts_code='M2701.DCE',oi=100,vol=100,close=100,settle=100) for date in dates if date!=dates[-3]])
        context=pair_context(data,dates[-1],dates)
        self.assertNotIn('oi_change5',context)

    def test_pair_with_changing_role_identity_rejected(self):
        data=pd.DataFrame([dict(trade_date='20260907',role='main',ts_code='M2609.DCE'),dict(trade_date='20260908',role='main',ts_code='M2701.DCE')])
        with self.assertRaises(DataError):
            pair_context(data,'20260908')

    def test_one_low_atr_day_is_not_long_compression(self):
        data=indicators(bars([100]*300))
        for field in ['rps20','rps60','rps120','rps20_prev5','rps120_prev5']:
            data[field]=50
        data.loc[data.index[-25:-5],'atr_ratio']=1.0
        data.loc[data.index[-10],'atr_ratio']=0.5
        data.loc[data.index[-1],'atr_ratio']=1.2
        data.loc[data.index[-1],'atr_change5']=.2
        self.assertFalse(evaluate(data,1,{},Settings())['signal_atr_expansion'])

    def test_negative_secondary_oi_cannot_hide_in_positive_pair_sum(self):
        dates=pd.bdate_range('2026-08-01',periods=25).strftime('%Y%m%d')
        rows=[]
        for i,date in enumerate(dates):
            for role,code in [('main','M2701.DCE'),('secondary','M2705.DCE')]:
                rows.append(dict(trade_date=date,role=role,ts_code=code,
                    oi=-90 if role=='secondary' and i==4 else 100,vol=100,close=100,settle=100))
        with self.assertRaises(DataError):
            pair_context(pd.DataFrame(rows),dates[-1],dates)


if __name__ == '__main__':
    unittest.main()
