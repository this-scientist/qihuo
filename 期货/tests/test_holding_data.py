import sys
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector import DataError
from holding_data import (collect_main_holdings, collect_update_holdings,
                          holding_query, summarize_holding, validate_holding,
                          unavailable_summary)


DATE = '20260924'


def target(**overrides):
    value = dict(ts_code='M.DCE', contract='M2701.DCE', exchange='DCE',
                 trade_date=DATE, main_oi=10000)
    value.update(overrides)
    return value


def holding_frame(rows=22, **overrides):
    records = []
    for index in range(rows):
        record = dict(
            trade_date=DATE,
            symbol='M2701',
            broker=f'会员{index:02d}',
            vol=1000 + index,
            vol_chg=index - 10,
            long_hld=100 + index,
            long_chg=index + 1,
            short_hld=300 - index,
            short_chg=2 * index,
            exchange='DCE',
        )
        record.update(overrides)
        records.append(record)
    return pd.DataFrame(records)


class HoldingQueryTests(unittest.TestCase):
    def test_exchange_specific_symbols(self):
        self.assertEqual(
            holding_query('M2701.DCE', 'DCE'),
            {'trade_date': None, 'symbol': 'M2701', 'exchange': 'DCE'},
        )
        self.assertEqual(holding_query('RB2701.SHF', 'SHFE')['symbol'], 'RB2701')
        self.assertEqual(holding_query('SI2611.GFE', 'GFEX')['symbol'], 'si2611')
        self.assertEqual(holding_query('TA2701.ZCE', 'CZCE')['symbol'], 'TA701')
        self.assertEqual(holding_query('TA701.ZCE', 'CZCE')['symbol'], 'TA701')
        self.assertEqual(holding_query('SC2611.INE', 'INE')['exchange'], 'SHFE')

    def test_invalid_czce_contract_is_rejected(self):
        with self.assertRaises(DataError):
            holding_query('TA27.ZCE', 'CZCE')


class HoldingSummaryTests(unittest.TestCase):
    def test_long_and_short_rankings_are_cut_independently(self):
        frame = holding_frame()
        summary = summarize_holding(frame, target(), main_oi=10000)
        expected_long = sum(range(102, 122))
        expected_short = sum(range(281, 301))
        self.assertEqual(summary['holding_status'], 'available')
        self.assertEqual(summary['top20_long'], expected_long)
        self.assertEqual(summary['top20_short'], expected_short)
        self.assertEqual(summary['top20_net'], expected_long - expected_short)
        self.assertEqual(summary['top20_long_change'], sum(range(3, 23)))
        self.assertEqual(summary['top20_short_change'], sum(2 * value for value in range(20)))
        self.assertEqual(summary['top20_net_change'], sum(range(3, 23)) - sum(2 * value for value in range(20)))
        self.assertEqual([row['broker'] for row in summary['top_long_brokers']],
                         ['会员21', '会员20', '会员19', '会员18', '会员17'])
        self.assertEqual([row['broker'] for row in summary['top_short_brokers']],
                         ['会员00', '会员01', '会员02', '会员03', '会员04'])
        self.assertAlmostEqual(summary['top20_long_concentration'], expected_long / 10000)
        self.assertAlmostEqual(summary['top20_short_concentration'], expected_short / 10000)

    def test_missing_change_in_selected_rank_keeps_change_missing(self):
        frame = holding_frame()
        frame.loc[frame.broker.eq('会员21'), 'long_chg'] = None
        summary = summarize_holding(frame, target(), main_oi=10000)
        self.assertIsNone(summary['top20_long_change'])
        self.assertIsNotNone(summary['top20_short_change'])
        self.assertIsNone(summary['top20_net_change'])

    def test_invalid_broker_names_keep_numeric_summary_only(self):
        frame = holding_frame()
        frame.loc[0, 'broker'] = '损坏�席位'
        summary = summarize_holding(frame, target(), main_oi=10000)
        self.assertEqual(summary['holding_status'], 'numeric_only')
        self.assertEqual(summary['holding_reason'], '席位名称源数据异常')
        self.assertGreater(summary['top20_long'], 0)
        self.assertEqual(summary['top_long_brokers'], [])
        self.assertEqual(summary['top_short_brokers'], [])

    def test_missing_main_oi_only_omits_concentration(self):
        summary = summarize_holding(holding_frame(), target(main_oi=None), main_oi=None)
        self.assertEqual(summary['holding_status'], 'available')
        self.assertIsNone(summary['top20_long_concentration'])
        self.assertIsNone(summary['top20_short_concentration'])

    def test_impossible_concentration_invalidates_summary(self):
        summary = summarize_holding(holding_frame(), target(main_oi=100), main_oi=100)
        self.assertEqual(summary['holding_status'], 'invalid')
        self.assertIn('集中度', summary['holding_reason'])
        self.assertIsNone(summary['top20_long'])
        self.assertEqual(summary['top_long_brokers'], [])

    def test_wrong_identity_negative_holdings_and_row_cap_are_rejected(self):
        cases = [
            holding_frame(trade_date='20260923'),
            holding_frame(symbol='Y2701'),
            holding_frame(exchange='CZCE'),
            holding_frame(long_hld=-1),
            holding_frame(rows=2000),
        ]
        for frame in cases:
            with self.subTest(first=frame.iloc[0].to_dict(), rows=len(frame)):
                with self.assertRaises(DataError):
                    validate_holding(frame, target())

    def test_ine_accepts_shfe_route_but_not_unrelated_contract(self):
        frame = holding_frame(symbol='SC2611', exchange='SHFE')
        validated = validate_holding(
            frame,
            target(ts_code='SC.INE', contract='SC2611.INE', exchange='INE'),
        )
        self.assertEqual(len(validated), 22)
        frame['symbol'] = 'NR2611'
        with self.assertRaises(DataError):
            validate_holding(
                frame,
                target(ts_code='SC.INE', contract='SC2611.INE', exchange='INE'),
            )

    def test_unavailable_summary_never_invents_zero(self):
        summary = unavailable_summary(target(), 'unavailable', '交易所未发布')
        self.assertEqual(summary['holding_status'], 'unavailable')
        self.assertIsNone(summary['top20_long'])
        self.assertIsNone(summary['top20_net_change'])
        self.assertEqual(summary['top_long_brokers'], [])


class FakeCollector:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, name, **params):
        self.calls.append(dict(api=name, **params))
        value = self.responses[params['symbol']]
        if isinstance(value, Exception):
            raise value
        return value.copy()


class HoldingCollectionTests(unittest.TestCase):
    def selected(self):
        return pd.DataFrame([
            dict(ts_code='M2701.DCE', main_code='M.DCE', role='main', exchange='DCE', oi=10000),
            dict(ts_code='M2705.DCE', main_code='M.DCE', role='secondary', exchange='DCE', oi=9000),
            dict(ts_code='SI2611.GFE', main_code='SI.GFE', role='main', exchange='GFEX', oi=8000),
        ])

    def test_collects_only_real_main_and_keeps_contract_failures_local(self):
        dce = holding_frame()
        collector = FakeCollector({'M2701': dce, 'si2611': pd.DataFrame(columns=dce.columns)})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = collect_main_holdings(collector, root, self.selected(), DATE)
            self.assertEqual([call['symbol'] for call in collector.calls], ['M2701', 'si2611'])
            self.assertTrue(all(call['api'] == 'fut_holding' for call in collector.calls))
            self.assertEqual(report['counts']['available'], 1)
            self.assertEqual(report['counts']['unavailable'], 1)
            self.assertFalse((root/'raw/holding/DCE'/DATE/'M2705.csv').exists())
            raw = root/'raw/holding/DCE'/DATE/'M2701.csv'
            receipt = raw.with_suffix('.json')
            self.assertTrue(raw.exists())
            self.assertTrue(receipt.exists())
            self.assertEqual(json.loads(receipt.read_text(encoding='utf-8'))['api'], 'fut_holding')
            payload = json.loads((root/f'processed/holding/{DATE}.json').read_text(encoding='utf-8'))
            self.assertEqual(payload['asof'], DATE)
            self.assertEqual([row['ts_code'] for row in payload['records']], ['M.DCE', 'SI.GFE'])
            self.assertEqual(payload['records'][1]['holding_status'], 'unavailable')
            quality = json.loads((root/f'quality/holding_{DATE}.json').read_text(encoding='utf-8'))
            self.assertEqual(quality['counts'], report['counts'])

    def test_valid_cache_avoids_second_network_call(self):
        collector = FakeCollector({'M2701': holding_frame(), 'si2611': pd.DataFrame(columns=holding_frame().columns)})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = collect_main_holdings(collector, root, self.selected(), DATE)
            self.assertEqual(len(collector.calls), 2)
            collector.responses = {'M2701': DataError('network should not run'),
                                   'si2611': pd.DataFrame(columns=holding_frame().columns)}
            second = collect_main_holdings(collector, root, self.selected(), DATE)
            self.assertEqual(len(collector.calls), 3)
            self.assertEqual(first['records'][0], second['records'][0])

    def test_missing_selected_file_returns_explicit_report(self):
        collector = FakeCollector({})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = collect_update_holdings(collector, root, DATE)
            self.assertEqual(report['status'], 'unavailable')
            self.assertIn('selected', report['reason'])
            self.assertEqual(report['counts']['available'], 0)
            self.assertTrue((root/f'quality/holding_{DATE}.json').exists())

    def test_research_update_collects_holdings_after_main_contracts_publish(self):
        with patch.dict(os.environ, {
                'OAR_TUSHARE_TOKEN': 'test-token',
                'OAR_TUSHARE_HTTP_URL': 'https://example.invalid'}):
            import research_server
            from trend_model import MODEL_VERSION

        collector = object()
        payload = dict(asof=DATE, quality={'success': True}, records=[], decisions=[],
                       factors=[], model_version=MODEL_VERSION, phase_settings={})
        store = research_server.ResearchStore.__new__(research_server.ResearchStore)
        store.root = Path('test-root')
        store.lock = threading.RLock()
        store.job = {'status': 'queued'}
        store.phase = object()
        store.payloads = {}
        store.option_cache = {}
        store._persist_state = Mock()
        store.copy_supplements = Mock()

        with patch('fetch_futures_data.make_collector', return_value=collector), \
                patch('focused.run_focused', return_value={
                    'published_days': [DATE], 'partial_days': []}), \
                patch('holding_data.collect_update_holdings') as collect, \
                patch('history.prepare_history'), \
                patch('research_server.read_csv', return_value=pd.DataFrame()), \
                patch('research_server.build_payload', return_value=payload), \
                patch('research_server.publish_snapshot', return_value=payload), \
                patch('research_server.mysql_cache_put', return_value=True):
            store._worker('update', DATE, {'force': False})

        collect.assert_called_once_with(
            collector, store.root/'updates'/DATE, DATE, False)
        self.assertEqual(store.job['status'], 'success')


if __name__ == '__main__':
    unittest.main()
