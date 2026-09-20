// 通用表头排序：点击 thead 任意列对当前 tbody 行排序；缺失值恒排最后。
// 数值列按数值比较（自动识别 %、千分位、+/-），文本列按中文拼音比较。
export function cellKey(cell){
 const raw=String(cell?.dataset.sort??cell?.textContent??'').trim();
 if(!raw||raw==='—'||raw==='缺失')return null;
 const numeric=Number(raw.replace(/[,%\s]/g,''));
 const isNumeric=Number.isFinite(numeric)&&/^[+\-]?[\d.,]+%?$/.test(raw);
 return {text:raw,num:isNumeric?numeric:null};
}
export function compareKeys(a,b,dir){
 if(a===null&&b===null)return 0;
 if(a===null)return 1;
 if(b===null)return -1;
 const numeric=a.num!==null&&b.num!==null;
 if(numeric)return (a.num-b.num)*dir;
 return a.text.localeCompare(b.text,'zh-Hans-CN',{numeric:true})*dir;
}
export function enableTableSorting(table){
 const thead=table.querySelector('thead');
 if(!thead||thead.dataset.sortable)return;
 thead.dataset.sortable='1';
 thead.addEventListener('click',event=>{
  const th=event.target.closest('th');
  if(!th||!thead.contains(th))return;
  const tbody=table.querySelector('tbody');
  const rows=[...tbody.querySelectorAll('tr')].filter(tr=>tr.cells.length&&tr.cells.length===thead.rows[0].cells.length);
  if(rows.length<2)return;
  const index=[...th.parentElement.children].indexOf(th);
  const current=th.getAttribute('aria-sort');
  const keys=rows.map(tr=>cellKey(tr.cells[index]));
  const numericColumn=keys.filter(k=>k!==null).every(k=>k.num!==null);
  const dir=current==='ascending'?-1:current==='descending'?1:(numericColumn?-1:1);
  const order=keys.map((key,pos)=>pos).sort((x,y)=>compareKeys(keys[x],keys[y],dir)||x-y);
  order.forEach(pos=>tbody.appendChild(rows[pos]));
  [...thead.rows[0].children].forEach(cell=>cell.removeAttribute('aria-sort'));
  th.setAttribute('aria-sort',dir===1?'ascending':'descending');
 });
}
