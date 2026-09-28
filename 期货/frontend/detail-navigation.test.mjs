import test from 'node:test';
import assert from 'node:assert/strict';
import {
  orderedDetailRows,
  adjacentDetailRow,
  wheelStep,
  ignoresDetailShortcut,
} from './detail-navigation.mjs';

const row=(ts_code,name,status,slope,extra={})=>({
  ts_code,name,main_code:`${ts_code}-MAIN`,
  ema20_actionability:status,
  ema20_slope5_atr:slope,
  ...extra,
});

test('orders by actionability then absolute EMA20 strength and name',()=>{
  const rows=[
    row('D','丁','not_actionable',2),
    row('B','乙','actionable',.4),
    row('A','甲','actionable',.9),
    row('C','丙','wait_pullback',1.2),
    row('E','戊','do_not_chase',1.5),
  ];
  assert.deepEqual(orderedDetailRows(rows).map(item=>item.ts_code),['A','B','C','E','D']);
});

test('deduplicates products and filters name, product code, or contract code',()=>{
  const rows=[row('LC.GFE','碳酸锂','actionable',.8),row('LC.GFE','重复','not_actionable',0),row('CU.SHF','铜','actionable',.5,{main_code:'CU2611.SHF'})];
  assert.deepEqual(orderedDetailRows(rows).map(item=>item.ts_code),['LC.GFE','CU.SHF']);
  assert.deepEqual(orderedDetailRows(rows,'2611').map(item=>item.ts_code),['CU.SHF']);
  assert.deepEqual(orderedDetailRows(rows,'碳酸').map(item=>item.ts_code),['LC.GFE']);
});

test('moves one item and clamps at both ends without wrapping',()=>{
  const rows=[row('A','甲','actionable',.9),row('B','乙','actionable',.5)];
  assert.equal(adjacentDetailRow(rows,'A',1).ts_code,'B');
  assert.equal(adjacentDetailRow(rows,'B',1).ts_code,'B');
  assert.equal(adjacentDetailRow(rows,'A',-1).ts_code,'A');
});

test('current row filtered out by search stays on current detail',()=>{
  const rows=[row('A','甲','actionable',.9),row('B','乙','actionable',.5)];
  assert.equal(adjacentDetailRow(rows,'Z',1),null);
  assert.equal(adjacentDetailRow([],'A',1),null);
});

test('wheel threshold produces a single direction',()=>{
  assert.equal(wheelStep(4),0);
  assert.equal(wheelStep(16),1);
  assert.equal(wheelStep(-16),-1);
});

test('shortcut guard ignores editing controls and open dialogs',()=>{
  assert.equal(ignoresDetailShortcut({tagName:'INPUT'}),true);
  assert.equal(ignoresDetailShortcut({tagName:'DIV',isContentEditable:true}),true);
  assert.equal(ignoresDetailShortcut({tagName:'DIV'},true),true);
  assert.equal(ignoresDetailShortcut({tagName:'DIV'}),false);
});
