import test from 'node:test';
import assert from 'node:assert/strict';
import {buildEntryHint, buildSignalMatrix, frameLabel} from './signal-matrix.mjs';

test('signal matrix separates daily trend, price action, structure, execution, and option modules',()=>{
 const row={
  decision_side:'long',
  trend_state_label:'启动',
  market_cycle_label:'突破尖峰',
  dir_score:72,
  structure_confirm:'SUPPORT',
  structure_direction:'long',
  option_action:'Call',
 };
 const priceAction={signals:[
  {side:'long',label:'突破'},
  {side:'short',label:'假突破'},
  {side:'long',label:'回踩'},
 ]};
 const execution={exec_score:83,stance_label:'顺向边缘'};
 const matrix=buildSignalMatrix(row,{priceAction,execution});
 assert.deepEqual(matrix.map(item=>[item.id,item.stance,item.value]),[
  ['daily_trend','support','偏多 · 突破尖峰'],
  ['price_action','support','多2 / 空1'],
  ['structure','support','偏多 · 同向'],
  ['execution','support','83 · 顺向边缘'],
  ['option','support','做：买认购'],
 ]);
});

test('signal matrix marks conflicts and unavailable modules explicitly',()=>{
 const row={decision_side:'short',structure_confirm:'CONFLICT',structure_direction:'long',option_action:'不做'};
 const matrix=buildSignalMatrix(row,{priceAction:{signals:[]},execution:null});
 assert.equal(matrix.find(item=>item.id==='daily_trend').stance,'support');
 assert.equal(matrix.find(item=>item.id==='price_action').stance,'neutral');
 assert.equal(matrix.find(item=>item.id==='structure').stance,'conflict');
 assert.equal(matrix.find(item=>item.id==='execution').stance,'missing');
 assert.equal(matrix.find(item=>item.id==='option').stance,'neutral');
});

test('frame labels distinguish daily and minute signal context',()=>{
 assert.equal(frameLabel('daily'),'日线');
 assert.equal(frameLabel('5'),'5m');
 assert.equal(frameLabel(30),'30m');
});

test('minute price action unavailable is marked as missing instead of reusing daily signals',()=>{
 const matrix=buildSignalMatrix(
  {decision_side:'long'},
  {priceAction:{signals:[],unavailable:true,reason:'网络失败'}}
 );
 const priceAction=matrix.find(item=>item.id==='price_action');
 assert.equal(priceAction.stance,'missing');
 assert.equal(priceAction.value,'当前周期不可用');
 assert.match(priceAction.detail,/网络失败/);
});

test('entry hint combines daily direction with current minute signal',()=>{
 const row={decision_side:'long'};
 const support=buildEntryHint(row,{frame:'5',priceAction:{signals:[
  {side:'long',strategy:'ema20_pullback',label:'回踩',detail:'顺势回踩EMA20后收在均线上方'},
 ]}});
 assert.equal(support.stance,'support');
 assert.match(support.title,/5m 回踩确认/);

 const conflict=buildEntryHint(row,{frame:'15',priceAction:{signals:[
  {side:'short',strategy:'fake_breakout',label:'假突破'},
 ]}});
 assert.equal(conflict.stance,'conflict');
 assert.match(conflict.detail,/反向价格行为/);
});
