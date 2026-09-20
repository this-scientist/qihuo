import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from focused import select_contracts
from collector import DataError


class FocusedTests(unittest.TestCase):
    def snapshot(self):
        return pd.DataFrame([
            dict(ts_code='M2701.DCE', trade_date='20260908', vol=200, oi=300),
            dict(ts_code='M2705.DCE', trade_date='20260908', vol=100, oi=500),
            dict(ts_code='M2709.DCE', trade_date='20260908', vol=10, oi=100),
            dict(ts_code='M.DCE', trade_date='20260908', vol=200, oi=300),
            dict(ts_code='ZC2701.DCE', trade_date='20260908', vol=0, oi=200),
        ])

    def test_main_from_mapping_secondary_by_oi(self):
        mapping = pd.DataFrame([dict(ts_code='M.DCE', trade_date='20260908', mapping_ts_code='M2701.DCE')])
        result, skipped = select_contracts(self.snapshot(), mapping, 'DCE', '20260908')
        self.assertEqual(result[['ts_code','role']].values.tolist(), [['M2701.DCE','main'],['M2705.DCE','secondary']])

    def test_zero_volume_commodity_skipped(self):
        mapping = pd.DataFrame([dict(ts_code='ZC.DCE', trade_date='20260908', mapping_ts_code='ZC2701.DCE')])
        data = self.snapshot()
        data = data[data.ts_code.str.startswith('ZC')]
        result, skipped = select_contracts(data, mapping, 'DCE', '20260908')
        self.assertTrue(result.empty)
        self.assertEqual(skipped[0]['reason'], 'no_volume')

    def test_zero_volume_secondary_not_selected(self):
        data = self.snapshot()
        data.loc[data.ts_code.eq('M2705.DCE'), 'vol'] = 0
        mapping = pd.DataFrame([dict(ts_code='M.DCE', trade_date='20260908', mapping_ts_code='M2701.DCE')])
        result, _ = select_contracts(data, mapping, 'DCE', '20260908')
        self.assertEqual(result.ts_code.tolist(), ['M2701.DCE','M2709.DCE'])

    def test_missing_active_main_is_error(self):
        mapping = pd.DataFrame([dict(ts_code='M.DCE', trade_date='20260908', mapping_ts_code='M2611.DCE')])
        with self.assertRaises(DataError):
            select_contracts(self.snapshot(), mapping, 'DCE', '20260908')

    def test_mapping_wrong_commodity_rejected(self):
        mapping = pd.DataFrame([dict(ts_code='M.DCE', trade_date='20260908', mapping_ts_code='Y2701.DCE')])
        with self.assertRaises(DataError):
            select_contracts(self.snapshot(), mapping, 'DCE', '20260908')

    def test_secondary_continuous_mapping_not_counted_as_commodity(self):
        mapping = pd.DataFrame([
            dict(ts_code='M.DCE', trade_date='20260908', mapping_ts_code='M2701.DCE'),
            dict(ts_code='ML.DCE', trade_date='20260908', mapping_ts_code='M2705.DCE')])
        result, _ = select_contracts(self.snapshot(), mapping, 'DCE', '20260908')
        self.assertEqual(len(result), 2)

    def test_mapped_main_without_volume_is_skipped(self):
        data = self.snapshot()
        data.loc[data.ts_code.eq('M2701.DCE'), 'vol'] = 0
        mapping = pd.DataFrame([dict(ts_code='M.DCE', trade_date='20260908', mapping_ts_code='M2701.DCE')])
        result, skipped = select_contracts(data, mapping, 'DCE', '20260908')
        self.assertTrue(result.empty)
        self.assertEqual(skipped[0]['reason'], 'mapped_main_no_volume')


if __name__ == '__main__':
    unittest.main()
