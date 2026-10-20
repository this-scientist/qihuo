import test from 'node:test';
import assert from 'node:assert/strict';
import {buildPullbackLists} from './ema-pullback.mjs';
const bars=(sign=1)=>Array.from({length:100},(_,i)=>['20260101',200+sign*i,202+sign*i,198+sign*i,200+sign*i]);
test('classifies independent of decision side and sorts nearest first',()=>{
 const a=bars(),b=bars();a[99]=['20261020',290,292,287,290];
 const result=buildPullbackLists({records:[{code:'a'},{code:'b'},{code:'s'}],candles:{a,b,s:bars(-1)}});
 assert.deepEqual(result.long.map(x=>x.code),['a','b']);assert.equal(result.short[0].code,'s');
 assert.equal(result.long[0].status,'触线后收回');
 assert.ok(result.long[0].distanceAtr>0);
});
test('excludes missing, invalid and insufficient histories',()=>{
 const bad=bars();bad[90][4]=null;
 const result=buildPullbackLists({records:[{code:'a'},{code:'b'},{code:'c'}],candles:{a:bars().slice(0,30),b:bad}});
 assert.equal(result.excluded,3);assert.equal(result.long.length,0);
});
test('keeps a trend after price crosses to the wrong side',()=>{
 const a=bars();a[99]=['20261020',280,282,275,277];
 const result=buildPullbackLists({records:[{code:'a'}],candles:{a}});
 assert.equal(result.long[0].status,'穿线待观察');assert.ok(result.long[0].distanceAtr<0);
});
