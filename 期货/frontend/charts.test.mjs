import test from 'node:test';
import assert from 'node:assert/strict';
import {zoomRange, normalizePriceLevels, priceFromPointer, ema20ChartSeries, klineWheelIntent, ema20GapRuns} from './charts.mjs';

test('chart accepts only the EMA20 overlay',()=>{
 assert.deepEqual(ema20ChartSeries({ema20:[1,2],ma60:[3,4]}),[{id:'ema20',label:'EMA20',values:[1,2]}]);
 assert.deepEqual(ema20ChartSeries({ma20:[1,2]}),[]);
});

test('chart rebuilds EMA20 from candles when a legacy payload has no EMA20',()=>{
 const candles=[
  ['20260901',10,11,9,10,100,200],
  ['20260902',20,21,19,20,100,200],
  ['20260903',30,31,29,30,100,200],
 ];
 const series=ema20ChartSeries({ma20:[11,12,13],ma60:[9,10,11]},candles);
 assert.equal(series.length,1);
 assert.equal(series[0].id,'ema20');
 assert.deepEqual(series[0].values.map(value=>Number(value.toFixed(6))),[10,10.952381,12.76644]);
});

test('zoomRange zooms around the pointer anchor and keeps the newest bar in range',()=>{
 const zoomed=zoomRange({start:40,count:60,total:120},30,.5);
 assert.deepEqual(zoomed,{start:55,count:30});
 const atRight=zoomRange({start:60,count:60,total:120},59,.5);
 assert.deepEqual(atRight,{start:90,count:30});
});

test('zoomRange clamps minimum, maximum and pan boundaries',()=>{
 assert.deepEqual(zoomRange({start:0,count:20,total:120},10,.1),{start:4,count:12});
 assert.deepEqual(zoomRange({start:80,count:40,total:120},20,10),{start:0,count:120});
 assert.deepEqual(zoomRange({start:0,count:120,total:120},60,.5),{start:30,count:60});
});

test('normalizePriceLevels keeps editable support and resistance with stable ids',()=>{
 assert.deepEqual(normalizePriceLevels([
  {id:'today-support',kind:'support',label:'系统支撑',value:98.5},
  {id:'today-resistance',kind:'resistance',label:'系统压力',value:106},
  {kind:'support',value:null},
 ]),[
  {id:'today-support',kind:'support',label:'系统支撑',value:98.5,systemValue:98.5},
  {id:'today-resistance',kind:'resistance',label:'系统压力',value:106,systemValue:106},
 ]);
});

test('priceFromPointer maps dragged level to price and clamps it to the chart domain',()=>{
 assert.equal(priceFromPointer(50,{top:20,height:200,low:90,high:110}),107);
 assert.equal(priceFromPointer(-20,{top:20,height:200,low:90,high:110}),110);
 assert.equal(priceFromPointer(260,{top:20,height:200,low:90,high:110}),90);
});

test('K-line wheel navigates normally and zooms only with Control',()=>{
 assert.equal(klineWheelIntent({deltaY:40,ctrlKey:false},'navigate'),'next');
 assert.equal(klineWheelIntent({deltaY:-40,ctrlKey:false},'navigate'),'previous');
 assert.equal(klineWheelIntent({deltaY:40,ctrlKey:true},'navigate'),'zoom-out');
 assert.equal(klineWheelIntent({deltaY:-40,ctrlKey:true},'navigate'),'zoom-in');
 assert.equal(klineWheelIntent({deltaY:4,ctrlKey:false},'navigate'),'none');
 assert.equal(klineWheelIntent({deltaY:40,ctrlKey:false},'zoom'),'zoom-out');
});

test('ema20GapRuns marks same-side runs above or below EMA20 longer than 20 bars',()=>{
 const above=Array.from({length:21},(_,i)=>[`202601${String(i+1).padStart(2,'0')}`,12,13,11,12,1,1]);
 const touch=['20260201',10,10.5,9.5,10,1,1];
 const below=Array.from({length:21},(_,i)=>[`202603${String(i+1).padStart(2,'0')}`,8,9,7,8,1,1]);
 const runs=ema20GapRuns([...above,touch,...below],Array(43).fill(10));
 assert.deepEqual(runs,[
  {start:0,end:20,side:'up',count:21},
  {start:22,end:42,side:'down',count:21},
 ]);
});

test('ema20GapRuns requires more than 20 bars and breaks on touch or missing EMA',()=>{
 const aboveBar=()=>['20260101',12,13,11,12,1,1];
 assert.deepEqual(ema20GapRuns(Array.from({length:20},aboveBar),Array(20).fill(10)),[]);
 const touched=Array.from({length:21},aboveBar),touchedEma=Array(21).fill(10);
 touched[10][3]=10; // 下影线刚好触及EMA20，区间中断为两段各10根
 assert.deepEqual(ema20GapRuns(touched,touchedEma),[]);
 const broken=Array.from({length:25},aboveBar),brokenEma=Array(25).fill(10);
 brokenEma[10]=null; // EMA缺失，中断为10根与14根两段
 assert.deepEqual(ema20GapRuns(broken,brokenEma),[]);
});
