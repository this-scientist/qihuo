import {api,asofQuery,mountToolbar} from './common.mjs';
import {enableTableSorting} from './sortable.mjs';
const $=id=>document.getElementById(id);
let data,scanner,direction='long',detailCode=null;
const fmt=value=>value==null?'—':Number(value).toFixed(2);
const signed=value=>value==null?'—':`${value>=0?'+':''}${Number(value).toFixed(2)}`;
const signedClass=(value,invert=false)=>value==null?'':Number(value)>0?(!invert?'up':'down'):(Number(value)<0?(!invert?'down':'up'):'');
const ITEM_LABELS={rps_strength:'RPS强度',rps_accel:'RPS加速度',adx_accel:'ADX加速度',breakout:'突破强度',oi:'OI变化',volume:'成交量',inventory:'库存/基差',term:'期限结构Carry',liquidity:'期权流动性'};
const SIGNAL_LABELS=(direction,m={})=>{
 const rawRps20=direction==='short'?(m.rps20==null?null:100-m.rps20):m.rps20;
 const cur=v=>v==null?'（当前值缺失）':`（当前 ${Number(v).toFixed(1)}）`;
 return {rps_top:direction==='short'?`① RPS排全市场后10%（原始RPS20≤10）${cur(rawRps20)}`:`① RPS排全市场前10%（方向RPS20≥90）${cur(m.rps20)}`,
 rps_rise:direction==='short'?`② RPS加速走弱：五日下降≥10${cur(m.rps_accel)}`:`② RPS五日上升≥10${cur(m.rps_accel)}`,
 adx_turn:direction==='short'?'③ ADX拐头增强且−DI占优':'③ ADX拐头向上且DI同向',
 breakout:direction==='short'?'④ 跌破20/55日平台':'④ 突破20/55日平台',
 oi_up:'⑤ OI五日增加',volume_up:'⑥ 温和放量（量比≥1.2）',inventory:'⑦ 现货/基差同向支持',
 term:direction==='short'?'⑧ 期限结构同向强化（Contango同向且五日未反转）':'⑧ 期限结构同向强化（Backwardation同向且五日未反转）',
 iv_not_hot:'⑨ IV未过热（≤HV1.3倍且≤60）',liquidity_ok:'⑩ 期权流动性（量仓≥1000）'}};
const pct=value=>value==null?'—':`${value>=0?'+':''}${Number(value).toFixed(2)}%`;
const GLOSSARY={
 '爆发指数':'0–100综合分：RPS、ADX、突破、持仓、成交、期限结构、IV、期权流动性十项加权（缺失项归一）。分数越高=趋势爆发条件越齐。',
 '组合信号':'十条多空条件成立的条数，分母只计有数据的条件；8条以上才值得重仓研究，★=四重共振同时成立。',
 '方向RPS20':'该品种近20日涨跌幅在全市场的百分位名次（做空已翻转为100−原始值）。≥90=最强/最弱的10%，且方向与交易一致才有意义。',
 'RPS五日加速度':'RPS20比5个交易日前变化了多少：多头为正、空头为负且幅度大，代表相对强度正朝交易方向加速。',
 'ADX(五日变化)':'ADX衡量趋势强弱（不分涨跌），≥20算有趋势；括号是5日变化，上升=趋势正在增强。',
 '5日涨跌':'主力合约近5个交易日收盘价的涨跌幅。',
 'OI五日':'持仓量（Open Interest，未平仓合约总数）近5日变化。增加=新资金带新仓进场，比纯平仓推出来的行情更扎实。',
 '量比':'当日成交量÷近20日均量。1.2–3倍是温和放量；超过3倍反而可能是情绪冲顶。',
 'IV−HV20':'期权隐含波动率IV 减 标的近20日实际波动率HV20。正=期权比近期实际波动贵，负=相对便宜。',
 '趋势·阶段':'系统判定的趋势生命周期（趋势启动/持续趋势/过度延伸等）及已持续交易日数，悬停看判定原因。',
 '状态':'反转雷达判定：强势衰退、衰退排列、扩散翻多/翻空、回补反弹（下跌中）、减仓上行（多头趋势中）。',
 '警报':'触发的反转预警条目，越多越值得盯防；列表按警报数优先排序。',
 '回补反弹':'下跌趋势中价格5日涨≥1%但持仓量减≥1%：上涨主要来自空头买回平仓，是一次性买盘，别当成反转追多。',
 '减仓上行':'多头趋势中价格涨但持仓量反而降：新资金没接力（可能是获利了结+空头回补），属于资金背离警示——不是看空信号，但需盯能否重新增仓；若Back结构同步强化则基本面仍支撑。',
 '价涨仓减':'无明确趋势背景时，5日价升≥1%而持仓量减≥1%，疑似空头回补。',
 'RPS20':'近20日涨跌幅在全市场的百分位名次（0最弱、100最强，原始值）。',
 'RPS60':'近60日涨跌幅在全市场的百分位名次，代表中期相对强弱。',
 'RPS120':'近120日涨跌幅在全市场的百分位名次，代表长期相对强弱。',
 'RPS五日变化':'RPS20相对5日前的变化：快速下滑=领导地位丧失，快速上升=变强。',
 'RPS阶梯':'RPS20<RPS60<RPS120=短期已转弱但长期仍强（衰退前兆）；RPS20>RPS60>RPS120=短期率先转强（新趋势扩散）。',
 'Carry五日':'年化Carry近5日变化。Back中下滑=牛市基本面恶化；Contango中回升=空头基本面恶化。',
 '合约':'真实到期的期货合约代码（如CF611=棉花2026年11月交割）。',
 '角色':'按持仓量OI排的流动性角色：主力=最活跃合约，其后依次是次主力、第三活跃。',
 '交割月':'该合约到期交割的年月。',
 '距交割天数':'距最后交易日的自然日；≤5天的合约已剔除（临近交割流动性与价格易失真）。',
 '结算价':'交易所当日结算价（未复权），构造期限曲线用它而不是收盘价。',
 '成交量':'当日成交手数，衡量能不能方便地进出。',
 '持仓量':'收盘后未平仓手数（OI），衡量资金深度；越大买卖越容易成交。',
 '10倍候选合约':'期权链中轻中度虚值合约（|Delta|0.10–0.40、7–30天到期），列评分最高的3张。',
 '方向':'认购=Call（做多买），认沽=Put（做空买）。',
 '行权价':'期权约定的标的买卖价；它离现价的距离就是虚值程度。',
 '剩余天':'距期权到期的自然日（DTE）。7–15天Gamma最强且行情来得及，是10倍模型甜区；>30天爆发力弱不入选。',
 'Delta':'标的每变动1元，期权价格理论变动多少。|Delta|0.15–0.30=权利金便宜又有足够爆发力的甜区。',
 'Gamma评级':'Delta随行情加速的能力（同链相对归一）。评级越高，标的一穿越行权价期权涨得越猛。',
 '参考IV':'由期权价格反算的隐含波动率，即市场对未来波动的定价（年化%）。',
 'IV状态':'IV相对HV20的位置：低于HV=便宜，中低位适合买方；"已透支"(溢价>30%)时方向看对也可能因IV回落亏钱。',
 '合约分/20':'10倍模型合约层得分=Delta位置6+Gamma4+到期时间5+流动性5。',
 '流动性':'成交量与持仓量取小：≥2000充足，≥1000合格，以下偏薄。',
 '期权合约':'具体期权代码（品种-月份-认购C/认沽P-行权价）。',
 '档位':'主仓|Delta|0.20–0.55胜率较高；彩票仓0.08–0.20权利金极便宜但归零概率也高。',
 'Gamma':'标的每涨1元时Delta的增加量；平值附近最大，是期权"加速上涨"的来源。',
 'Theta/日':'每多持有一天损失的时间价值，是买方的持有成本；到期越近损耗越快。',
 'Vega/1%':'IV每升1个百分点期权赚多少；IV从低位抬升是10倍行情的收益来源之一。',
 '趋势阶段':'趋势生命周期阶段及持续交易日数。',
 '阶段持续':'当前阶段已维持的交易日数；越久越成熟，也可能越接近末端。',
 '阶段原因':'判成该阶段的具体依据（ADX、均线排列、偏离ATR等）。',
 '原版趋势分':'最早策略模块的0–100趋势分，≥70为已确认趋势。',
 '原版启动分':'最早策略模块的启动观察分，≥65进入启动观察。',
 '启动命中':'九条原始启动信号命中的条数。',
 '偏离MA20':'现价离20日均线的距离，用ATR（近14日平均波幅）标准化；>3表示短线涨/跌过头，追单风险高。',
 'ATR分位':'当前波动率ATR在近一年中的百分位。低位=长期低波动压缩，往往是突破前夜。',
 '期限结构':'近月与远月合约的价格排列。Backwardation（近月>远月）=现货紧缺、支持做多；Contango（近月<远月）=现货疲软、支持做空。',
 '年化Carry':'(近月价÷远月价−1)按月份差年化的百分比，让不同品种可横向比较。正=Backwardation，负=Contango。',
 'Carry二十日':'Carry近20日变化，看中期结构改善/恶化的速度。',
 '曲率':'(近月+远月−2×中月)÷中月，衡量曲线中段凹陷/凸起，异常提示近远月供需错配。',
 'HV20':'标的近20日实际涨跌算出的年化历史波动率，是判断期权贵不贵的基准。',
 '10倍潜力':'品种发动机80分（趋势/RPS/ADX/资金/基本面/IV）+最优合约20分；≥80高、60–80中。',
 '建议':'该做多买Call还是做空买Put，以及模型偏好的Delta与到期日区间。',
 '最优合约':'10倍合约池里评分最高的那张期权。',
 rps_strength:'RPS强度：方向RPS20越高分越多，衡量相对强弱的绝对位置。',
 rps_accel:'RPS加速度：5日内相对强度朝交易方向移动越快分越高。',
 adx_accel:'ADX加速度：ADX上升且DI同向得高分，DI反向打对折。',
 breakout:'突破强度：刚突破基底平台10分，破55日平台3分，破20日平台2分。',
 oi:'OI变化：5日和20日持仓都增加得满分=新资金持续进场。',
 volume:'成交量：温和放量(量比1.2–3)满分；爆量(>3倍)降分，可能是行情末端。',
 inventory:'库存/基差：需导入外部现货数据；现货价与基差变化同交易方向才得分，未导入则缺失。',
 term:'期限结构Carry：Back/Contango与方向一致6分，Carry显著(≥2%)+2，5日动量同向+2。',
 iv:'期权IV项：IV相对HV越便宜分越高；期权已被炒贵（溢价大）得低分。',
 liquidity:'期权流动性：参考合约成交量与持仓量越大分越高，2000手以上满分。',
 sig_rps_top:'做多=20日涨幅排进全市场前10%；做空=排进后10%（原始RPS20≤10）。代表相对强弱到了极端。',
 sig_rps_rise:'RPS在5天内朝交易方向移动≥10个百分位=领导地位正在快速获得/丧失。',
 sig_adx_turn:'ADX五日上升≥3且≥20，同时DI方向与交易一致=趋势正在启动增强。',
 sig_breakout:'刚突破/跌破基底平台，或突破/跌破20日、55日高低点。',
 sig_oi_up:'持仓量5日增加=增仓行情，靠新资金推动而不是纯平仓。',
 sig_volume_up:'量比≥1.2=成交量配合放大。',
 sig_inventory:'需外部导入现货数据；现货价与基差5日变化都与交易方向同向。',
 sig_term:'做多要Backwardation且Carry五日未反转走弱；做空要Contango同向。',
 sig_iv_not_hot:'IV≤HV20的1.3倍且≤60%=期权还没被提前炒贵。',
 sig_liquidity_ok:'参考期权合约成交量和持仓量都≥1000手，实际能进出。',
 tb_startup:'趋势启动25分=平台突破10+启动信号条数10（8条满分）+四重共振5，衡量行情是否正在爆发。',
 tb_rps:'RPS动量15分=相对强弱位置8+5日加速度7。',
 tb_adx:'ADX/DI10分=趋势强度正在拐头且DI与交易方向一致。',
 tb_oi_volume:'持仓+成交10分=增仓6+放量4，判断是不是新资金推动的真趋势。',
 tb_fundamentals:'基本面10分=期限结构Carry6+现货基差/库存4（未导入时该子项缺失、按6分归一）。',
 tb_iv_state:'IV状态10分=期权便宜度6+标的低波动压缩2+已实际突破2，专防"方向对但期权买贵"。',
 '结构':'商品市场独有的第二套雷达：结构与价格趋势一致时给"强/中/弱"质量；结构方向与价格趋势相反且结构分≥55时显示"多/空头酝酿"（供需先变、价格未动）。',
 '结构方向':'结构面（资金/现货/跨期/曲线）综合占优的方向，独立于价格趋势方向；两者相反时即为"背离"。',
 '结构分':'五维度按可用项归一后的0–100分：多头结构分与空头结构分分别计算，高者且高出≥10分才算占优。',
 '资金(OI)':'价格方向×持仓变化的资金性质：价涨仓增=新多进入（真资金），价涨仓减=空头平仓（一次性买盘），价跌仓增=新空进入，价跌仓减=多头撤退。',
 '现货(基差)':'现货价与基差变化是否同向确认期货趋势：两者同向=现货真实性确认（满分10），仅一项同向给5分；需导入fundamentals.csv，否则缺失。',
 '跨期(月差)':'近远月价差的变化方向：价差走扩=近端转紧（利多），收窄=近端转松（利空）；当前价差符号同向再加2分。',
 '曲线(期限结构)':'整条曲线的定价：Backwardation（近强远弱）=市场交易短缺，Contango（近弱远强）=过剩；Carry动量同向+2、五日拐点+2。',
 '库存':'库存/仓单变化：累库利空、去库利多。当前外部数据仅含现货与全品种OI，库存未接入，该维度缺失不计分。',
 '背离':'结构占优方向与价格趋势相反且结构分≥55：库存/基差/月差/期限结构已先变而价格尚未反映，是提前观察区（非入场信号）。',
 '覆盖':'五维度中实际有数据的维度数；缺失维度不计入可用分，按可用分归一，不虚构数值。',
 '价格趋势':'价格趋势雷达（RPS/ADX/突破/均线）判定的方向与生命周期阶段。',
};
const tip=key=>{const text=GLOSSARY[key];if(!text)return null;const s=document.createElement('span');s.className='tip';s.textContent='?';s.setAttribute('data-tip',text);return s};
let tipActive=null,tipPinned=false;
function tipBubble(){let b=document.getElementById('tip-bubble');if(!b){b=document.createElement('div');b.id='tip-bubble';document.body.appendChild(b)}return b}
function placeTip(el){
 const b=tipBubble();const pad=6;
 b.classList.add('show');
 const w=b.offsetWidth,h=b.offsetHeight,vw=window.innerWidth,vh=window.innerHeight;
 const r=el.getBoundingClientRect();
 let x=r.left+r.width/2-w/2;
 x=Math.max(pad,Math.min(x,vw-w-pad));
 let y=r.bottom+6;
 if(y+h>vh-pad)y=Math.max(pad,r.top-h-6);
 b.style.left=x+'px';b.style.top=y+'px';
}
function showTip(el,pinned=false){tipPinned=pinned;if(tipActive===el&&!pinned)return;tipActive=el;const b=tipBubble();b.textContent=el.getAttribute('data-tip');placeTip(el)}
function hideTip(force=false){if(tipPinned&&!force)return;tipPinned=false;tipActive=null;tipBubble().classList.remove('show')}
document.addEventListener('pointerover',e=>{const el=e.target.closest?.('.tip');if(el){tipPinned=false;showTip(el)}});
document.addEventListener('pointerout',e=>{if(tipActive&&!tipPinned&&(!e.relatedTarget||!tipActive.contains(e.relatedTarget)))hideTip(true)});
document.addEventListener('click',e=>{const el=e.target.closest?.('.tip');if(el){e.stopPropagation();showTip(el,true)}else hideTip(true)});
document.addEventListener('scroll',()=>{if(tipActive)placeTip(tipActive)},{capture:true});
window.addEventListener('resize',()=>{if(tipActive)placeTip(tipActive)});
function decorateHeaders(){document.querySelectorAll('thead th').forEach(th=>{if(th.querySelector('.tip'))return;const mark=tip(th.textContent.trim());if(mark)th.appendChild(mark)})}
const DIR_TEXT={long:'多头',short:'空头',neutral:'震荡'};
const STRUCT_DIR_TEXT={long:'偏多',short:'偏空',neutral:'中性'};
const structCell=r=>r.structure_divergence??(r.structure_quality??'—');
const structClass=r=>r.structure_divergence?'fail':(r.structure_quality==='强'?'up':r.structure_quality==='弱'?'down':'');
const DIM_LABELS=[['oi','资金 · OI'],['basis','现货 · 基差'],['spread','跨期 · 月差'],['term','曲线 · 期限结构'],['inventory','库存']];
const phaseText=r=>`${DIR_TEXT[r.trend_direction]??'—'}·${r.phase??'—'}${r.phase_age==null?'':`（${r.phase_age}日）`}`;
const TAB_TITLES={long:'多头候选',short:'空头候选',extended:'过度延伸观察'};
const rows=()=>scanner[direction];
function renderList(){
 const list=rows();
 $('list-title').textContent=TAB_TITLES[direction]??'候选';
 $('list-count').textContent=`${list.length}个`;
 $('scan-summary').textContent=direction==='extended'?scanner.extension_note:'爆发指数=十项加权（缺失模块按可用权重归一）· 组合信号为满足/适用条数';
 const body=$('scan-rows');body.replaceChildren();
 list.forEach(record=>{
  const tr=document.createElement('tr');tr.dataset.code=record.ts_code;tr.tabIndex=0;
  const first=document.createElement('td'),name=document.createElement('strong'),contract=document.createElement('span');
  name.textContent=record.name;contract.className='contract';contract.textContent=record.main_code;first.append(name,contract);tr.appendChild(first);
  const m=record.metrics;
  const columns=[
   {text:record.sector},
   {text:fmt(record.explosion_score)+(record.tenbagger?.label==='高'?' · 10倍高':''),cls:'score-cell'},
   {text:`${record.signals_met}/${record.signals_applicable}${record.resonance?' ★':''}`},
   {text:fmt(m.rps20)},
   {text:signed(m.rps_accel)},
   {text:`${fmt(m.adx)}(${signed(m.adx_slope)})`},
   {text:signed(m.return5),cls:signedClass(m.return5)},
   {text:signed(m.oi_change5),cls:signedClass(m.oi_change5)},
   {text:fmt(m.volume_ratio)},
   {text:signed(m.iv_premium),cls:signedClass(m.iv_premium,true)},
   {text:phaseText(record),title:record.phase_reason||''},
   {text:structCell(record),cls:structClass(record)}];
  columns.forEach(({text,cls,title})=>{const td=document.createElement('td');td.textContent=text;if(cls)td.className=cls;if(title)td.title=title;tr.appendChild(td)});
  const open=()=>{detailCode=record.ts_code;renderDetail();$('scan-detail').hidden=false;$('scan-detail').scrollIntoView({behavior:'smooth',block:'start'})};
  tr.onclick=open;tr.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open()}};
  body.appendChild(tr);
 });
 if(!list.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=13;td.className='empty';td.textContent=direction==='extended'?'当前没有处于过度延伸阶段的品种。':'当前方向没有可排名的品种。';tr.appendChild(td);body.appendChild(tr)}
}
const TB_ENGINE_LABELS={startup:'趋势启动（25）',rps:'RPS动量（15）',adx:'ADX/DI（10）',oi_volume:'OI+成交（10）',fundamentals:'基差/月差/库存（10）',iv_state:'IV状态（10）'};
function renderTenbagger(record,dir){
 const tb=record.tenbagger;const summary=$('tb-summary');summary.replaceChildren();
 if(!tb){return}
 const rec=tb.best?`关注 ${tb.side} · ${tb.delta_hint} · ${tb.dte_hint}`:`当前无 |Delta|0.10–0.40、DTE7–30 的候选合约`;
 [['10倍潜力',tb.score==null?'—':`${tb.score}分（${tb.label}）`],['建议',rec],['最优合约',tb.best??'—'],
  ['IV状态',tb.iv_state],['ATR分位',tb.atr_percentile==null?'—':fmt(tb.atr_percentile)]].forEach(([label,value])=>{
  const div=document.createElement('div'),span=document.createElement('span');span.textContent=label;
  const mark=tip(label);if(mark)span.appendChild(mark);
  div.append(span,document.createTextNode(String(value)));summary.appendChild(div)});
 const grid=$('tb-grid');grid.replaceChildren();
 Object.entries(tb.engine).forEach(([key,item])=>{
  const div=document.createElement('div');div.className='rule-check';
  const text=document.createElement('span');text.textContent=`${TB_ENGINE_LABELS[key]||key}${item.missing?'（部分缺失，按'+item.avail+'分归一）':''}`;
  const mark=tip('tb_'+key);if(mark)text.appendChild(mark);
  const status=document.createElement('span');status.textContent=`${item.score}/${item.max}`;
  status.className=item.score>=item.max*.7?'pass':item.score>0?'fail':'missing';
  div.append(text,status);grid.appendChild(div)});
 const body=$('tb-rows');body.replaceChildren();
 tb.contracts.forEach(pick=>{
  const tr=document.createElement('tr');
  const first=document.createElement('td'),code=document.createElement('strong'),under=document.createElement('span');
  code.textContent=pick.ts_code;under.className='contract';under.textContent=`到期 ${pick.maturity_date} · 权利金 ${fmt(pick.premium)}`;first.append(code,under);tr.appendChild(first);
  [pick.call_put==='C'?'认购':'认沽',fmt(pick.exercise_price),pick.days_to_expiry,fmt(pick.delta),pick.gamma_label,
   fmt(pick.iv_reference)+'%',pick.iv_premium_pct==null?'—':signed(pick.iv_premium_pct)+'%',pick.iv_state,
   `${pick.tb_score}/20`,pick.vol,pick.oi,pick.liq_label].forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.appendChild(td)});
  body.appendChild(tr)});
 if(!tb.contracts.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=13;td.className='empty';td.textContent='无轻中度虚值（|Delta|0.10–0.40、DTE7–30）合约；可在下方常规候选表查看主仓/彩票仓。';tr.appendChild(td);body.appendChild(tr)}
}
function renderDetail(){
 const record=rows().find(r=>r.ts_code===detailCode);
 if(!record){$('scan-detail').hidden=true;return}
 const dir=direction==='extended'?record.direction:direction;
 $('detail-title').textContent=`${record.name} · ${record.ts_code} · ${dir==='long'?'做多':'做空'}`;
 const m=record.metrics;
 $('detail-summary').replaceChildren();
 [['爆发指数',fmt(record.explosion_score)],['组合信号',`${record.signals_met}/${record.signals_applicable}${record.resonance?' ★':''}`],
  ['趋势阶段',phaseText(record)],['阶段持续',record.phase_age==null?'—':`${record.phase_age}个交易日`],['阶段原因',record.phase_reason??'—'],
  ['原版趋势分',fmt(record.trend_score)],['原版启动分',fmt(record.startup_score)],
  ['启动命中',`${record.startup_hits}/9`],['方向RPS20',fmt(m.rps20)],['RPS加速度',signed(m.rps_accel)],['偏离MA20',`${fmt(m.extension_atr)} ATR`],['ATR分位',m.atr_percentile==null?'—':fmt(m.atr_percentile)],
  ['期限结构',m.structure??'—'],['年化Carry',pct(m.carry_annualized)],['Carry五日',m.carry_change5==null?'—':signed(m.carry_change5)],['Carry二十日',m.carry_change20==null?'—':signed(m.carry_change20)],
  ['曲率',fmt(m.curvature)],['参考IV',fmt(m.iv)],['HV20',fmt(m.hv20)],['IV−HV20',signed(m.iv_premium)]].forEach(([label,value])=>{
  const div=document.createElement('div'),span=document.createElement('span');span.textContent=label;
  const mark=tip(label);if(mark)span.appendChild(mark);
  div.append(span,document.createTextNode(String(value)));$('detail-summary').appendChild(div)});
 const structureSummary=$('detail-structure');
 if(record.structure)fillSummary(structureSummary,structureEntries(record.structure));
 else{structureSummary.replaceChildren();structureSummary.textContent='该品种缺少结构数据。'}
 const grid=$('item-grid');grid.replaceChildren();
 Object.entries(record.items).forEach(([key,item])=>{
  const div=document.createElement('div');div.className='rule-check';
  const text=document.createElement('span');text.textContent=`${ITEM_LABELS[key]||key}（满分${item.max}）`;
  const mark=tip(key);if(mark)text.appendChild(mark);
  const status=document.createElement('span');
  if(item.status==='ok'){status.textContent=`${item.score}/${item.max}`;status.className=item.score>=item.max*.7?'pass':item.score>0?'fail':'missing'}
  else{status.textContent='缺失';status.className='missing'}
  div.append(text,status);grid.appendChild(div)});
 const list=$('signal-list');list.replaceChildren();
 const labels=SIGNAL_LABELS(dir,m);
 Object.entries(record.signals).forEach(([key,value])=>{
  const div=document.createElement('div');div.className='rule-check';
  const text=document.createElement('span');text.textContent=labels[key]||key;
  const mark=tip('sig_'+key);if(mark)text.appendChild(mark);
  const status=document.createElement('span');
  status.textContent=value===true?'成立':value===false?'不成立':'数据缺失';status.className=value===true?'pass':value===false?'fail':'missing';
  div.append(text,status);list.appendChild(div)});
 renderTenbagger(record,dir);
 const termNote=$('term-note');
 if(m.structure==null){termNote.textContent='该品种缺少固定主次对的真实结算价历史，期限结构动量缺失。'}
 else{termNote.textContent=`当前${m.structure}（年化Carry ${pct(m.carry_annualized)}），五日变化 ${m.carry_change5==null?'—':signed(m.carry_change5)} 个百分点${m.structure_flip5?'，五日内符号已翻转——期限结构拐点':''}。Carry来自真实月合约（未复权）固定主次对；下方三档曲线来自当日全合约快照，旧快照可能没有。${record.resonance?' 四重共振已触发：'+record.resonance_parts.join(' + ')+'。':''}`}
 const termBody=$('term-rows');termBody.replaceChildren();
 record.curve.forEach(row=>{
  const tr=document.createElement('tr');
  [row.ts_code,row.role,row.delivery_month,row.days_to_delivery,fmt(row.settle),row.vol,row.oi].forEach(value=>{
   const td=document.createElement('td');td.textContent=value;tr.appendChild(td)});
  termBody.appendChild(tr)});
 if(!record.curve.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=7;td.className='empty';td.textContent='当日无全合约曲线快照（旧数据）；Carry动量仍按固定主次对历史计算。';tr.appendChild(td);termBody.appendChild(tr)}
 const note=$('contract-note');note.textContent=record.contracts.length?'档位规则：主仓|Delta| 0.20–0.55、彩票仓0.08–0.20，期限优先20–60自然日，依次放宽10–60、7–120天；按贴近目标|Delta|与流动性挑选。':'该品种当前没有同时满足有效期（7–120天）、有效量仓与参考IV的期权合约，期权相关评分按缺失处理。';
 const body=$('contract-rows');body.replaceChildren();
 record.contracts.forEach(pick=>{
  const tr=document.createElement('tr');
  const first=document.createElement('td'),code=document.createElement('strong'),under=document.createElement('span');
  code.textContent=pick.ts_code;under.className='contract';under.textContent=`${pick.underlying_code} · 到期 ${pick.maturity_date} · 权利金 ${fmt(pick.premium)}`;first.append(code,under);tr.appendChild(first);
  const tier=document.createElement('td'),tag=document.createElement('span');tag.className=`contract-tier ${pick.tier.startsWith('主仓')?'main':''}`;tag.textContent=pick.tier;
  if(pick.note)tag.title=pick.note;tier.appendChild(tag);tr.appendChild(tier);
  [pick.call_put==='C'?'认购':'认沽',fmt(pick.exercise_price),pick.days_to_expiry,fmt(pick.delta),fmt(pick.gamma),fmt(pick.theta),fmt(pick.vega),
   pick.iv_reference==null?'—':fmt(pick.iv_reference)+'%',pick.vol,pick.oi].forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.appendChild(td)});
  body.appendChild(tr);
 });
 if(!record.contracts.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=12;td.className='empty';td.textContent='无可挑选合约';tr.appendChild(td);body.appendChild(tr)}
 $('detail-option-link').href=`/options.html?asof=${scanner.asof}&code=${record.ts_code}`;
}
function setDirection(value){
 direction=value;detailCode=null;$('scan-detail').hidden=true;$('structure-detail').hidden=true;
 [['dir-long','long'],['dir-short','short'],['dir-extended','extended'],['dir-radar','radar'],['dir-structure','structure']].forEach(([id,key])=>{
  $(id).classList.toggle('active',value===key);$(id).setAttribute('aria-selected',value===key)});
 const radar=value==='radar',structure=value==='structure';
 $('scan-wrap').hidden=radar||structure;$('radar-wrap').hidden=!radar;$('structure-wrap').hidden=!structure;
 if(radar)renderRadar();else if(structure)renderStructure();else renderList();
}
function dimText(d){
 if(!d||d.status!=='ok')return '缺失';
 const parts=[d.state];
 if(d.direction)parts.push(STRUCT_DIR_TEXT[d.direction]);
 if(d.change)parts.push(d.change);
 return parts.join(' · ');
}
function structureEntries(s){
 return [['结构方向',s.dominant?STRUCT_DIR_TEXT[s.dominant]:'中性混合'],
  ['结构分',`偏多 ${fmt(s.long_score)} / 偏空 ${fmt(s.short_score)}`],
  ['结构质量',s.quality??'—'],['背离',s.divergence??'—'],['覆盖',`${s.coverage}/5`],
  ...DIM_LABELS.map(([key,label])=>[label,dimText(s[key])])];
}
function fillSummary(container,entries){
 container.replaceChildren();
 entries.forEach(([label,value])=>{
  const div=document.createElement('div'),span=document.createElement('span');span.textContent=label;
  const mark=tip(label);if(mark)span.appendChild(mark);
  div.append(span,document.createTextNode(String(value)));container.appendChild(div)});
}
function renderStructureDetail(s){
 $('structure-title').textContent=`${s.name??''} · ${s.ts_code} · 结构雷达`;
 fillSummary($('structure-summary'),structureEntries(s).slice(0,5));
 const grid=$('structure-grid');grid.replaceChildren();
 DIM_LABELS.forEach(([key,label])=>{
  const d=s[key],div=document.createElement('div');div.className='rule-check';
  const text=document.createElement('span');text.textContent=label;
  const mark=tip(label);if(mark)text.appendChild(mark);
  const status=document.createElement('span');
  if(!d||d.status!=='ok'){status.textContent='缺失（不计入可用分）';status.className='missing'}
  else{status.textContent=dimText(d);status.className=d.direction&&d.direction===s.trend_direction?'pass':'fail'}
  div.append(text,status);grid.appendChild(div)});
 const parts=[];
 if(s.divergence)parts.push(`${s.divergence}：资金/现货/跨期/曲线已偏向${STRUCT_DIR_TEXT[s.dominant]}，但价格趋势仍为${DIR_TEXT[s.trend_direction]??'未确认'}——供需结构先变、价格尚未确认，属于提前观察区，不是入场信号。`);
 else if(s.quality)parts.push(`结构面与价格趋势（${DIR_TEXT[s.trend_direction]??'—'}）方向一致，结构质量${s.quality}${s.quality==='强'?'：资金与供需支持这波趋势延续。':s.quality==='中'?'：结构部分支持，需继续观察资金与月差能否跟进。':'：结构支撑不足，趋势持续性存疑，追单需谨慎。'}`);
 else parts.push('价格趋势尚未明确，结构面作为独立参考，等待价格趋势雷达确认。');
 parts.push(`覆盖 ${s.coverage}/5 个维度，缺失维度不计入可用分；现货/基差需导入 fundamentals.csv，库存当前未接入。`);
 $('structure-verdict').textContent=parts.join(' ');
}
function renderStructure(){
 const list=scanner.structure??[];
 $('list-title').textContent='结构雷达';$('list-count').textContent=`${list.length}个品种`;
 $('scan-summary').textContent=scanner.structure_note??'';
 const body=$('structure-rows');body.replaceChildren();
 list.forEach(s=>{
  const tr=document.createElement('tr');tr.tabIndex=0;
  const cells=[
   {text:`${s.name??''} / ${s.ts_code??''}`},{text:s.sector??'—'},
   {text:s.dominant?STRUCT_DIR_TEXT[s.dominant]:'中性混合',cls:s.dominant==='long'?'up':s.dominant==='short'?'down':''},
   {text:fmt(s.best_score),cls:'score-cell'},
   {text:dimText(s.oi)},{text:dimText(s.basis)},{text:dimText(s.spread)},{text:dimText(s.term)},{text:dimText(s.inventory)},
   {text:s.divergence??'—',cls:s.divergence?'fail':''},
   {text:phaseText(s)},{text:`${s.coverage}/5`}];
  cells.forEach(({text,cls})=>{const td=document.createElement('td');td.textContent=text;if(cls)td.className=cls;tr.appendChild(td)});
  const open=()=>{renderStructureDetail(s);$('scan-detail').hidden=true;$('structure-detail').hidden=false;$('structure-detail').scrollIntoView({behavior:'smooth',block:'start'})};
  tr.onclick=open;tr.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open()}};
  body.appendChild(tr)});
 if(!list.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=12;td.className='empty';td.textContent='暂无结构雷达数据（需要持仓、真实月对结算价或已导入现货）。';tr.appendChild(td);body.appendChild(tr)}
}
function renderRadar(){
 const list=scanner.radar??[];
 $('list-title').textContent='反转雷达';$('list-count').textContent=`${list.length}个品种`;
 $('scan-summary').textContent=scanner.radar_note??'';
 const body=$('radar-rows');body.replaceChildren();
 list.forEach(r=>{
  const tr=document.createElement('tr');
  const cells=[
   {text:`${r.name??''} / ${r.ts_code??''}`},{text:r.sector??'—'},
   {text:r.state,cls:r.state==='常规'?'':(r.state.includes('翻多')?'up':'down')},
   {text:r.alerts.length?r.alerts.join('；'):'—'},
   {text:fmt(r.rps20)},{text:fmt(r.rps60)},{text:fmt(r.rps120)},
   {text:signed(r.rps_slope5),cls:signedClass(r.rps_slope5)},
   {text:r.ladder??'—'},
   {text:pct(r.oi_change5),cls:signedClass(r.oi_change5)},
   {text:pct(r.return5),cls:signedClass(r.return5)},
   {text:pct(r.carry_change5),cls:signedClass(r.carry_change5)}];
  cells.forEach(({text,cls})=>{const td=document.createElement('td');td.textContent=text;if(cls)td.className=cls;tr.appendChild(td)});
  body.appendChild(tr)});
 if(!list.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=12;td.className='empty';td.textContent='暂无反转雷达数据。';tr.appendChild(td);body.appendChild(tr)}
}
async function init(){
 try{
  data=await api('/api/data'+(asofQuery()?'?'+asofQuery():''));
  $('data-date').textContent=`收盘日 ${data.asof} · 期权扫描`;
  scanner=await api('/api/scanner'+(asofQuery()?'?'+asofQuery():''));
  $('scan-notes').textContent=scanner.notes.join(' ')||'无额外限制说明。';
  enableTableSorting(document.querySelector('.table-wrap table'));
  $('scan-detail').querySelectorAll('.table-wrap table').forEach(table=>enableTableSorting(table));
  enableTableSorting($('radar-wrap').querySelector('table'));
  enableTableSorting($('structure-wrap').querySelector('table'));
  decorateHeaders();
  renderList();
  $('dir-long').onclick=()=>setDirection('long');$('dir-short').onclick=()=>setDirection('short');$('dir-extended').onclick=()=>setDirection('extended');$('dir-radar').onclick=()=>setDirection('radar');$('dir-structure').onclick=()=>setDirection('structure');
  $('close-detail').onclick=()=>{detailCode=null;$('scan-detail').hidden=true};
  $('close-structure').onclick=()=>{$('structure-detail').hidden=true};
  await mountToolbar();
 }catch(error){$('scan-error').textContent=error.message;$('data-date').textContent='数据读取失败'}
}
init();
