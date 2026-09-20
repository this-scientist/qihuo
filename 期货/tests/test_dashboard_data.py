import unittest
import pandas as pd
from dashboard_data import classify, aggregate_curves, public_metrics


class DashboardTests(unittest.TestCase):
    def test_black_members_and_unique_classification(self):
        for code in ['RB.SHF','HC.SHF','I.DCE','J.DCE','JM.DCE','SF.ZCE','SM.ZCE']:
            self.assertEqual(classify(code), '黑色')
        self.assertEqual(classify('AU.SHF'), '贵金属')
        self.assertEqual(classify('M.DCE'), '农产品')
        self.assertEqual(classify('UNKNOWN.DCE'), '其他')

    def test_class_curve_is_equal_weight_not_average_price(self):
        curves = {'RB.SHF':[['20260910',100],['20260911',110]],
                  'I.DCE':[['20260910',1000],['20260911',900]]}
        values = aggregate_curves(curves)['黑色']
        self.assertEqual(values['count'],2)
        self.assertAlmostEqual(values['values'][-1][1],100)

    def test_percent_and_nulls_are_not_confused(self):
        row = public_metrics({'return20':.12,'oi_change5':-.03,'rollover_absorption5':.8,'atr_pct':2.5,'adx':float('nan'),'close':100,'rollover_transfer':True})
        self.assertEqual(row['return20'],12)
        self.assertEqual(row['oi_change5'],-3)
        self.assertEqual(row['rollover_absorption5'],80)
        self.assertEqual(row['atr_pct'],2.5)
        self.assertIsNone(row['adx'])
        self.assertTrue(row['rollover_transfer'])

    def test_aggregate_requires_common_dates(self):
        curves={'RB.SHF':[['20260909',50],['20260910',100],['20260911',110]],
                'I.DCE':[['20260910',1000],['20260911',900]]}
        values=aggregate_curves(curves)['黑色']['values']
        self.assertEqual(values[0],['20260910',100.0])
        self.assertAlmostEqual(values[-1][1],100)


if __name__=='__main__': unittest.main()
