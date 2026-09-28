// 商品详情工作台的纯导航模型：排序、搜索过滤、首尾停止的边界导航、滚轮步长与快捷键守卫。
// 本模块不接触 DOM，所有函数均可在 Node 下单测。
const ACTION_RANK={actionable:0,wait_pullback:1,do_not_chase:2,not_actionable:3};
const text=value=>String(value??'').toLocaleLowerCase('zh-CN');

export function orderedDetailRows(records=[],query=''){
  const seen=new Set(),needle=text(query).trim();
  return records.filter(row=>{
    if(!row?.ts_code||seen.has(row.ts_code))return false;
    seen.add(row.ts_code);
    return !needle||text(`${row.name} ${row.ts_code} ${row.main_code}`).includes(needle);
  }).sort((a,b)=>
    (ACTION_RANK[a.ema20_actionability]??9)-(ACTION_RANK[b.ema20_actionability]??9)||
    Math.abs(Number(b.ema20_slope5_atr)||0)-Math.abs(Number(a.ema20_slope5_atr)||0)||
    String(a.name??a.ts_code).localeCompare(String(b.name??b.ts_code),'zh-CN')
  );
}

export function adjacentDetailRow(records,currentCode,step){
  if(!records.length)return null;
  const index=records.findIndex(row=>row.ts_code===currentCode);
  // 当前商品被搜索过滤时保持当前详情，不偷偷跳到过滤结果。
  if(index<0)return null;
  const next=Math.max(0,Math.min(records.length-1,index+Math.sign(step)));
  return records[next];
}

export const wheelStep=(deltaY,threshold=8)=>Math.abs(deltaY)<threshold?0:deltaY>0?1:-1;

export function ignoresDetailShortcut(target,dialogOpen=false){
  const tag=String(target?.tagName||'').toUpperCase();
  return dialogOpen||Boolean(target?.isContentEditable)||['INPUT','TEXTAREA','SELECT','BUTTON'].includes(tag);
}
