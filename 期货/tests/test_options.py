import unittest
from option_analysis import black76, implied_vol, option_metrics


class OptionsTests(unittest.TestCase):
    def test_expiry_day_keeps_contract_without_inventing_iv(self):
        meta=dict(ts_code='TEST',exercise_price=100,call_put='C',maturity_date='20260911',opt_multiplier=10)
        row=option_metrics(meta,dict(close=1,vol=1,oi=1),'20260911',100)
        self.assertEqual(row['days_to_expiry'],0)
        self.assertIsNone(row['iv_reference'])

    def test_black76_atm_and_inversion(self):
        price=black76(100,100,1,0,.2,'C')
        self.assertAlmostEqual(price,7.9655674554,places=8)
        self.assertAlmostEqual(implied_vol(price,100,100,1,0,'C'),.2,places=5)
        self.assertAlmostEqual(black76(100,100,1,0,.2,'P'),price)

    def test_out_of_bound_price_is_not_iv(self):
        self.assertIsNone(implied_vol(101,100,100,1,0,'C'))
        self.assertIsNone(implied_vol(0,100,100,0,0,'C'))

    def test_no_quotes_never_confirm_executable_candidate(self):
        m=dict(ts_code='M2701-C-3000.DCE',exercise_price=3000,call_put='C',exercise_type='美式',
            maturity_date='20261207',opt_multiplier=10)
        row=option_metrics(m,dict(close=100,vol=200,oi=500),'20260911',3000,.02)
        self.assertFalse(row['executable'])
        self.assertEqual(row['premium_per_lot'],1000)
        self.assertTrue(row['model_approximation'])
        self.assertIsNone(row['bid_ask_spread_pct'])

    def test_missing_multiplier_does_not_invent_lot_cost(self):
        m=dict(ts_code='M2701-C-3000.DCE',exercise_price=3000,call_put='C',exercise_type='美式',maturity_date='20261207')
        row=option_metrics(m,dict(close=100,vol=1,oi=1),'20260911',3000,.02)
        self.assertIsNone(row['premium_per_lot'])


if __name__=='__main__':unittest.main()
