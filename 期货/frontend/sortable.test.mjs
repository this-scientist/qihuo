import test from 'node:test';
import assert from 'node:assert/strict';
import {cellKey, compareKeys} from './sortable.mjs';

const cell=text=>({textContent:text,dataset:{}});
const key=text=>cellKey(cell(text));

test('cellKey parses percent, signed and comma numbers; missing markers are null',()=>{
 assert.equal(key('+5.20%').num,5.2);
 assert.equal(key('-3.76%').num,-3.76);
 assert.equal(key('1,234').num,1234);
 assert.equal(key('36').num,36);
 assert.equal(key('92.10').num,92.1);
 assert.equal(key('焦煤').num,null);
 assert.equal(key('多头 · 趋势启动').num,null);
 assert.equal(key('—'),null);
 assert.equal(key('缺失'),null);
 assert.equal(key(''),null);
});

test('missing values always sort last regardless of direction',()=>{
 assert.equal(compareKeys(key('—'),key('5'),1),1);
 assert.equal(compareKeys(key('—'),key('5'),-1),1);
 assert.equal(compareKeys(key('缺失'),key('—'),1),0);
});

test('numeric columns compare by value, text columns by locale',()=>{
 assert.ok(compareKeys(key('9'),key('10'),1)<0);
 assert.ok(compareKeys(key('9'),key('10'),-1)>0);
 assert.ok(compareKeys(key('+2.00%'),key('-1.00%'),1)>0);
 assert.ok(compareKeys(key('-2.00%'),key('+1.00%'),1)<0);
 const text=compareKeys(key('焦煤'),key('纯碱'),1);
 assert.notEqual(text,0);
});
