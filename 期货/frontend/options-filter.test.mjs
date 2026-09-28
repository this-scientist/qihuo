import test from 'node:test';
import assert from 'node:assert/strict';
import {withAverageIV, selectOptions} from './options-filter.mjs';
const row=(extra={})=>({underlying_code:'M2701',maturity_date:'20261207',call_put:'C',days_to_expiry:5,iv_reference:20,vol:100,oi:500,role:'main',moneyness_pct:0,...extra});
test('IV mean groups underlying, expiry and side, excluding invalid values',()=>{
 const result=withAverageIV([row(),row({iv_reference:40}),row({iv_reference:null}),row({iv_reference:Infinity}),row({iv_reference:0}),row({call_put:'P',iv_reference:60}),row({underlying_code:'M2705',iv_reference:70}),row({maturity_date:'20270101',iv_reference:80})]);
 assert.equal(result[0].average_iv,30);assert.equal(result[0].iv_sample_count,2);
 assert.equal(result[2].average_iv,30);assert.equal(result[5].average_iv,60);
 assert.equal(withAverageIV([row({iv_reference:null})])[0].average_iv,null);
});
test('0–10 includes endpoints; mean remains independent of liquidity filters',()=>{
 const rows=withAverageIV([row({days_to_expiry:0,vol:0,iv_reference:40}),row({days_to_expiry:10}),row({days_to_expiry:11}),row({days_to_expiry:-1})]);
 const settings={minDays:0,maxDays:10,minVol:0,minOi:0,maxDistance:100,side:'all',role:'all',sort:'expiry'};
 assert.deepEqual(selectOptions(rows,settings).map(r=>r.days_to_expiry),[0,10]);
 const selected=selectOptions(rows,{...settings,minVol:1});assert.equal(selected.length,1);assert.equal(selected[0].average_iv,25);
 assert.throws(()=>selectOptions(rows,{...settings,minDays:11}),/区间/);
 assert.throws(()=>selectOptions(rows,{...settings,maxDays:1.5}),/整数/);
});
test('minScore filters by tradability; trade sort desc with liquidity tiebreak',()=>{
 const rows=withAverageIV([
  row({days_to_expiry:5,vol:3000,oi:5000,tradability:{score:82,eligible:true}}),
  row({days_to_expiry:5,vol:100,oi:500,tradability:{score:66,eligible:true}}),
  row({days_to_expiry:5,vol:2000,oi:2000,tradability:{score:40,eligible:true}}),
  row({days_to_expiry:5,vol:5000,oi:5000,tradability:{score:99,eligible:false}}),
  row({days_to_expiry:5,vol:900,oi:900,tradability:{score:null}}),
 ]);
 const settings={minDays:0,maxDays:10,minVol:0,minOi:0,maxDistance:100,side:'all',role:'all',sort:'trade'};
 assert.deepEqual(selectOptions(rows,{...settings,minScore:65}).map(r=>r.tradability.score),[82,66]);
 assert.deepEqual(selectOptions(rows,{...settings,minScore:50}).map(r=>r.tradability.score),[82,66]);
 // 同分：量仓较小值大者排前；缺分恒最后。
 const tied=withAverageIV([
  row({days_to_expiry:5,vol:100,oi:100,tradability:{score:70}}),
  row({days_to_expiry:5,vol:800,oi:800,tradability:{score:70}}),
  row({days_to_expiry:5,vol:50,oi:50,tradability:{score:null}}),
 ]);
 assert.deepEqual(selectOptions(tied,settings).map(r=>r.vol),[800,100,50]);
});
test('score filter never admits an ineligible contract even with a high raw score',()=>{
 const settings={minDays:0,maxDays:60,minVol:0,minOi:0,maxDistance:100,side:'all',role:'all',sort:'trade',minScore:0};
 const rows=withAverageIV([
  row({tradability:{score:70,eligible:true}}),
  row({tradability:{score:99,raw_score:99,eligible:false,block_reasons:['成交量不足']}}),
 ]);
 assert.deepEqual(selectOptions(rows,settings).map(r=>r.tradability.score),[70]);
});
test('underlying filter selects one contract and overrides role filter',()=>{
 const rows=withAverageIV([row({underlying_code:'M2701',role:'main'}),row({underlying_code:'M2705',role:'secondary',vol:200})]);
 const base={minDays:0,maxDays:10,minVol:0,minOi:0,maxDistance:100,side:'all',role:'all',sort:'vol'};
 assert.deepEqual(selectOptions(rows,{...base,underlying:'M2705'}).map(r=>r.underlying_code),['M2705']);
 assert.equal(selectOptions(rows,{...base,underlying:'all'}).length,2);
 // 指定合约时忽略 role，避免“选了主力合约却被次主力身份过滤”的空结果。
 assert.equal(selectOptions(rows,{...base,underlying:'M2701',role:'secondary'}).length,1);
});
test('aligned mode hides counter-trend rows; neutral and missing stay',()=>{
 const rows=withAverageIV([
  row({tradability:{score:70,counter_trend:true}}),     // 逆趋势：默认隐藏
  row({tradability:{score:68,counter_trend:false}}),    // 顺势：保留
  row({tradability:{score:60,counter_trend:false}}),    // 中性标的：保留
  row({tradability:{score:null}}),                      // 缺数据：不拦
 ]);
 const base={minDays:0,maxDays:10,minVol:0,minOi:0,maxDistance:100,side:'all',role:'all',sort:'trade',minScore:null};
 assert.equal(selectOptions(rows,{...base,align:'aligned'}).length,3);
 assert.equal(selectOptions(rows,{...base,align:'all'}).length,4);
 // 与最低分叠加：逆趋势即使分数≥65也被隐藏。
 const rich=withAverageIV([row({tradability:{score:74,eligible:false,counter_trend:true}}),row({tradability:{score:70,eligible:true,counter_trend:false}})]);
 assert.deepEqual(selectOptions(rich,{...base,align:'aligned',minScore:65}).map(r=>r.tradability.score),[70]);
});
