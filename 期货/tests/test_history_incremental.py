import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from collector import atomic_csv, atomic_json
from history import prepare_history_incremental


class IncrementalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.previous = self.root / 'previous'
        self.source = self.root / 'source'

    def write_previous(self, code='A.DCE', main='A2701.DCE'):
        history = pd.DataFrame([
            dict(ts_code=code, trade_date='20260928', mapping_ts_code=main,
                 open=100.0, high=102.0, low=99.0, close=101.0, settle=101.0,
                 raw_close=101.0, adj_factor=1.0, exchange='DCE',
                 adjustment='forward_ratio_same_day_overlap'),
            dict(ts_code=code, trade_date='20260929', mapping_ts_code=main,
                 open=101.0, high=103.0, low=100.0, close=102.0, settle=102.0,
                 raw_close=102.0, adj_factor=1.0, exchange='DCE',
                 adjustment='forward_ratio_same_day_overlap'),
        ])
        pair = pd.DataFrame([
            dict(ts_code=main, trade_date='20260929', role='main', main_code=code,
                 open=101.0, high=103.0, low=100.0, close=102.0, settle=102.0,
                 vol=1000, oi=2000, exchange='DCE'),
            dict(ts_code='A2705.DCE', trade_date='20260929', role='secondary', main_code=code,
                 open=105.0, high=106.0, low=104.0, close=105.0, settle=105.0,
                 vol=800, oi=1800, exchange='DCE'),
        ])
        history_path = self.previous / 'processed/history/A_DCE.csv'
        pair_path = self.previous / 'processed/pair_history/A_DCE.csv'
        atomic_csv(history, history_path)
        atomic_csv(pair, pair_path)
        atomic_json(dict(asof='20260929', prepared=[dict(
            ts_code=code, exchange='DCE',
            history_sha256=hashlib.sha256(history_path.read_bytes()).hexdigest(),
            pair_sha256=hashlib.sha256(pair_path.read_bytes()).hexdigest())],
            exclusions=[]), self.previous / 'quality/history_run.json')

    def selected(self, main='A2701.DCE'):
        return pd.DataFrame([
            dict(ts_code=main, trade_date='20260930', role='main', main_code='A.DCE',
                 open=102.0, high=104.0, low=101.0, close=103.0, settle=103.0,
                 vol=1100, oi=2100, exchange='DCE'),
            dict(ts_code='A2705.DCE', trade_date='20260930', role='secondary', main_code='A.DCE',
                 open=106.0, high=107.0, low=105.0, close=106.0, settle=106.0,
                 vol=900, oi=1900, exchange='DCE'),
        ])

    def test_extends_previous_history_when_main_contract_is_unchanged(self):
        self.write_previous()
        report, remaining = prepare_history_incremental(
            self.source, self.selected(), '20260930', self.previous)
        self.assertEqual(remaining, [])
        self.assertEqual(report['exclusions'], [])
        self.assertEqual(len(report['prepared']), 1)
        history = pd.read_csv(self.source / 'processed/history/A_DCE.csv', dtype={'trade_date': str})
        self.assertEqual(history.trade_date.tolist(), ['20260928', '20260929', '20260930'])
        self.assertEqual(history.mapping_ts_code.iloc[-1], 'A2701.DCE')
        self.assertEqual(history.raw_close.iloc[-1], 103.0)
        pair = pd.read_csv(self.source / 'processed/pair_history/A_DCE.csv', dtype={'trade_date': str})
        self.assertEqual(sorted(pair[pair.trade_date.eq('20260930')].role.tolist()), ['main', 'secondary'])

    def test_roll_change_is_left_for_full_history_preparation(self):
        self.write_previous(main='A2701.DCE')
        report, remaining = prepare_history_incremental(
            self.source, self.selected(main='A2709.DCE'), '20260930', self.previous)
        self.assertEqual(report['prepared'], [])
        self.assertEqual(remaining, ['A.DCE'])


if __name__ == '__main__':
    unittest.main()
