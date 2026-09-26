import test from 'node:test';
import assert from 'node:assert/strict';

import {holdingExplanation, renderHoldings} from './holdings.mjs';


const complete = {
  holding_status: 'available',
  holding_reason: null,
  holding_contract: 'M2701.DCE',
  holding_trade_date: '20260924',
  top20_long: 52000,
  top20_short: 50800,
  top20_net: 1200,
  top20_long_change: 100,
  top20_short_change: 400,
  top20_net_change: -300,
  top20_long_concentration: .52,
  top20_short_concentration: .508,
  top_long_brokers: [{broker: '甲期货', holding: 6000, change: 200}],
  top_short_brokers: [{broker: '乙期货', holding: 5800, change: -50}],
};


test('explains published top-20 net position without turning it into advice', () => {
  const text = holdingExplanation(complete);
  assert.match(text, /前20席位净多/);
  assert.match(text, /净多减少/);
  assert.doesNotMatch(text, /建议|做多|做空|确认趋势/);
});


test('renders summary, concentration, broker leaders and the fixed scope note', () => {
  const html = renderHoldings(complete);
  assert.match(html, /M2701\.DCE/);
  assert.match(html, /52,000/);
  assert.match(html, /多仓集中度/);
  assert.match(html, /52\.00%/);
  assert.match(html, /甲期货/);
  assert.match(html, /乙期货/);
  assert.match(html, /全市场多空总量相等/);
  assert.match(html, /不参与系统评分/);
});


test('numeric-only status keeps totals but hides all broker names', () => {
  const value = {...complete, holding_status: 'numeric_only',
    holding_reason: '席位名称源数据异常',
    top_long_brokers: [{broker: '损坏席位', holding: 6000, change: 200}],
    top_short_brokers: [{broker: '损坏席位', holding: 5800, change: -50}]};
  const html = renderHoldings(value);
  assert.match(html, /52,000/);
  assert.match(html, /席位名称源数据异常/);
  assert.doesNotMatch(html, /损坏席位/);
  assert.doesNotMatch(html, /多头前五|空头前五/);
});


test('unavailable and invalid statuses show reasons without invented zeros', () => {
  const unavailable = renderHoldings({holding_status: 'unavailable',
    holding_reason: '交易所未发布'});
  const invalid = renderHoldings({holding_status: 'invalid',
    holding_reason: '席位集中度超出合理范围'});
  assert.match(unavailable, /交易所未发布/);
  assert.match(invalid, /席位集中度超出合理范围/);
  assert.doesNotMatch(unavailable, />0(?:\.00)?</);
  assert.doesNotMatch(invalid, />0(?:\.00)?</);
});


test('escapes broker names and status reasons before inserting HTML', () => {
  const html = renderHoldings({...complete,
    top_long_brokers: [{broker: '<script>alert(1)</script>', holding: 6000, change: 200}]});
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  const missing = renderHoldings({holding_status: 'invalid', holding_reason: '<img src=x>'});
  assert.doesNotMatch(missing, /<img/);
  assert.match(missing, /&lt;img src=x&gt;/);
});
