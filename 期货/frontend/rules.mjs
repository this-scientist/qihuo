export function evaluateRules(record,rules,match='all') {
 const active=rules.filter(rule=>rule.enabled!==false);
 const details=active.map(rule=>{
  const left=record[rule.key],right=rule.rhs==='factor'?record[rule.factor]:rule.value;
  let passed=false;
  if(left===null||left===undefined||typeof left==='number'&&!Number.isFinite(left)||
     !['true','false'].includes(rule.op)&&(right===null||right===undefined||typeof right==='number'&&!Number.isFinite(right)))
    return {rule,left,right,status:'missing'};
  switch(rule.op){
   case '>':passed=left>right;break;case '>=':passed=left>=right;break;
   case '<':passed=left<right;break;case '<=':passed=left<=right;break;
   case '=':passed=left===right;break;case '!=':passed=left!==right;break;
   case 'between':passed=left>=right&&left<=rule.upper;break;
   case 'true':passed=left===true;break;case 'false':passed=left===false;break;
  }
  return {rule,left,right,status:passed?'pass':'fail'};
 });
 return {matches:!details.length||(match==='all'?details.every(d=>d.status==='pass'):details.some(d=>d.status==='pass')),
         details,passed:details.filter(d=>d.status==='pass').length,missing:details.filter(d=>d.status==='missing').length};
}

export function validateConfig(config,factors){
 const catalog=new Map(factors.map(f=>[f.key,f]));
 if(config.version!==1||!['long','short'].includes(config.direction)||!['all','any'].includes(config.match)||!Array.isArray(config.rules)||config.rules.length>100)throw Error('配置格式、方向或匹配方式无效');
 for(const rule of config.rules){
  const factor=catalog.get(rule.key);if(!factor)throw Error('未知因子：'+rule.key);
  if(rule.enabled!==undefined&&typeof rule.enabled!=='boolean')throw Error('因子启用状态无效');
  if(rule.enabled===false)continue;
  if(factor.type==='boolean'){
   if(!['true','false'].includes(rule.op))throw Error('信号因子只能选择成立或不成立');
  }else{
   if(!['>','>=','<','<=','=','!=','between'].includes(rule.op))throw Error('比较运算无效');
   if(rule.rhs==='factor'){
    if(catalog.get(rule.factor)?.type!=='number'||rule.op==='between')throw Error('比较因子无效');
   }else if(typeof rule.value!=='number'||!Number.isFinite(rule.value))throw Error('请输入有效数值');
   if(rule.op==='between'&&(typeof rule.upper!=='number'||!Number.isFinite(rule.upper)||rule.upper<rule.value))throw Error('区间上限必须不小于下限');
  }
 }
 return config;
}
