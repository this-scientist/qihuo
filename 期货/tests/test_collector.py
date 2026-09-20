import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from collector import Collector, DataError, validate_daily, commodity_totals
from collector import LIMITS
from transport import TushareHTTP
import requests


def quote(code='M2701.DCE', date='20260908', oi=100):
    return dict(ts_code=code, trade_date=date, open=10, high=12,
                low=9, close=11, settle=11, vol=20, amount=30, oi=oi)


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.fail = False

    def query(self, name, **kw):
        self.calls.append((name, kw))
        if self.fail:
            raise RuntimeError('network failure')
        if name == 'fut_trade_cal':
            return pd.DataFrame([dict(exchange=kw['exchange'], cal_date='20260908', is_open=1)])
        return pd.DataFrame([quote()])


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.api = FakeAPI()
        self.c = Collector(self.api, Path(self.tmp.name), exchanges=['DCE'], interval=0, retries=1)

    def test_wrong_date_rejected(self):
        with self.assertRaises(DataError):
            validate_daily(pd.DataFrame([quote(date='20260907')]), '20260908', 'DCE')

    def test_invalid_ohlc_rejected(self):
        row = quote()
        row['high'] = 8
        with self.assertRaises(DataError):
            validate_daily(pd.DataFrame([row]), '20260908', 'DCE')

    def test_negative_oi_rejected(self):
        with self.assertRaises(DataError):
            validate_daily(pd.DataFrame([quote(oi=-1)]), '20260908', 'DCE')

    def test_wrong_exchange_rejected(self):
        with self.assertRaises(DataError):
            validate_daily(pd.DataFrame([quote(code='CU2701.SHF')]), '20260908', 'DCE')

    def test_conflicting_duplicates_rejected(self):
        with self.assertRaises(DataError):
            validate_daily(pd.DataFrame([quote(), quote(oi=200)]), '20260908', 'DCE')

    def test_identical_duplicates_removed(self):
        self.assertEqual(len(validate_daily(pd.DataFrame([quote(), quote()]), '20260908', 'DCE')), 1)

    def test_api_failure_raises(self):
        self.api.fail = True
        with self.assertRaises(DataError):
            self.c.call('fut_daily', trade_date='20260908')

    def test_calendar_uses_futures_endpoint(self):
        self.assertEqual(self.c.calendar('DCE', '20260908', '20260908'), ['20260908'])
        self.assertEqual(self.api.calls[0][0], 'fut_trade_cal')

    def test_existing_unverified_file_is_not_skipped(self):
        path = Path(self.tmp.name) / 'raw/daily/DCE/20260908.csv'
        path.parent.mkdir(parents=True)
        pd.DataFrame([quote(oi=1)]).to_csv(path, index=False)
        self.c.partition('fut_daily', 'daily', 'DCE', '20260908')
        self.assertEqual(pd.read_csv(path).oi.iloc[0], 100)

    def test_validated_cache_detects_tampering(self):
        self.c.partition('fut_daily', 'daily', 'DCE', '20260908')
        before = len(self.api.calls)
        self.c.partition('fut_daily', 'daily', 'DCE', '20260908')
        self.assertEqual(len(self.api.calls), before)
        path = Path(self.tmp.name) / 'raw/daily/DCE/20260908.csv'
        pd.DataFrame([quote(oi=2)]).to_csv(path, index=False)
        self.c.partition('fut_daily', 'daily', 'DCE', '20260908')
        self.assertGreater(len(self.api.calls), before)

    def test_totals_exclude_synthetic_contracts(self):
        data = pd.DataFrame([quote(), quote('M2705.DCE', oi=50), quote('M.DCE', oi=999), quote('ML.DCE', oi=999)])
        basic = pd.DataFrame([dict(ts_code='M2701.DCE', fut_code='M', exchange='DCE'), dict(ts_code='M2705.DCE', fut_code='M', exchange='DCE')])
        result = commodity_totals(data, basic)
        self.assertEqual(result.total_oi.iloc[0], 150)
        self.assertEqual(result.contract_count.iloc[0], 2)

    def test_missing_contract_is_fetched_individually(self):
        original = self.api.query
        def query(name, **kw):
            if kw.get('ts_code') == 'M2705.DCE':
                return pd.DataFrame([quote('M2705.DCE', oi=50)])
            return original(name, **kw)
        self.api.query = query
        df = self.c.partition('fut_daily', 'daily', 'DCE', '20260908', ['M2701.DCE', 'M2705.DCE'])
        self.assertEqual(set(df.ts_code), {'M2701.DCE', 'M2705.DCE'})

    def test_missing_contract_does_not_publish_receipt(self):
        with self.assertRaises(DataError):
            self.c.partition('fut_daily', 'daily', 'DCE', '20260908', ['M2701.DCE', 'M2705.DCE'])
        self.assertFalse((Path(self.tmp.name) / 'raw/daily/DCE/20260908.json').exists())

    def test_zero_price_with_active_volume_rejected(self):
        row = quote()
        row['close'] = 0
        with self.assertRaises(DataError):
            validate_daily(pd.DataFrame([row]), '20260908', 'DCE')

    def test_totals_do_not_coerce_missing_oi_to_zero(self):
        basic = pd.DataFrame([dict(ts_code='M2701.DCE', fut_code='M', exchange='DCE')])
        with self.assertRaises(DataError):
            commodity_totals(pd.DataFrame([quote(oi=None)]), basic)

    def test_special_f_contracts_are_audited_and_excluded(self):
        base = dict(exchange='DCE', list_date='20200101', delist_date='20270101', d_month='202701')
        def query(name, **kw):
            if kw.get('fut_type') == '1':
                return pd.DataFrame([dict(base, ts_code='M2701.DCE', fut_code='M'), dict(base, ts_code='L2701F.DCE', fut_code='L_F')])
            return pd.DataFrame([dict(base, ts_code='M.DCE', fut_code='M')])
        self.api.query = query
        ordinary, _ = self.c.basic('DCE')
        self.assertEqual(ordinary.ts_code.tolist(), ['M2701.DCE'])
        self.assertTrue((Path(self.tmp.name) / 'raw/basic/fut_excluded_DCE.csv').exists())

    def test_dormant_contract_missing_prices_keeps_oi_with_invalid_price_flag(self):
        row = quote()
        row.update(open=None, high=None, low=None, vol=0)
        result = validate_daily(pd.DataFrame([row]), '20260908', 'DCE')
        self.assertEqual(result.oi.iloc[0], 100)
        self.assertFalse(result.price_valid.iloc[0])

    def test_partial_exchange_failure_does_not_publish_merged_day(self):
        self.c.exchanges = ['DCE', 'CZCE']
        original = self.api.query
        def query(name, **kw):
            if kw.get('exchange') == 'CZCE':
                raise RuntimeError('network error')
            if name == 'fut_basic':
                code = 'M2701.DCE' if kw['fut_type'] == '1' else 'M.DCE'
                return pd.DataFrame([dict(ts_code=code, fut_code='M', exchange='DCE', list_date='20200101', delist_date='20270101', d_month='202701')])
            return original(name, **kw)
        self.api.query = query
        report = self.c.run('20260908', '20260908', ['daily'])
        self.assertFalse(report['success'])
        self.assertTrue((Path(self.tmp.name) / 'raw/daily/DCE/20260908.csv').exists())
        self.assertFalse((Path(self.tmp.name) / 'raw/daily/20260908.csv').exists())

    def test_row_cap_refetches_each_contract(self):
        old_limit = LIMITS['fut_daily']
        self.addCleanup(LIMITS.__setitem__, 'fut_daily', old_limit)
        LIMITS['fut_daily'] = 2
        def query(name, **kw):
            if 'ts_code' in kw:
                return pd.DataFrame([quote(kw['ts_code'])])
            return pd.DataFrame([quote(), quote('ML.DCE')])
        self.api.query = query
        result = self.c.partition('fut_daily', 'daily', 'DCE', '20260908', ['M2701.DCE', 'M2705.DCE'])
        self.assertEqual(set(result.ts_code), {'M2701.DCE', 'M2705.DCE'})

    def test_http_error_never_becomes_empty_success(self):
        transport = TushareHTTP('test-token', 'https://example.invalid')
        class Session:
            def post(self, *args, **kwargs):
                response = requests.Response()
                response.status_code = 500
                return response
        transport.session = Session()
        with self.assertRaises(requests.HTTPError):
            transport.query('fut_daily')


if __name__ == '__main__':
    unittest.main()
