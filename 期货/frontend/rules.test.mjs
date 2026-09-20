import test from 'node:test';
import assert from 'node:assert/strict';
import {evaluateRules,validateConfig} from './rules.mjs';
const factors=[{key:'adx',type:'number'},{key:'ma20',type:'number'},{key:'ma60',type:'number'},{key:'flag',type:'boolean'}];
test('factor comparison and AND/OR',()=>{
 const rules=[{enabled:true,key:'adx',op:'>=',value:20},{enabled:true,key:'ma20',op:'>',rhs:'factor',factor:'ma60'}];
 assert.equal(evaluateRules({adx:25,ma20:100,ma60:110},rules,'all').matches,false);
 assert.equal(evaluateRules({adx:25,ma20:100,ma60:110},rules,'any').matches,true);
});
test('missing never becomes zero or boolean false',()=>{
 for(const rule of [{key:'adx',op:'<=',value:20},{key:'flag',op:'false'}]){
  const result=evaluateRules({adx:null,flag:null},[rule],'all');assert.equal(result.matches,false);assert.equal(result.details[0].status,'missing');
 }
});
test('disabled rules and no rules',()=>{
 assert.equal(evaluateRules({},[{key:'adx',op:'>',value:20,enabled:false}],'all').matches,true);
 assert.equal(evaluateRules({},[],'any').matches,true);
});
test('inclusive bounds and exact booleans',()=>{
 assert.equal(evaluateRules({adx:20,flag:false},[{key:'adx',op:'between',value:10,upper:20},{key:'flag',op:'false'}],'all').matches,true);
 assert.equal(evaluateRules({flag:0},[{key:'flag',op:'false'}],'all').matches,false);
});
test('invalid imports are rejected',()=>{
 const config={version:1,direction:'long',match:'all',rules:[{key:'adx',op:'between',value:30,upper:20}]};
 assert.throws(()=>validateConfig(config,factors));
 config.rules=[{key:'unknown',op:'>=',value:20}];assert.throws(()=>validateConfig(config,factors));
 config.rules=[{key:'adx',op:'>=',value:'abc'}];assert.throws(()=>validateConfig(config,factors));
 config.rules=[{key:'adx',op:'>=',value:20}];assert.doesNotThrow(()=>validateConfig(config,factors));
});
test('disabled invalid thresholds cannot block enabled rules or saved configurations',()=>{
 const config={version:1,direction:'long',match:'all',rules:[{key:'adx',op:'>=',value:NaN,enabled:false},{key:'ma20',op:'>',value:90}]};
 assert.doesNotThrow(()=>validateConfig(config,factors));
 assert.equal(evaluateRules({ma20:100},config.rules).matches,true);
 assert.doesNotThrow(()=>validateConfig(JSON.parse(JSON.stringify(config)),factors));
 config.rules[0].enabled=true;assert.throws(()=>validateConfig(config,factors));
});
