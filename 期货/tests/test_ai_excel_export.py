# -*- coding: utf-8 -*-
import io
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_excel_export import build_ai_excel, export_filename, workbook_response_headers


def sheet_names(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        workbook = archive.read('xl/workbook.xml').decode('utf-8')
    return workbook


def workbook_text(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        return '\n'.join(
            archive.read(name).decode('utf-8')
            for name in archive.namelist()
            if name.startswith('xl/worksheets/sheet')
        )


PAYLOAD = {
    'asof': '20260924',
    'data_hash': 'abc123',
    'quality': {'success': True, 'universe': 1},
    'exclusions': [{'ts_code': 'X.DCE', 'reason': '历史不足'}],
    'supplemental_status': [{'ts_code': 'M.DCE', 'spot': 'missing'}],
    'factors': [
        {'key': 'return20', 'label': '20日涨跌幅', 'group': '价格 / 收益', 'unit': '%'},
        {'key': 'adx', 'label': 'ADX14', 'group': '趋势强度', 'unit': ''},
    ],
    'records': [{
        'ts_code': 'M.DCE', 'name': '豆粕', 'sector': '农产品',
        'main_code': 'M2701.DCE', 'secondary_code': 'M2705.DCE',
        'direction': 'long', 'trend_direction': 'long', 'phase': '趋势启动',
        'close': 3100.0, 'return20': 8.5, 'rps20': 91.2, 'adx': 28.0,
        'atr14': None, 'oi_change5': 4.2, 'carry_annualized': -2.1,
        'structure': 'backwardation',
        'trader_positions': {
            'holding_status': 'available', 'holding_contract': 'M2701.DCE',
            'top20_long': 1000, 'top20_short': 800, 'top20_net': 200,
            'top20_long_change': 30, 'top20_short_change': -10,
            'top20_net_change': 40, 'top20_long_concentration': 0.3,
            'top20_short_concentration': 0.25,
            'top_long_brokers': [{'name': 'A席位', 'value': 100}],
            'top_short_brokers': [],
        },
        'curve': [
            {'ts_code': 'M2701.DCE', 'delivery_month': '2701', 'settle': 3100, 'oi': 10000, 'vol': 2000},
            {'ts_code': 'M2705.DCE', 'delivery_month': '2705', 'settle': 3050, 'oi': 8000, 'vol': 1500},
        ],
        'curvature': None,
    }],
    'decisions': [{
        'ts_code': 'M.DCE', 'name': '豆粕', 'sector': '农产品',
        'main_code': 'M2701.DCE', 'decision_direction': 'long',
        'decision_side': 'long', 'state_v2': 'START',
        'trend_state_label': '启动', 'trend_option_gate': 'allow',
        'dir_score': 88, 'start_score': 76,
        'price_rps': 90, 'vol_rps': 70, 'oi_change_rps': 65,
        'structure_confirm': 'yes', 'option_action': 'buy_call',
    }],
    'candles': {'M.DCE': [['20260923', 3000, 3120, 2980, 3100, 20000, 100000]]},
    'moving': {'M.DCE': {'ema20': [3010]}},
}

OPTIONS = {
    'records': [{
        'ts_code': 'M2701C3200.DCE', 'main_code': 'M.DCE',
        'underlying_code': 'M2701.DCE', 'call_put': 'C',
        'exercise_price': 3200, 'premium': 50, 'vol': 120, 'oi': 900,
        'delta': 0.35, 'gamma': 0.01, 'theta': -0.02, 'vega': 0.13,
        'iv_reference': 18.2, 'days_to_expiry': 32, 'moneyness_pct': 3.2,
        'tradability': {'score': 82, 'grade': 'A'},
    }]
}

SCANNER = {
    'long': [{
        'ts_code': 'M.DCE', 'name': '豆粕', 'direction': 'long',
        'explosion_score': 84, 'signals_met': 5, 'signals_applicable': 7,
        'resonance': True, 'tenbagger_score': 72, 'tenbagger_label': '观察',
        'best_option_code': 'M2701C3200.DCE',
    }],
    'short': [],
}


class AiExcelExportTests(unittest.TestCase):
    def test_workbook_contains_model_ready_sheets_and_chinese_labels(self):
        blob = build_ai_excel(PAYLOAD, OPTIONS, SCANNER)
        names = sheet_names(blob)
        for title in ['说明', '品种总览', '决策信号', '技术因子', '期限结构',
                      '席位持仓', '期权链', '期权机会', '图表序列', '数据质量']:
            self.assertIn(title, names)
        text = workbook_text(blob)
        self.assertIn('20日涨跌幅', text)
        self.assertIn('豆粕', text)
        self.assertIn('M2701C3200.DCE', text)

    def test_missing_values_stay_blank_instead_of_zero(self):
        blob = build_ai_excel(PAYLOAD, OPTIONS, SCANNER)
        text = workbook_text(blob)
        self.assertIn('ATR14', text)
        self.assertNotIn('None', text)

    def test_download_headers_are_excel_specific(self):
        headers = workbook_response_headers('20260924')
        self.assertEqual(headers['Content-Type'],
                         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn(export_filename('20260924'), headers['Content-Disposition'])


if __name__ == '__main__':
    unittest.main()
