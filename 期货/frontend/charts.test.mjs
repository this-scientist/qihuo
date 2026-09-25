import test from 'node:test';
import assert from 'node:assert/strict';
import {zoomRange, normalizePriceLevels, priceFromPointer} from './charts.mjs';

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
