import test from 'node:test';
import assert from 'node:assert/strict';
import {zoomRange, normalizePriceLevels, priceFromPointer, ema20ChartSeries, klineWheelIntent} from './charts.mjs';

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
