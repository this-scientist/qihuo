import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from option_analysis import black76, greeks, option_metrics
from option_scanner import build_scanner, radar_row, scan_one, pick_contracts, annotate_options, structure_radar, build_opportunities


FUTURE, VOL, RATE = 100.0, 0.25, 0.02
DTE = 40


def option_row(strike, side, vol_lots=3000, oi_lots=5000, dte=DTE):
    time = dte / 365
    premium = black76(FUTURE, float(strike), time, RATE, VOL, side)
    greek = greeks(FUTURE, float(strike), time, RATE, VOL, side)
    return dict(ts_code=f'JM2609-{side}-{strike}.DCE', underlying_code='JM2609.DCE', main_code='JM.DCE',
        role='main', exchange='DCE', call_put=side, exercise_price=float(strike), maturity_date='20261021',
        days_to_expiry=dte, underlying_close=FUTURE, premium=premium, multiplier=60.0,
        premium_per_lot=premium * 60.0, vol=vol_lots, oi=oi_lots, moneyness_pct=(strike / FUTURE - 1) * 100,
        iv_reference=VOL * 100, hv20=20.0, hv60=22.0, model_approximation=True,
        delta=greek['delta'], gamma=greek['gamma'], vega=greek['vega'], theta=greek['theta'])


def strong_record(direction='long'):
    d = direction == 'long'
    # 方向RPS20=92：多头原始RPS92，空头原始RPS8；五日前原始值保证方向加速度同为+14。
    raw_rps, prev_rps = (92.0, 78.0) if d else (8.0, 22.0)
    return dict(ts_code='JM.DCE', name='焦煤', sector='黑色', main_code='JM2609.DCE', direction=direction,
        trend_direction=direction, phase='趋势启动', trend_score=80.0, startup_score=75.0, startup_hits=7,
        directional_rps20=92.0, rps20=raw_rps, rps20_prev5=prev_rps, adx=24.0, adx_slope=4.0, plus_di=28.0 if d else 12.0,
        minus_di=12.0 if d else 28.0, break20_up=d, break55_up=d, break20_down=not d, break55_down=not d,
        signal_base_breakout=True, oi_change5=3.0, oi_change20=6.0, volume_ratio=1.5, spread_change5=5.0 if d else -5.0,
        extension_atr=1.2, atr_percentile=60.0, return5=2.0 if d else -2.0)


def weak_record(direction='long'):
    record = strong_record(direction)
    record.update(directional_rps20=52.0, rps20=52.0, rps20_prev5=51.0, adx=15.0, adx_slope=0.5,
        signal_base_breakout=False, oi_change5=-2.0, oi_change20=-4.0, volume_ratio=0.9, spread_change5=-1.0 if direction == 'long' else 1.0)
    return record


class GreeksTests(unittest.TestCase):
    def test_put_call_parity_and_signs(self):
        call = greeks(100, 100, 0.5, 0.0, 0.2, 'C')
        put = greeks(100, 100, 0.5, 0.0, 0.2, 'P')
        self.assertAlmostEqual(call['delta'] - put['delta'], 1.0, places=8)
        self.assertAlmostEqual(call['gamma'], put['gamma'], places=10)
        self.assertGreater(call['vega'], 0)
        self.assertLess(call['theta'], 0)
        self.assertLess(put['delta'], 0)

    def test_metrics_include_reference_greeks(self):
        meta = dict(ts_code='X.DCE', exercise_price=100, call_put='C', exercise_type='美式', maturity_date='20261021', opt_multiplier=10)
        row = option_metrics(meta, dict(close=3.0, vol=100, oi=200), '20260911', 100, .02)
        self.assertTrue(0 < row['delta'] < 1)
        self.assertGreater(row['gamma'], 0)
        self.assertLess(row['theta'], 0)
        self.assertTrue(row['model_approximation'])


def tb_row(code, delta, gamma, dte, iv=22.0, hv20=24.0, vol=3000, oi=5000, side='C', strike=105.0):
    return dict(ts_code=f'JM2609-{side}-{strike}-{code}.DCE', underlying_code='JM2609.DCE', main_code='JM.DCE',
        role='main', exchange='DCE', call_put=side, exercise_price=strike, maturity_date='20261021',
        days_to_expiry=dte, underlying_close=FUTURE, premium=1.0, multiplier=60.0, premium_per_lot=60.0,
        vol=vol, oi=oi, moneyness_pct=5.0, iv_reference=iv, hv20=hv20, hv60=22.0,
        model_approximation=True, delta=delta, gamma=gamma, vega=0.1, theta=-0.02)


class TenbaggerTests(unittest.TestCase):
    def test_sweet_delta_and_dte_band_wins(self):
        # 甜区：|Delta|0.20 + DTE12；对照：|Delta|0.35（非甜区）+ DTE25。后者Gamma虽高，总分仍低。
        sweet = tb_row('sweet', 0.20, 0.012, 12)
        edge = tb_row('edge', 0.35, 0.020, 25)
        result = scan_one(strong_record('long'), 'long', [sweet, edge])
        tb = result['tenbagger']
        self.assertEqual(tb['best'], sweet['ts_code'])
        best = tb['contracts'][0]['tb_breakdown']
        edge_bd = tb['contracts'][1]['tb_breakdown']
        self.assertEqual(best['delta_band'], 6)       # 0.15–0.30 甜区
        self.assertEqual(best['dte'], 5)             # 7–15 甜区
        self.assertGreater(best['total'], edge_bd['total'])

    def test_iv_overpriced_flagged_and_cheap_scores_higher(self):
        cheap_chain = [tb_row('cheap', 0.20, 0.012, 12, iv=20.0, hv20=24.0)]
        rich_chain = [tb_row('rich', 0.20, 0.012, 12, iv=35.0, hv20=24.0)]
        cheap = scan_one(strong_record('long'), 'long', cheap_chain)['tenbagger']
        rich = scan_one(strong_record('long'), 'long', rich_chain)['tenbagger']
        self.assertEqual(cheap['contracts'][0]['iv_state'], '低于HV（便宜）')
        self.assertEqual(rich['contracts'][0]['iv_state'], '已透支')  # 溢价(35-24)/24≈45.8%
        self.assertGreater(cheap['engine']['iv_state']['score'], rich['engine']['iv_state']['score'])

    def test_engine_weights_and_missing_normalization(self):
        result = scan_one(strong_record('long'), 'long', [tb_row('x', 0.20, 0.012, 12)])
        tb = result['tenbagger']
        self.assertEqual(sum(item['max'] for item in tb['engine'].values()), 80)
        # 强记录无现货/基差字段 → 基本面模块部分缺失，按6分归一而不是整模块归零。
        self.assertTrue(tb['engine']['fundamentals']['missing'])
        self.assertEqual(tb['engine']['fundamentals']['avail'], 6)
        self.assertIsNotNone(tb['score'])
        self.assertIn(tb['label'], ['高', '中', '低'])

    def test_put_side_and_empty_pool(self):
        put = tb_row('put', -0.18, 0.011, 10, side='P')
        result = scan_one(strong_record('short'), 'short', [put])
        tb = result['tenbagger']
        self.assertEqual(tb['side'], 'Put')
        self.assertEqual(tb['best'], put['ts_code'])
        # 全是远月（>30天）→ 无10倍候选池，分数仍可计算但合约为空。
        far = scan_one(strong_record('long'), 'long', [tb_row('far', 0.20, 0.012, 45)])['tenbagger']
        self.assertEqual(far['contracts'], [])
        self.assertIsNone(far['best'])


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.chain = [option_row(strike, side) for side in ['C', 'P'] for strike in range(88, 113, 2)]

    def test_strong_long_scores_and_signals(self):
        result = scan_one(strong_record('long'), 'long', self.chain)
        # 库存缺失：可用权重 90；其余九项几乎满分，指数应明显高于70。
        self.assertGreater(result['explosion_score'], 70)
        self.assertEqual(result['items']['inventory']['status'], 'missing')
        self.assertEqual(result['signals_applicable'], 9)
        self.assertEqual(result['signals_met'], 9)
        self.assertAlmostEqual(result['metrics']['rps_accel'], 14.0)

    def test_contract_tiers_respect_delta_bands(self):
        picks, reference = pick_contracts(self.chain, 'long')
        tiers = {pick['tier']: pick for pick in picks}
        main, lotto = tiers['主仓 |Delta| 0.20–0.55'], tiers['彩票仓 |Delta| 0.08–0.20']
        self.assertTrue(0.20 <= main['delta'] <= 0.55)
        self.assertTrue(0.08 <= lotto['delta'] < 0.20)
        self.assertNotEqual(main['ts_code'], lotto['ts_code'])
        self.assertTrue(all(20 <= pick['days_to_expiry'] <= 60 for pick in picks))

    def test_short_direction_uses_puts(self):
        picks, reference = pick_contracts(self.chain, 'short')
        self.assertTrue(picks)
        self.assertTrue(all(pick['call_put'] == 'P' for pick in picks))
        self.assertTrue(all(pick['delta'] < 0 for pick in picks))
        result = scan_one(strong_record('short'), 'short', self.chain)
        self.assertEqual(result['signals_met'], 9)

    def test_far_dte_91_to_120_falls_back_with_note(self):
        # 主力期权挂在远月（如甲醇91天、橡胶105天）时，放宽到7–120天档仍应选出并标注。
        chain = [option_row(strike, side, dte=95) for side in ['C', 'P'] for strike in range(100, 117, 2)]
        picks, reference = pick_contracts(chain, 'long')
        self.assertTrue(picks)
        self.assertTrue(all(7 <= pick['days_to_expiry'] <= 120 for pick in picks))
        self.assertTrue(any('120' in pick['note'] for pick in picks))
        self.assertIsNotNone(reference)

    def test_dte_below_7_or_above_120_excluded(self):
        near = [option_row(strike, 'C', dte=5) for strike in range(100, 112, 2)]
        far = [option_row(strike, 'C', dte=121) for strike in range(100, 112, 2)]
        self.assertEqual(pick_contracts(near, 'long')[0], [])
        self.assertEqual(pick_contracts(far, 'long')[0], [])

    def test_preferred_band_wins_over_outer_band(self):
        # 20–60天与91–120天合约同时存在时，优先档命中且不带放宽标注。
        chain = [option_row(strike, side, dte=40) for side in ['C', 'P'] for strike in range(100, 113, 2)]
        chain += [option_row(strike, side, dte=95) for side in ['C', 'P'] for strike in range(100, 113, 2)]
        picks, _ = pick_contracts(chain, 'long')
        self.assertTrue(picks)
        self.assertTrue(all(pick['days_to_expiry'] <= 60 and not pick['note'] for pick in picks))

    def test_missing_chain_redistributes_weight(self):
        result = scan_one(strong_record('long'), 'long', [])
        self.assertIsNone(result['metrics']['iv'])
        self.assertEqual(result['items']['iv']['status'], 'missing')
        self.assertEqual(result['items']['liquidity']['status'], 'missing')
        self.assertEqual(result['contracts'], [])
        self.assertEqual(result['signals']['iv_not_hot'], None)
        self.assertEqual(result['signals_applicable'], 7)
        self.assertGreater(result['explosion_score'], 70)

    def test_weak_record_scores_below_strong(self):
        strong = scan_one(strong_record('long'), 'long', self.chain)
        weak = scan_one(weak_record('long'), 'long', self.chain)
        self.assertLess(weak['explosion_score'], strong['explosion_score'])
        self.assertLess(weak['signals_met'], strong['signals_met'])

    def test_build_scanner_ranks_and_limits(self):
        payload = dict(asof='20260911', records=[strong_record('long'), weak_record('long'), strong_record('short'), weak_record('short')])
        options = dict(records=self.chain)
        report = build_scanner(payload, options, top=1)
        self.assertEqual(report['asof'], '20260911')
        self.assertEqual(len(report['long']), 1)
        self.assertEqual(report['long'][0]['ts_code'], 'JM.DCE')
        self.assertEqual(report['short'][0]['ts_code'], 'JM.DCE')
        self.assertIn('weights', report)
        self.assertTrue(report['notes'])

    def test_symbols_without_option_chain_sink_below_tradeable(self):
        strong = strong_record('long')  # 高分但不给期权链
        weak = weak_record('long')
        weak.update(ts_code='B.DCE', name='豆二', main_code='B2609.DCE')
        chain = [dict(row, main_code='B.DCE') for row in self.chain]
        payload = dict(asof='20260911', records=[strong, weak])
        report = build_scanner(payload, dict(records=chain), top=5)
        self.assertEqual([r['ts_code'] for r in report['long']], ['B.DCE', 'JM.DCE'])
        self.assertFalse(report['long'][1]['option_ready'])
        self.assertTrue(report['long'][0]['option_ready'])

    def test_overextended_candidates_get_dedicated_list(self):
        over_long = strong_record('long'); over_long.update(phase='过度延伸', phase_match=True, phase_age=12)
        over_short = strong_record('short'); over_short.update(phase='过度延伸', phase_match=True, phase_age=8)
        # 多头延伸的品种被按空头方向扫描：阶段不匹配，不得进入延伸观察。
        wrong = strong_record('short'); wrong.update(phase='过度延伸', trend_direction='long', phase_match=False)
        payload = dict(asof='20260911', records=[over_long, over_short, wrong])
        report = build_scanner(payload, dict(records=self.chain), top=5)
        self.assertEqual(sorted(r['direction'] for r in report['extended']), ['long', 'short'])
        self.assertTrue(all(r['phase'] == '过度延伸' and r['phase_match'] for r in report['extended']))
        long_row = next(r for r in report['extended'] if r['direction'] == 'long')
        self.assertEqual(long_row['phase_age'], 12)
        self.assertEqual(long_row['ts_code'], 'JM.DCE')
        self.assertIn('extension_note', report)
        # 主榜单不受影响：延伸品种同样参与多头主榜排名。
        self.assertTrue(report['long'])

    def test_short_rps_top_uses_directional_decile(self):
        # 空头信号①：原始RPS20=8（全市场垫底）→ 方向RPS=92 → 前10%成立；加速度取原始RPS下行幅度。
        strong = scan_one(strong_record('short'), 'short', self.chain)
        self.assertTrue(strong['signals']['rps_top'])
        self.assertEqual(strong['metrics']['rps20'], 92.0)
        self.assertEqual(strong['metrics']['rps_accel'], 14.0)
        # 方向RPS20=85（原始RPS≈15）→ 信号①不成立：后10%门槛不放宽。
        weak = strong_record('short'); weak.update(directional_rps20=85.0)
        self.assertIs(scan_one(weak, 'short', self.chain)['signals']['rps_top'], False)
        # 玉米式情形：空头爆发/共振很强，但原始RPS20=22.4（后22%而非后10%）→ 信号①仍不成立。
        corn = strong_record('short')
        corn.update(ts_code='C.DCE', name='玉米', directional_rps20=77.61, rps20=22.39, rps20_prev5=33.0)
        corn_scan = scan_one(corn, 'short', self.chain)
        self.assertIs(corn_scan['signals']['rps_top'], False)
        self.assertEqual(corn_scan['metrics']['rps20'], 77.61)
        # 边界：原始RPS20恰好10.0成立，10.01不成立。
        edge = strong_record('short')
        edge.update(directional_rps20=90.0, rps20=10.0, rps20_prev5=20.0)
        self.assertIs(scan_one(edge, 'short', self.chain)['signals']['rps_top'], True)
        edge.update(directional_rps20=89.99, rps20=10.01)
        self.assertIs(scan_one(edge, 'short', self.chain)['signals']['rps_top'], False)

    def test_reversal_radar_flags_weakening_diffusion_and_covering(self):
        # 碳酸锂式衰退：RPS20从92掉到74（-18），衰退排列且RPS120仍高 → 强势衰退+衰退排列两条警报。
        decaying = strong_record('long')
        decaying.update(rps20=74.0, rps20_prev5=92.0, rps60=87.0, rps60_prev5=90.0, rps120=95.0, rps120_prev5=94.0,
            return5=0.4, oi_change5=2.0, structure='Backwardation', structure_flip5=True)
        # New Bull扩散：RPS20>60>120 且三周期同步上升。
        new_bull = strong_record('long')
        new_bull.update(ts_code='LC.GFE', name='碳酸锂', rps20=93.0, rps20_prev5=71.0, rps60=67.0, rps60_prev5=60.0,
            rps120=31.0, rps120_prev5=28.0, return5=4.0, oi_change5=15.0)
        # 价涨仓减·下跌趋势中：5日价升1.5%而OI减2% → 回补反弹（空头平仓，勿追多）。
        covering = strong_record('short')
        covering.update(ts_code='SA.CZCE', name='纯碱', rps20=50.0, rps20_prev5=48.0, rps60=52.0, rps60_prev5=51.0,
            rps120=48.0, rps120_prev5=47.0, return5=1.5, oi_change5=-2.0)
        # 价涨仓减·多头趋势中（甲醇式：RPS97强多头+Back强化却减仓）→ 减仓上行，不得再标"回补反弹"。
        long_covering = strong_record('long')
        long_covering.update(ts_code='MA.ZCE', name='甲醇', trend_direction='long',
            rps20=97.0, rps20_prev5=94.0, rps60=88.0, rps60_prev5=90.0, rps120=86.0, rps120_prev5=87.0,
            return5=1.57, oi_change5=-5.4)
        # 价涨仓减·无趋势背景：中性定性。
        neutral_covering = strong_record('long')
        neutral_covering.update(ts_code='XX.DCE', name='中性品种', trend_direction='neutral',
            rps20=50.0, rps20_prev5=49.0, rps60=51.0, rps60_prev5=50.0, rps120=49.0, rps120_prev5=48.0,
            return5=1.2, oi_change5=-1.5)
        payload = dict(asof='20260911', records=[decaying, strong_record('short'), new_bull, covering, long_covering, neutral_covering])
        report = build_scanner(payload, dict(records=self.chain), top=5)
        self.assertTrue(report['radar_note'])
        radar = {r['ts_code']: r for r in report['radar']}
        self.assertEqual(len(report['radar']), 5)  # JM多空两行按品种去重
        decay = radar['JM.DCE']
        self.assertEqual(decay['state'], '强势衰退')
        self.assertEqual(decay['rps_slope5'], -18.0)
        self.assertEqual(decay['alert_count'], 2)  # 强势衰退 + 衰退排列
        bull = radar['LC.GFE']
        self.assertEqual(bull['state'], '扩散翻多')
        self.assertEqual(bull['ladder'], 'RPS20>60>120')
        self.assertEqual(bull['diffusion'], 'up')
        cov = radar['SA.CZCE']
        self.assertEqual(cov['state'], '回补反弹')
        self.assertIn('空头平仓', '；'.join(cov['alerts']))
        # 甲醇式：强多头中的价涨仓减=减仓上行，警报与状态都不得出现"回补反弹"。
        ma = radar['MA.ZCE']
        self.assertEqual(ma['state'], '减仓上行')
        self.assertIn('减仓上行', '；'.join(ma['alerts']))
        self.assertNotIn('回补反弹', '；'.join(ma['alerts']))
        # 无趋势背景：中性定性。
        self.assertEqual(radar['XX.DCE']['state'], '价涨仓减')
        self.assertEqual(report['radar'][0]['ts_code'], 'JM.DCE')  # 警报最多者排最前
        # 只有衰退排列（非警报级衰退、无同步扩散）→ 状态=衰退排列。
        ladder_only = strong_record('long')
        ladder_only.update(rps20=61.0, rps20_prev5=63.0, rps60=87.0, rps60_prev5=86.0, rps120=95.0, rps120_prev5=94.0)
        self.assertEqual(radar_row(ladder_only)['state'], '衰退排列')

    def test_scan_one_passes_phase_context(self):
        record = strong_record('long'); record.update(phase='过度延伸', phase_match=True,
            phase_age=9, phase_reason='方向已确认，偏离MA20 3.41 ATR', phase_extension_atr=3.41)
        result = scan_one(record, 'long', self.chain)
        self.assertEqual(result['phase'], '过度延伸')
        self.assertTrue(result['phase_match'])
        self.assertEqual(result['phase_age'], 9)
        self.assertEqual(result['phase_extension_atr'], 3.41)
        self.assertIn('ATR', result['phase_reason'])


class TradabilityTests(unittest.TestCase):
    def _payload(self, record):
        return {'asof': '20260918', 'records': [record]}

    def _annotated(self, rows, record=None):
        payload = {'asof': '20260918', 'records': [] if record is None else [record]}
        option_payload = {'records': rows}
        annotate_options(payload, option_payload)
        return {r['ts_code']: r['tradability'] for r in rows}

    def test_aligned_atm_scores_high_and_carries_context(self):
        chain = [option_row(100, 'C', dte=5), option_row(100, 'P', dte=5)]
        scores = self._annotated(chain, strong_record('long'))
        call = scores[chain[0]['ts_code']]
        self.assertGreaterEqual(call['score'], 65)
        self.assertIn(call['grade'], ['优', '良'])
        self.assertEqual(call['trend_direction'], 'long')
        self.assertEqual(call['phase'], '趋势启动')
        self.assertIsNotNone(call['explosion'])
        self.assertIn('Gamma甜区', call['tags'])
        self.assertIn('末日轮', call['tags'])
        self.assertNotIn('逆趋势', call['tags'])

    def test_counter_trend_capped_and_aligned_wins(self):
        chain = [option_row(100, 'C', dte=5), option_row(100, 'P', dte=5)]
        scores = self._annotated(chain, strong_record('long'))
        call, put = scores[chain[0]['ts_code']], scores[chain[1]['ts_code']]
        # 顺势 Call：方向对齐，可进良/优。
        self.assertTrue(call['aligned'])
        self.assertFalse(call['counter_trend'])
        # 逆趋势 Put：贴标签、发动机半折、硬封顶55，永不进良/优。
        self.assertIn('逆趋势', put['tags'])
        self.assertFalse(put['aligned'])
        self.assertTrue(put['counter_trend'])
        self.assertLessEqual(put['score'], 55)
        self.assertIn(put['grade'], ['可关注', '弱'])
        self.assertGreater(call['score'], put['score'])

    def test_neutral_trend_not_counter_aligned_none(self):
        record = strong_record('long')
        record['trend_direction'] = 'neutral'
        chain = [option_row(100, 'C', dte=12), option_row(100, 'P', dte=12)]
        scores = self._annotated(chain, record)
        for row in chain:
            tb = scores[row['ts_code']]
            self.assertIsNone(tb['aligned'])
            self.assertNotIn('逆趋势', tb['tags'])
            self.assertFalse(tb['counter_trend'])

    def test_deep_otm_delta_below_ten_tagged(self):
        otm = option_row(120, 'C', dte=5)  # 深虚值，|Delta| 远低于 0.10
        scores = self._annotated([otm], strong_record('long'))
        tb = scores[otm['ts_code']]
        self.assertIn('深虚值', tb['tags'])
        self.assertEqual(tb['breakdown']['delta'], 0)

    def test_iv_overpriced_gets_zero_and_tag(self):
        rich = tb_row('rich', 0.30, 0.02, 12, iv=40.0, hv20=20.0)
        scores = self._annotated([rich], strong_record('long'))
        tb = scores[rich['ts_code']]
        self.assertIn('IV透支', tb['tags'])
        self.assertEqual(tb['breakdown']['iv'], 0)
        self.assertGreater(tb['iv_premium_pct'], 30)

    def test_iv_cheap_gets_full_iv_points(self):
        cheap = tb_row('cheap', 0.30, 0.02, 12, iv=18.0, hv20=24.0)
        scores = self._annotated([cheap], strong_record('long'))
        tb = scores[cheap['ts_code']]
        self.assertIn('IV便宜', tb['tags'])
        self.assertEqual(tb['breakdown']['iv'], 10)

    def test_theta_drag_rules(self):
        # 末日轮（DTE≤7）：DTE 档已折让，Theta 只贴警示不二次扣分。
        near = option_row(100, 'C', dte=2)
        near_tb = self._annotated([near], strong_record('long'))[near['ts_code']]
        self.assertIn('Theta损耗重', near_tb['tags'])
        self.assertIn('最后两天', near_tb['tags'])
        self.assertEqual(near_tb['breakdown']['dte'], 6)
        # 非末日轮高 Theta 损耗（日损耗10%权利金）：扣 3 分（15→12）。
        bleed = tb_row('bleed', 0.30, 0.02, 12, iv=22.0, hv20=24.0)
        bleed['premium'] = 1.0
        bleed['theta'] = -0.10
        bleed_tb = self._annotated([bleed], strong_record('long'))[bleed['ts_code']]
        self.assertIn('Theta损耗重', bleed_tb['tags'])
        self.assertEqual(bleed_tb['breakdown']['dte'], 12)

    def test_missing_greeks_returns_none_score(self):
        broken = option_row(100, 'C', dte=5)
        broken['gamma'] = None
        scores = self._annotated([broken], strong_record('long'))
        tb = scores[broken['ts_code']]
        self.assertIsNone(tb['score'])
        self.assertEqual(tb['grade'], '缺数据')

    def test_missing_underlying_record_does_not_crash(self):
        row = option_row(100, 'C', dte=5)
        scores = self._annotated([row], None)
        tb = scores[row['ts_code']]
        self.assertIn('无标的评分', tb['tags'])
        self.assertIsNotNone(tb['score'])  # 仍给出期权结构分，标的项归零
        self.assertEqual(tb['breakdown']['underlying'], 0)

    def test_score_sorts_high_to_low_in_realistic_chain(self):
        # 强多头标的上：对齐 ATM 短期 call 应排在逆趋势深虚值 put 之前。
        chain = [option_row(strike, side, dte=dte)
                 for side in ['C', 'P'] for dte in (5, 40) for strike in range(88, 113, 4)]
        scores = self._annotated(chain, strong_record('long'))
        ranked = sorted(chain, key=lambda r: scores[r['ts_code']]['score'], reverse=True)
        top = scores[ranked[0]['ts_code']]
        self.assertEqual(top['direction'], 'long')
        self.assertNotIn('逆趋势', top['tags'])
        self.assertGreaterEqual(top['score'], 65)


class StructureRadarTests(unittest.TestCase):
    def _record(self, **extra):
        base = dict(ts_code='JM.DCE', name='焦煤', sector='黑色', trend_direction='long',
            return5=2.0, oi_change5=6.0, oi_change20=10.0, spread_change5=4.0, spread=10.0,
            carry_annualized=6.0, carry_change5=2.0, structure='Backwardation', structure_flip5=False)
        base.update(extra)
        return base

    def test_oi_four_states(self):
        # Aggregate OI describes participation, not the identity of opening traders.
        cases = [(3.0, 6.0, '增仓上涨', 'long'), (3.0, -6.0, '减仓上涨', 'long'),
                 (-3.0, 6.0, '增仓下跌', 'short'), (-3.0, -6.0, '减仓下跌', 'short')]
        for ret5, oi5, state, direction in cases:
            row = structure_radar(self._record(return5=ret5, oi_change5=oi5))['oi']
            self.assertEqual(row['state'], state)
            self.assertEqual(row['direction'], direction)
        # 新多进入（强化）高于空头平仓（低质量）：8+2 对 3-2。
        new_long = structure_radar(self._record(return5=3.0, oi_change5=6.0, oi_change20=10.0))['oi']
        covering = structure_radar(self._record(return5=3.0, oi_change5=-6.0, oi_change20=-10.0))['oi']
        self.assertGreater(new_long['long'], covering['long'])

    def test_bullish_structure_scores_long_higher(self):
        # 多结构：价涨仓增 + 现货基差双强 + 月差转紧 + Back扩大。
        bull = structure_radar(self._record(spot_change5=2.0, basis_change5=30.0, carry_change5=2.0))
        self.assertGreater(bull['long_score'], bull['short_score'])
        self.assertTrue(bull['long_bias'])
        self.assertEqual(bull['dominant'], 'long')
        # 空结构：镜像。
        bear = structure_radar(self._record(trend_direction='short', return5=-2.0, oi_change5=6.0, oi_change20=10.0,
            spot_change5=-2.0, basis_change5=-30.0, spread_change5=-4.0, spread=-10.0,
            carry_annualized=-6.0, carry_change5=-2.0, structure='Contango'))
        self.assertGreater(bear['short_score'], bear['long_score'])
        self.assertTrue(bear['short_bias'])

    def test_divergence_when_structure_opposes_price_trend(self):
        # 价格仍空头但结构偏多且分≥55 → 多头酝酿。
        record = self._record(trend_direction='short', return5=-3.0, oi_change5=6.0,
            spot_change5=2.0, basis_change5=30.0, spread_change5=4.0, spread=10.0,
            carry_annualized=6.0, carry_change5=2.0)
        row = structure_radar(record)
        self.assertEqual(row['dominant'], 'long')
        self.assertEqual(row['divergence'], '多头酝酿')
        self.assertEqual(row['quality'], '弱')  # 与趋势一致的空头结构分很低
        # 结构方向与价格趋势一致 → 无背离，给结构质量。
        aligned = structure_radar(self._record(trend_direction='long'))
        self.assertIsNone(aligned['divergence'])
        self.assertIn(aligned['quality'], ['强', '中', '弱'])

    def test_missing_dimensions_normalized(self):
        # 无现货/基差、无库存：可用维度只剩 OI/月差/期限结构，仍可计算且 coverage 正确。
        record = self._record(spot_change5=None, basis_change5=None)
        row = structure_radar(record)
        self.assertEqual(row['coverage'], 3)
        self.assertEqual(row['basis']['status'], 'missing')
        self.assertEqual(row['inventory']['status'], 'missing')
        self.assertIsNone(row['basis']['long'])
        self.assertIsNotNone(row['long_score'])
        # 完全无结构数据 → 分数为 None、无占优方向。
        empty = structure_radar(dict(ts_code='XX.DCE', trend_direction='long'))
        self.assertEqual(empty['coverage'], 0)
        self.assertIsNone(empty['long_score'])
        self.assertIsNone(empty['dominant'])
        self.assertIsNone(empty['divergence'])

    def test_basis_and_spread_directions(self):
        contango_loosening = structure_radar(self._record(trend_direction='short', spread_change5=-4.0,
            spread=-10.0, carry_annualized=-6.0, structure='Contango', return5=-2.0, oi_change5=5.0))
        self.assertEqual(contango_loosening['spread']['state'], '近月相对走弱')
        self.assertEqual(contango_loosening['term']['direction'], 'short')
        basis_weak = structure_radar(self._record(trend_direction='short',
            spot_change5=-1.0, basis_change5=-20.0))['basis']
        self.assertEqual(basis_weak['state'], '现货弱·基差走弱')
        self.assertEqual(basis_weak['short'], 10)

    def test_scan_one_carries_structure_fields(self):
        record = strong_record('long')
        record.update(spot_change5=2.0, basis_change5=30.0)
        chain = [option_row(100, 'C', dte=20)]
        scanned = scan_one(record, 'long', chain)
        self.assertIn('structure', scanned)
        self.assertEqual(scanned['structure_score'], scanned['structure']['long_score'])
        self.assertEqual(scanned['structure_quality'], scanned['structure']['quality'])

    def test_build_scanner_includes_structure_list(self):
        payload = dict(asof='20260918', records=[strong_record('long'), weak_record('short')])
        result = build_scanner(payload, {'records': []})
        self.assertIn('structure', result)
        self.assertEqual(result['structure'][0]['ts_code'], 'JM.DCE')
        self.assertIn('structure_note', result)


class OpportunityTests(unittest.TestCase):
    def _report(self, rows, records, floor=50.0):
        payload = {'asof': '20260918', 'records': records}
        option_payload = {'records': rows, 'status': '已采集'}
        annotate_options(payload, option_payload)
        return build_opportunities(payload, option_payload, floor=floor)

    def test_group_meta_counts_trim_and_sort(self):
        chain = [option_row(100, 'C', dte=5), option_row(100, 'P', dte=5)]
        report = self._report(chain, [strong_record('long')])
        self.assertEqual(len(report['groups']), 1)
        group = report['groups'][0]
        self.assertEqual(group['main_code'], 'JM.DCE')
        self.assertEqual(group['name'], '焦煤')
        self.assertEqual(group['sector'], '黑色')
        self.assertEqual(group['trend_direction'], 'long')
        self.assertEqual(group['count'], 2)
        self.assertEqual(group['call_count'], 1)
        self.assertEqual(group['put_count'], 1)
        # 逆趋势 Put 封顶55但仍保留在下发数据中（前端默认隐藏、可显式打开）。
        self.assertEqual(group['counter_count'], 1)
        # 组内按可做性分降序，第一名为顺势 Call。
        scores = [c['score'] for c in group['contracts']]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(group['contracts'][0]['call_put'], 'C')
        self.assertEqual(group['best_score'], scores[0])
        # 展示字段已裁剪：不带走 gamma/vega 等未展示列。
        self.assertNotIn('gamma', group['contracts'][0])
        self.assertIn('iv_premium_pct', group['contracts'][0])
        self.assertTrue(report['note'])

    def test_groups_ranked_by_best_score(self):
        jm = [option_row(100, 'C', dte=5)]
        b_row = strong_record('long')
        b_row.update(ts_code='B.DCE', name='豆二', main_code='B2609.DCE')
        b_chain = [dict(option_row(100, 'C', dte=40), ts_code='B2609-C-100.DCE',
            underlying_code='B2609.DCE', main_code='B.DCE')]
        report = self._report(jm + b_chain, [strong_record('long'), b_row])
        codes = [g['main_code'] for g in report['groups']]
        self.assertEqual(codes, ['JM.DCE', 'B.DCE'])
        best = [g['best_score'] for g in report['groups']]
        self.assertEqual(best, sorted(best, reverse=True))
        self.assertEqual(report['groups'][1]['name'], '豆二')

    def test_floor_filters_and_missing_score_excluded(self):
        chain = [option_row(100, 'C', dte=5)]
        records = [strong_record('long')]
        self.assertEqual(self._report(chain, records, floor=99.0)['groups'], [])
        report = self._report(chain, records, floor=0.0)
        self.assertEqual(report['groups'][0]['count'], 1)
        # 缺 Greeks 的合约评分为 None，任何 floor 下都不进组。
        broken = option_row(100, 'C', dte=5)
        broken['gamma'] = None
        self.assertEqual(self._report([broken], records, floor=0.0)['groups'], [])

    def test_uncollected_status_passthrough(self):
        option_payload = {'records': [], 'status': '尚未采集该日期期权数据'}
        report = build_opportunities({'asof': '20260918', 'records': []}, option_payload)
        self.assertEqual(report['status'], option_payload['status'])
        self.assertEqual(report['groups'], [])


if __name__ == '__main__':
    unittest.main()
