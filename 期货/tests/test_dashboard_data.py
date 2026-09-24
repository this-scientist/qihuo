import unittest
import pandas as pd
from dashboard_data import classify, aggregate_curves, public_metrics, sector_trend, sector_relative_strength


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


def group_of(values):
    return {'members':[], 'count':0, 'values':[[str(20260100+index), value] for index, value in enumerate(values)]}


class SectorStrengthTests(unittest.TestCase):
    def test_sector_trend_reads_the_index_not_member_votes(self):
        falling=[100-index*0.5 for index in range(26)]
        self.assertEqual(sector_trend(falling)[0],'short')
        self.assertEqual(sector_trend(list(reversed(falling)))[0],'long')
        self.assertEqual(sector_trend([100.0]*26)[0],'flat')
        self.assertEqual(sector_trend([100,101])[0],'unknown')

    def test_short_sector_scores_the_heaviest_faller_highest(self):
        group=group_of([100-index*0.5 for index in range(26)])
        members=[dict(ts_code='J.DCE',sector='黑色',return20=-8.0,decision_side='short'),
                 dict(ts_code='RB.SHF',sector='黑色',return20=-5.0,decision_side='short'),
                 dict(ts_code='I.DCE',sector='黑色',return20=-1.0,decision_side='neutral'),
                 dict(ts_code='HC.SHF',sector='黑色',return20=2.0,decision_side='long')]
        fields=sector_relative_strength({'黑色':group},members)
        self.assertEqual(fields['J.DCE']['sector_direction'],'short')
        self.assertAlmostEqual(fields['J.DCE']['sector_strength'],100.0)
        self.assertAlmostEqual(fields['RB.SHF']['sector_strength'],66.67,places=1)
        self.assertAlmostEqual(fields['I.DCE']['sector_strength'],33.33,places=1)
        self.assertEqual([fields[code]['sector_rank'] for code in ['J.DCE','RB.SHF','I.DCE','HC.SHF']],[1,2,3,4])

    def test_counter_sector_rows_are_negated_by_reverse_strength(self):
        """取负的必须是反向强度：最强的逆势者要取得最负的分值，而不是最接近 0。"""
        group=group_of([100-index*0.5 for index in range(26)])
        members=[dict(ts_code='J.DCE',sector='黑色',return20=-8.0,decision_side='short'),
                 dict(ts_code='RB.SHF',sector='黑色',return20=0.0,decision_side='long'),
                 dict(ts_code='HC.SHF',sector='黑色',return20=6.0,decision_side='long')]
        fields=sector_relative_strength({'黑色':group},members)
        self.assertTrue(fields['HC.SHF']['sector_counter'])
        self.assertTrue(fields['RB.SHF']['sector_counter'])
        self.assertFalse(fields['J.DCE']['sector_counter'])
        self.assertAlmostEqual(fields['HC.SHF']['sector_strength'],-100.0)
        self.assertLess(fields['HC.SHF']['sector_strength'],fields['RB.SHF']['sector_strength'])
        self.assertLess(fields['RB.SHF']['sector_strength'],0)

    def test_flat_sector_never_marks_a_row_as_counter(self):
        fields=sector_relative_strength({'黑色':group_of([100.0]*26)},
            [dict(ts_code='RB.SHF',sector='黑色',return20=5.0,decision_side='long'),
             dict(ts_code='I.DCE',sector='黑色',return20=-5.0,decision_side='short')])
        self.assertEqual(fields['RB.SHF']['sector_direction'],'flat')
        self.assertFalse(fields['RB.SHF']['sector_counter'])
        self.assertFalse(fields['I.DCE']['sector_counter'])
        self.assertAlmostEqual(fields['RB.SHF']['sector_strength'],100.0)
        self.assertAlmostEqual(fields['I.DCE']['sector_strength'],0.0)

    def test_single_member_sector_has_no_percentile(self):
        fields=sector_relative_strength({'其他':group_of([100-index*0.5 for index in range(26)])},
            [dict(ts_code='EC.INE',sector='其他',return20=3.0,decision_side='long')])
        self.assertEqual(fields['EC.INE']['sector_members'],1)
        self.assertIsNone(fields['EC.INE']['sector_strength'])
        self.assertEqual(fields['EC.INE']['sector_rank'],1)


if __name__=='__main__': unittest.main()
