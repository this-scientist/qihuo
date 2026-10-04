import test from 'node:test';
import assert from 'node:assert/strict';
import {ema20, evaluatePriceAction, registeredStrategies} from './price-action-strategies.mjs';

test('registry exposes the first price action strategies',()=>{
 assert.deepEqual(registeredStrategies().map(item=>item.id),[
  'breakout',
  'fake_breakout',
  'ema20_pullback',
  'bar_shape',
 ]);
});

test('price action strategies emit chart-compatible signals',()=>{
 const candles=[
  ['20260901',100,105,99,104,1000],
  ['20260902',104,106,101,105,1000],
  ['20260903',105,107,102,106,1000],
  ['20260904',106,108,103,107,1000],
  ['20260905',107,109,104,108,1000],
  ['20260906',108,110,105,109,1000],
  ['20260907',109,111,106,110,1000],
  ['20260908',110,112,107,111,1000],
  ['20260909',111,113,108,112,1000],
  ['20260910',112,114,109,113,1000],
  ['20260911',113,115,110,114,1000],
  ['20260912',114,116,111,115,1000],
  ['20260913',115,117,112,116,1000],
  ['20260914',116,118,113,117,1000],
  ['20260915',117,119,114,118,1000],
  ['20260916',118,120,115,119,1000],
  ['20260917',119,121,116,120,1000],
  ['20260918',120,122,117,121,1000],
  ['20260919',121,123,118,122,1000],
  ['20260920',122,124,119,123,1000],
  ['20260921',123,125,120,124,1000],
  ['20260922',124,126,121,125,1000],
  ['20260923',125,127,122,126,1000],
  ['20260924',126,128,123,127,1000],
  ['20260925',127,129,124,128,1000],
  ['20260926',128,130,125,129,1000],
  ['20260927',129,131,126,130,1000],
  ['20260928',130,132,127,128,1000],
  ['20260929',128,135,127,134,1000],
  ['20260930',134,136,126,127,1000],
 ];
 const result=evaluatePriceAction({candles,moving:{ema20:ema20(candles)}});
 assert.ok(result.signals.some(item=>item.label==='突破'));
 assert.ok(result.signals.some(item=>item.label==='假突破'));
 assert.ok(result.signals.some(item=>item.label==='外包'));
 assert.ok(result.signals.every(item=>item.trade_date&&item.side&&Number.isFinite(item.close)));
 assert.ok(result.summary.some(item=>item.id==='breakout'&&item.count>0));
});
