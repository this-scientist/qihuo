const groupKey=row=>JSON.stringify([row.underlying_code,row.maturity_date,row.call_put]);
export function withAverageIV(records){
 const groups=new Map();
 for(const row of records){
  const key=groupKey(row),group=groups.get(key)||{sum:0,count:0};
  if(Number.isFinite(row.iv_reference)&&row.iv_reference>0){group.sum+=row.iv_reference;group.count++}
  groups.set(key,group);
 }
 return records.map(row=>{const group=groups.get(groupKey(row));return {...row,average_iv:group.count?group.sum/group.count:null,iv_sample_count:group.count}});
}
export function selectOptions(records,{minDays,maxDays,minVol,minOi,maxDistance,side,role,sort,minScore,align='aligned'}){
 if(!Number.isInteger(minDays)||!Number.isInteger(maxDays))throw Error('到期天数须为整数');
 if(minDays<0||maxDays<minDays)throw Error('到期天数区间无效');
 const hasScore=minScore!=null&&Number.isFinite(minScore);
 const selected=records.filter(row=>(side==='all'||row.call_put===side)&&(role==='all'||row.role===role)&&Number.isFinite(row.days_to_expiry)&&row.days_to_expiry>=minDays&&row.days_to_expiry<=maxDays&&Number.isFinite(row.vol)&&row.vol>=minVol&&Number.isFinite(row.oi)&&row.oi>=minOi&&Number.isFinite(row.moneyness_pct)&&Math.abs(row.moneyness_pct)<=maxDistance&&(!hasScore||(row.tradability?.score!=null&&row.tradability.score>=minScore))&&(align!=='aligned'||row.tradability?.counter_trend!==true));
 const metric=sort==='iv'?'iv_reference':sort==='oi'?'oi':'vol';
 return selected.sort((a,b)=>{
  if(sort==='trade'){
   const sa=a.tradability?.score??-1,sb=b.tradability?.score??-1;
   return sb-sa||Math.min(b.vol,b.oi)-Math.min(a.vol,a.oi)||b.vol-a.vol;
  }
  return sort==='expiry'?a.days_to_expiry-b.days_to_expiry||b.vol-a.vol:sort==='iv'?(a[metric]??Infinity)-(b[metric]??Infinity):b[metric]-a[metric];
 });
}
