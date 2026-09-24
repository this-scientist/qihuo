import unittest
from datetime import datetime, timedelta

from realtime import (age_seconds, fetch_quotes, parse_quote, snapshot, clear_cache)

# 真实抓取到的上期所铜 2610 盘中报价；开高低/最新/昨结已与东财同一时刻数据交叉验证
REAL = ('铜2610,110224,110790.000,111160.000,110560.000,0.000,110810.000,110820.000,'
        '110820.000,0.000,111330.000,2,47,115079.000,48250,沪,铜,2026-09-24,0,,,,')


def line_of(symbol, last='1000', pre='990'):
    payload = ('测试,101500,1005.000,1010.000,995.000,0.000,999.000,1001.000,%s,0.000,%s,'
               '3,5,8000.000,1200,沪,测,2026-09-24,0' % (last, pre))
    return 'var hq_str_nf_%s="%s";' % (symbol, payload)


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class Recorder:
    """记录请求 URL，按 URL 里的合约代码返回对应行情。"""

    def __init__(self, extra='', fail=False):
        self.urls, self.extra, self.fail = [], extra, fail

    def __call__(self, url, headers=None, timeout=None):
        self.urls.append(url)
        if self.fail:
            raise OSError('upstream down')
        symbols = [item.replace('nf_', '') for item in url.split('list=', 1)[1].split(',')]
        return FakeResponse(';'.join(line_of(s) for s in symbols) + self.extra)


class ParseTests(unittest.TestCase):
    def test_parses_cross_verified_sina_line(self):
        quote = parse_quote('CU2610.SHF', REAL)
        self.assertEqual(quote['ts_code'], 'CU2610.SHF')
        self.assertEqual(quote['name'], '铜2610')
        self.assertEqual(quote['time'], '11:02:24')
        self.assertEqual(quote['open'], 110790.0)
        self.assertEqual(quote['high'], 111160.0)
        self.assertEqual(quote['low'], 110560.0)
        self.assertEqual(quote['last'], 110820.0)
        self.assertEqual(quote['pre_settle'], 111330.0)
        self.assertEqual(quote['volume'], 48250.0)
        self.assertEqual(quote['oi'], 115079.0)
        self.assertEqual(quote['date'], '2026-09-24')

    def test_exposes_the_bid_ask_the_daily_pipeline_lacks(self):
        quote = parse_quote('CU2610.SHF', REAL)
        self.assertEqual(quote['bid'], 110810.0)
        self.assertEqual(quote['ask'], 110820.0)
        self.assertEqual(quote['bid_volume'], 2.0)
        self.assertEqual(quote['ask_volume'], 47.0)
        self.assertEqual(quote['spread'], 10.0)

    def test_change_pct_is_measured_against_previous_settle(self):
        quote = parse_quote('CU2610.SHF', REAL)
        self.assertAlmostEqual(quote['change_pct'], (110820 / 111330 - 1) * 100, places=6)

    def test_missing_previous_settle_yields_no_change(self):
        payload = REAL.replace('111330.000', '0.000')
        self.assertIsNone(parse_quote('CU2610.SHF', payload)['change_pct'])

    def test_rejects_truncated_and_priceless_lines(self):
        self.assertIsNone(parse_quote('CU2610.SHF', '铜2610,110224,110790'))
        self.assertIsNone(parse_quote('CU2610.SHF', ''))
        self.assertIsNone(parse_quote('CU2610.SHF', None))
        blank = ','.join(['铜2610', '110224'] + [''] * 20)
        self.assertIsNone(parse_quote('CU2610.SHF', blank))

    def test_age_seconds_uses_the_quote_timestamp(self):
        quote = {'date': '2026-09-24', 'time': '11:02:24'}
        self.assertEqual(age_seconds(quote, now=datetime(2026, 9, 24, 11, 2, 54)), 30.0)
        self.assertEqual(age_seconds(quote, now=datetime(2026, 9, 24, 11, 2, 24)), 0.0)
        self.assertIsNone(age_seconds({'date': '', 'time': ''}))


class FetchTests(unittest.TestCase):
    def test_maps_symbols_back_to_ts_code(self):
        quotes, error = fetch_quotes(['CU2610.SHF', 'RB2701.SHF'], get=Recorder())
        self.assertIsNone(error)
        self.assertEqual(sorted(quotes), ['CU2610.SHF', 'RB2701.SHF'])
        self.assertEqual(quotes['RB2701.SHF']['last'], 1000.0)

    def test_chunks_large_requests_instead_of_one_long_url(self):
        codes = ['AA%04d.SHF' % index for index in range(65)]
        recorder = Recorder()
        quotes, _ = fetch_quotes(codes, get=recorder)
        self.assertEqual(len(recorder.urls), 3)
        self.assertEqual(len(quotes), 65)

    def test_ignores_symbols_that_were_not_requested(self):
        quotes, _ = fetch_quotes(['CU2610.SHF'], get=Recorder(extra=';' + line_of('RB2701')))
        self.assertEqual(list(quotes), ['CU2610.SHF'])

    def test_upstream_failure_degrades_instead_of_raising(self):
        quotes, error = fetch_quotes(['CU2610.SHF'], get=Recorder(fail=True))
        self.assertEqual(quotes, {})
        self.assertIn('OSError', error)

    def test_empty_response_is_reported_not_silently_ok(self):
        quotes, error = fetch_quotes(['CU2610.SHF'], get=lambda *a, **k: FakeResponse(''))
        self.assertEqual(quotes, {})
        self.assertIn('没有返回可用报价', error)

    def test_no_codes_makes_no_request(self):
        recorder = Recorder()
        self.assertEqual(fetch_quotes([], get=recorder), ({}, None))
        self.assertEqual(recorder.urls, [])


class SnapshotCacheTests(unittest.TestCase):
    def setUp(self):
        clear_cache()

    def test_serves_from_cache_within_ttl(self):
        recorder = Recorder()
        first = snapshot(['CU2610.SHF'], get=recorder, now=100.0)
        second = snapshot(['CU2610.SHF'], get=recorder, now=102.0)
        self.assertFalse(first['cached'])
        self.assertTrue(second['cached'])
        self.assertEqual(len(recorder.urls), 1)
        self.assertEqual(second['quotes']['CU2610.SHF']['last'], 1000.0)

    def test_refetches_after_ttl(self):
        recorder = Recorder()
        snapshot(['CU2610.SHF'], get=recorder, now=100.0)
        snapshot(['CU2610.SHF'], get=recorder, now=100.0 + 6.0)
        self.assertEqual(len(recorder.urls), 2)

    def test_caches_failures_so_upstream_is_not_hammered(self):
        recorder = Recorder(fail=True)
        snapshot(['CU2610.SHF'], get=recorder, now=100.0)
        snapshot(['CU2610.SHF'], get=recorder, now=101.0)
        self.assertEqual(len(recorder.urls), 1)

    def test_empty_code_list_short_circuits(self):
        recorder = Recorder()
        result = snapshot([], get=recorder)
        self.assertEqual(result['quotes'], {})
        self.assertEqual(recorder.urls, [])


if __name__ == '__main__':
    unittest.main()
