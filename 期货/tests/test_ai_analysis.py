# -*- coding: utf-8 -*-
"""DeepSeek 分析模块：请求体构造、key 不外泄、JSON 容错、错误映射、缺 key 报错。"""
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_analysis
from ai_analysis import (LIMITATIONS, analyze, build_messages, configured, extract_levels,
                         load_config, parse_analysis)

CONFIG = dict(api_key='sk-secret-test', base_url='https://api.example.test',
              model='deepseek-v4-flash', timeout=5)
CONTEXT = {'品种': {'代码': 'LC.GFE', '名称': '碳酸锂'}, '价格': {'真实合约最新价': 134500.0}}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def captured_opener(payload, sink):
    def opener(request, timeout=None):
        sink['url'] = request.full_url
        sink['headers'] = dict(request.headers)
        sink['body'] = json.loads(request.data.decode('utf-8'))
        sink['timeout'] = timeout
        return FakeResponse(payload)
    return opener


def reply(content):
    return dict(model='deepseek-v4-flash', choices=[dict(message=dict(content=content))],
                usage=dict(prompt_tokens=100, completion_tokens=50))


VALID = json.dumps(dict(
    position=dict(stance='long', instrument='Call', delta_range='0.20-0.35', dte_range='20-45天',
                  stop='跌破 128000 止损', reasoning=['结构偏多', '持仓增加']),
    levels=dict(support=[dict(price=128000, why='前低')], resistance=[dict(price=140000, why='前高')]),
    industry=dict(summary='供需过剩', drivers=['产能投放'], uncertainty='非实时'),
    risks=['需求不及预期'], invalidations=['跌破前低'], data_gaps=['库存未接入'], disclaimer='仅供参考'))


class AiAnalysisTests(unittest.TestCase):
    def test_prompt_carries_context_and_limitations(self):
        messages = build_messages(CONTEXT)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertIn('LC.GFE', messages[1]['content'])
        self.assertIn('联网', ai_analysis.SYSTEM_PROMPT)
        self.assertTrue(any('联网' in item for item in LIMITATIONS))

    def test_analyze_parses_and_never_leaks_key(self):
        sink = {}
        result = analyze(CONTEXT, config=CONFIG, opener=captured_opener(reply(VALID), sink))
        self.assertEqual(sink['url'], 'https://api.example.test/chat/completions')
        self.assertEqual(sink['body']['model'], 'deepseek-v4-flash')
        self.assertEqual(sink['body']['messages'][1]['content'], ai_analysis.build_prompt(CONTEXT))
        self.assertNotIn('sk-secret-test', json.dumps(sink['body']))
        self.assertTrue(any(value == 'Bearer sk-secret-test' for value in sink['headers'].values()))
        self.assertEqual(result['analysis']['position']['stance'], 'long')
        self.assertIsNone(result['parse_error'])
        self.assertEqual(result['ai_levels']['support'][0]['price'], 128000.0)
        self.assertEqual(result['limitations'], LIMITATIONS)

    def test_analyze_accepts_fenced_json(self):
        sink = {}
        fenced = '```json\n' + VALID + '\n```'
        result = analyze(CONTEXT, config=CONFIG, opener=captured_opener(reply(fenced), sink))
        self.assertEqual(result['analysis']['industry']['summary'], '供需过剩')

    def test_analyze_extracts_json_from_prose(self):
        sink = {}
        noisy = '以下是结论：\n' + VALID + '\n以上。'
        result = analyze(CONTEXT, config=CONFIG, opener=captured_opener(reply(noisy), sink))
        self.assertIsNotNone(result['analysis'])

    def test_unparsable_output_reports_error_and_keeps_raw(self):
        sink = {}
        result = analyze(CONTEXT, config=CONFIG, opener=captured_opener(reply('抱歉，我无法回答。'), sink))
        self.assertIsNone(result['analysis'])
        self.assertTrue(result['parse_error'])
        self.assertIn('抱歉', result['raw'])

    def test_missing_key_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, 'DEEPSEEK_API_KEY'):
            analyze(CONTEXT, config=dict(CONFIG, api_key=None))

    def test_http_error_maps_to_value_error(self):
        def opener(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 401, 'Unauthorized', {}, None)
        with self.assertRaisesRegex(ValueError, '401'):
            analyze(CONTEXT, config=CONFIG, opener=opener)

    def test_network_error_maps_to_value_error(self):
        def opener(request, timeout=None):
            raise urllib.error.URLError('name resolution failed')
        with self.assertRaisesRegex(ValueError, '无法连接'):
            analyze(CONTEXT, config=CONFIG, opener=opener)

    def test_api_error_body_maps_to_value_error(self):
        sink = {}
        with self.assertRaisesRegex(ValueError, '额度'):
            analyze(CONTEXT, config=CONFIG,
                    opener=captured_opener({'error': {'message': '额度不足'}}, sink))

    def test_empty_choices_reports_parse_error(self):
        sink = {}
        result = analyze(CONTEXT, config=CONFIG, opener=captured_opener({'choices': []}, sink))
        self.assertIsNone(result['analysis'])
        self.assertTrue(result['parse_error'])

    def test_extract_levels_tolerates_plain_numbers(self):
        levels = extract_levels({'levels': {'support': [128000, {'price': '127000', 'why': '缺口'}],
                                            'resistance': []}})
        self.assertEqual([item['price'] for item in levels['support']], [128000.0, 127000.0])
        self.assertEqual(levels['resistance'], [])

    def test_parse_analysis_handles_empty(self):
        self.assertTrue(parse_analysis('')['parse_error'])
        self.assertTrue(parse_analysis(None)['parse_error'])

    def test_config_reads_env_then_file(self):
        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'sk-env', 'DEEPSEEK_MODEL': 'm-env'}, clear=False):
            config = load_config(Path('nonexistent.env'))
        self.assertEqual(config['api_key'], 'sk-env')
        self.assertEqual(config['model'], 'm-env')
        self.assertEqual(config['base_url'], 'https://api.deepseek.com')
        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'sk-env'}, clear=False):
            self.assertTrue(configured(Path('nonexistent.env')))


if __name__ == '__main__':
    unittest.main()
