# -*- coding: utf-8 -*-
"""候选页自定义品种：与 build_scanner 行同源同形、未知品种报错、真实价位缺失降级、AI 上下文完整。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from option_scanner import build_scanner
from research_server import ai_context, candidate_view, real_levels
from test_option_scanner import option_row, strong_record


class StubStore:
    """只实现 candidate_view/ai_context 需要的方法，避免依赖快照与数据库。"""

    def __init__(self, payload, options):
        self._payload = payload
        self._options = options

    def get(self, asof=None):
        return self._payload

    def option_payload(self, asof=None, *args, **kwargs):
        return self._options


def build_fixtures(code='JM.DCE'):
    record = strong_record('long')
    record['ts_code'] = code
    payload = dict(asof='20260918', records=[record], decisions=[dict(ts_code=code,
        trend_state_label='T2 趋势启动', state_v2='START', trend_option_gate='ALLOW')])
    chain = [option_row(strike, side, dte=20) for side in ['C', 'P'] for strike in range(92, 109, 4)]
    return payload, dict(records=chain)


class CandidateViewTests(unittest.TestCase):
    def setUp(self):
        self.payload, self.options = build_fixtures()
        self.store = StubStore(self.payload, self.options)

    def test_candidate_row_has_same_keys_as_scanner_row(self):
        view = candidate_view(self.store, '20260918', 'JM.DCE', 'long')
        scanner_row = build_scanner(self.payload, self.options)['long'][0]
        self.assertEqual(set(view['candidate'].keys()), set(scanner_row.keys()))

    def test_candidate_view_returns_context_blocks(self):
        view = candidate_view(self.store, '20260918', 'JM.DCE', 'long')
        self.assertEqual(view['code'], 'JM.DCE')
        self.assertEqual(view['direction'], 'long')
        self.assertIsNotNone(view['structure'])
        self.assertIn('explosion_score', view['candidate'])
        self.assertTrue(view['candidate']['items'])
        self.assertTrue(view['candidate']['signals'])

    def test_direction_falls_back_to_first_row(self):
        view = candidate_view(self.store, '20260918', 'JM.DCE', 'short')
        self.assertEqual(view['direction'], 'long')

    def test_unknown_code_raises_data_error(self):
        from collector import DataError
        with self.assertRaises(DataError):
            candidate_view(self.store, '20260918', 'NOPE.DCE')

    def test_ai_context_contains_all_sections(self):
        view = candidate_view(self.store, '20260918', 'JM.DCE', 'long')
        levels = dict(last=100.0, atr14=2.0, main_code='JM2609.DCE', support=[dict(price=98.0, sources=['近20日低点'], strength='中', distance_pct=-2.0, touches=2)],
                      resistance=[], coverage=1, notes=[])
        context = ai_context(self.store, '20260918', view, levels)
        for key in ['品种', '价格', '技术面', '商品结构', '期权候选合约', '本地支撑压力位', '数据缺口']:
            self.assertIn(key, context)
        self.assertEqual(context['技术面']['趋势状态'], 'T2 趋势启动')
        self.assertEqual(context['技术面']['生命周期'], 'START')
        self.assertEqual(context['本地支撑压力位']['支撑'][0]['price'], 98.0)
        self.assertTrue(context['期权候选合约'], '应带上主仓/彩票仓候选合约')
        self.assertEqual(context['期权候选合约'][0]['档位'].startswith('主仓'), True)


class RealLevelsTests(unittest.TestCase):
    def test_missing_pair_history_degrades_with_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = real_levels(Path(tmp), 'LC.GFE', 'LC2701.GFE')
        self.assertEqual(result['support'], [])
        self.assertEqual(result['resistance'], [])
        self.assertTrue(result['notes'])
        self.assertIn('pair_history', result['notes'][0])

    def test_pair_history_is_read_and_filtered_by_main_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'processed/pair_history'
            directory.mkdir(parents=True)
            lines = ['ts_code,trade_date,open,high,low,close,vol']
            for index in range(60):
                lines.append('LC2701.GFE,2026%04d,100,101,99,100,1000' % (index + 1))
            for index in range(60):
                lines.append('LC2609.GFE,2026%04d,50,51,49,50,1000' % (index + 1))
            (directory / 'LC_GFE.csv').write_text('\n'.join(lines), encoding='utf-8')
            result = real_levels(Path(tmp), 'LC.GFE', 'LC2701.GFE')
        self.assertEqual(result['main_code'], 'LC2701.GFE')
        self.assertTrue(result['support'], '过滤到 LC2701 后应有价位')
        self.assertAlmostEqual(result['last'], 100.0, places=4)
        prices = [item['price'] for item in result['support'] + result['resistance']]
        self.assertNotIn(50.0, [round(price, 4) for price in prices], '不应混入另一合约的价格')


if __name__ == '__main__':
    unittest.main()
