let market="us", view="markets", quotes={}, signals=null, sigLoading=false, sortBy="sig", sigProg={done:0,total:0};
let chartType="candle", lastData=null, lastSym="", crossModel="composite", fwdModel="composite", fwdPolling=false;
let maCfg=[{n:5,c:'#f59e0b',on:true},{n:10,c:'#a855f7',on:false},{n:20,c:'#3b82f6',on:true},{n:60,c:'#ec4899',on:false}];
const PAL=['#3b82f6','#22c55e','#f59e0b','#ef4444','#a855f7','#06b6d4','#ec4899','#84cc16'];
const $=id=>document.getElementById(id);
function toast(m){const t=$("toast");t.textContent=m;t.classList.add("on");setTimeout(()=>t.classList.remove("on"),4000);}

function spark(v,w=118,h=34){ if(!v||v.length<2)return"";
  const mn=Math.min(...v),mx=Math.max(...v),rg=(mx-mn)||1;
  const p=v.map((x,i)=>`${(i/(v.length-1)*w).toFixed(1)},${(h-2-(x-mn)/rg*(h-4)).toFixed(1)}`).join(" ");
  return `<svg width="${w}" height="${h}"><polyline fill="none" stroke="${v[v.length-1]>=v[0]?'#22c55e':'#ef4444'}" stroke-width="1.5" points="${p}"/></svg>`;}
function chart(data,type){ if(!data||!data.length)return"";
  const w=760,h=360,pL=52,pR=14,pT=14,pB=26,iw=w-pL-pR,ih=h-pT-pB;
  const lo=Math.min(...data.map(d=>d.l)),hi=Math.max(...data.map(d=>d.h)),rg=(hi-lo)||1;
  const Y=v=>pT+ih-(v-lo)/rg*ih,n=data.length,cw=iw/n;
  let grid="";                                  // Y轴网格+价格刻度
  for(let i=0;i<=4;i++){const v=lo+rg*i/4,y=Y(v);
    grid+=`<line x1="${pL}" y1="${y.toFixed(1)}" x2="${w-pR}" y2="${y.toFixed(1)}" stroke="#262b36"/>`;
    grid+=`<text x="${pL-7}" y="${(y+3.5).toFixed(1)}" text-anchor="end" font-size="10.5" fill="#8b93a1">${v.toFixed(2)}</text>`;}
  let xl="";                                    // X轴日期刻度
  [0,(n/3)|0,(2*n/3)|0,n-1].forEach(i=>{const x=pL+cw*i+cw/2;
    xl+=`<text x="${x.toFixed(1)}" y="${h-8}" text-anchor="middle" font-size="10.5" fill="#8b93a1">${data[i].d.slice(2)}</text>`;});
  let body="";
  if(type==="line"){const anyMA=maCfg.some(m=>m.on);           // 叠了均线时价格线用中性白,避免抢色
    const col=anyMA?'#cbd5e1':(data[n-1].c>=data[0].c?'#22c55e':'#ef4444');
    const pts=data.map((d,i)=>`${(pL+cw*i+cw/2).toFixed(1)},${Y(d.c).toFixed(1)}`).join(" ");
    body=`<polyline fill="none" stroke="${col}" stroke-width="1.5" opacity="${anyMA?0.85:1}" points="${pts}"/>`;}
  else{const bw=Math.max(1.2,cw*0.6);data.forEach((d,i)=>{const x=pL+cw*i+cw/2,c=d.c>=d.o?'#22c55e':'#ef4444';
    body+=`<line x1="${x.toFixed(1)}" y1="${Y(d.h).toFixed(1)}" x2="${x.toFixed(1)}" y2="${Y(d.l).toFixed(1)}" stroke="${c}"/>`;
    const a=Y(Math.max(d.o,d.c)),b=Y(Math.min(d.o,d.c));
    body+=`<rect x="${(x-bw/2).toFixed(1)}" y="${a.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1,b-a).toFixed(1)}" fill="${c}"/>`;});}
  const cs=data.map(d=>d.c);                    // 均线:短线MA5 / 长线MA20
  const maLine=(nn,col)=>{if(nn>cs.length)return"";let pts="";for(let i=nn-1;i<cs.length;i++){let sm=0;for(let j=i-nn+1;j<=i;j++)sm+=cs[j];
    pts+=`${(pL+cw*i+cw/2).toFixed(1)},${Y(sm/nn).toFixed(1)} `;}
    return pts?`<polyline fill="none" stroke="${col}" stroke-width="1.4" opacity="0.92" points="${pts.trim()}"/>`:"";};
  let mas="",leg="",lx=pL+4;
  maCfg.filter(m=>m.on).forEach(m=>{mas+=maLine(m.n,m.c);
    leg+=`<text x="${lx}" y="17" font-size="11" fill="${m.c}">— MA${m.n}</text>`;lx+=54;});
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;background:#12151b;border-radius:8px">${grid}${xl}${body}${mas}${leg}
    <line x1="${pL}" y1="${pT}" x2="${pL}" y2="${h-pB}" stroke="#3a4150"/>
    <line x1="${pL}" y1="${h-pB}" x2="${w-pR}" y2="${h-pB}" stroke="#3a4150"/></svg>`;}
function donut(items,size=150){ const r=size/2,ir=r*0.58,cx=r,cy=r;let a0=-Math.PI/2,s="";
  items.forEach(it=>{const a1=a0+Math.max(it.w,0.0001)*2*Math.PI;
    const x0=cx+r*Math.cos(a0),y0=cy+r*Math.sin(a0),x1=cx+r*Math.cos(a1),y1=cy+r*Math.sin(a1);
    const xi0=cx+ir*Math.cos(a0),yi0=cy+ir*Math.sin(a0),xi1=cx+ir*Math.cos(a1),yi1=cy+ir*Math.sin(a1);
    const lg=(a1-a0)>Math.PI?1:0;
    s+=`<path d="M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${r} ${r} 0 ${lg} 1 ${x1.toFixed(1)} ${y1.toFixed(1)} L ${xi1.toFixed(1)} ${yi1.toFixed(1)} A ${ir} ${ir} 0 ${lg} 0 ${xi0.toFixed(1)} ${yi0.toFixed(1)} Z" fill="${it.color}"/>`;a0=a1;});
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">${s}</svg>`;}

/* ---- 行情页 ---- */
function badge(s){ if(signals&&signals[s]){const m={hold:["b-hold","持有🟢"],cash:["b-cash","空仓🔴"],wait:["b-wait","观望🟡"]}[signals[s].label];
    return `<span class="badge ${m[0]}">${m[1]} P${signals[s].p.toFixed(2)}</span>`;}
  return sigLoading?`<span class="badge b-load"><span class="spin"></span> 算信号 ${sigProg.done}/${sigProg.total||'?'}</span>`:`<span class="badge b-load">—</span>`;}
function sortedSyms(){const s=(window._syms||[]).slice(),ch=x=>quotes[x]?quotes[x].chg:-999,sg=x=>(signals&&signals[x])?signals[x].p:-1;
  if(sortBy==="chg")s.sort((a,b)=>ch(b)-ch(a));else if(sortBy==="sym")s.sort();else s.sort((a,b)=>sg(b)-sg(a));return s;}
function renderGrid(){ if(!Object.keys(quotes).length){$("grid").innerHTML=Array(6).fill('<div class="skel"></div>').join("");return;}
  const pos=(window._paper&&window._paper.positions)||{};
  $("grid").innerHTML=sortedSyms().map(s=>{const q=quotes[s];
    if(!q)return `<div class="card" data-sym="${s}"><span class="cx" data-rm="${s}">✕</span><div class="sym">${s}</div><div class="pos">无行情</div></div>`;
    const up=q.chg>=0,held=pos[s];
    return `<div class="card" data-sym="${s}"><span class="cx" data-rm="${s}">✕</span><div class="c-top"><span class="sym">${s}</span>${badge(s)}</div>
      <div class="price">${q.price.toLocaleString()}</div>
      <div class="chg ${up?'up':'down'}">${up?'▲':'▼'} ${Math.abs(q.chg).toFixed(2)}%</div>
      <div class="row2"><span class="pos">${held?('持仓 '+(+held).toFixed(0)):''}</span>${spark(q.spark)}</div></div>`;}).join("");}
async function loadQuotes(){const r=await fetch("/api/quotes?market="+market);const d=await r.json();
  quotes=d.quotes||{};window._syms=d.symbols||[];$("upd").textContent=d.updated;
  const rt=d.source==="alpaca";$("src").innerHTML=rt?'<span style="color:var(--grn)">🟢 实时 Alpaca</span>':'🕒 延迟约15分(yfinance) · 美股设Alpaca密钥可转实时';
  renderGrid();}
async function loadSignals(refresh){sigLoading=true;signals=null;sigProg={done:0,total:0};renderGrid();let first=true;
  const poll=async()=>{try{
    const d=await (await fetch("/api/signals?market="+market+((first&&refresh)?"&refresh=1":""))).json();first=false;
    if(d.status==="ready"){signals=d.signals;sigLoading=false;renderGrid();if(refresh)toast("信号已刷新");}
    else if(d.error){sigLoading=false;renderGrid();}
    else{sigProg={done:d.done||0,total:d.total||0};renderGrid();setTimeout(poll,2500);}}
    catch(e){sigLoading=false;renderGrid();}};
  poll();}
const _wlPost=(m,body)=>fetch(`/api/watchlist?market=${m}`,{method:"POST",
  headers:{"Content-Type":"application/x-www-form-urlencoded"},body});
async function wlAdd(){const v=$("wl-in").value.trim();if(!v)return;$("wl-in").value="";
  try{await _wlPost(market,"add="+encodeURIComponent(v));toast("已加入自选 "+v.toUpperCase());
    quotes={};signals=null;loadQuotes();loadSignals();}catch(e){toast("添加失败");}}
async function wlRemove(s){try{await _wlPost(market,"remove="+encodeURIComponent(s));toast("已移除 "+s);
    quotes={};signals=null;loadQuotes();loadSignals();}catch(e){}}
async function loadPaperData(){try{window._paper=await (await fetch("/api/paper")).json();}catch(e){}renderGrid();}
async function rebalance(btn,msg,method){const b=$(btn);b.disabled=true;$(msg).textContent="下单中(首次要先算信号)…";
  try{const d=await (await fetch("/api/rebalance?market="+market+"&method="+(method||"topk"))).json();
    if(d.error)toast("⚠️ "+d.error);else{const os=Object.entries(d.orders||{});
      toast(os.length?("已成交:"+os.map(([s,q])=>(q>0?"买":"卖")+s+" "+Math.abs(q)).join(" · ")):"已是目标组合");
      window._paper=d.account;if(view==="portfolio")renderPortfolio();if(view==="overview")loadOverview();renderGrid();}}
  catch(e){toast("调仓失败");}b.disabled=false;$(msg).textContent="";}
async function loadOverview(){const el=$("ov");el.innerHTML='<div class="muted"><span class="spin"></span> 加载三市场概况…</div>';
  try{const d=await (await fetch("/api/overview")).json();
    const names={us:"美股 US",hk:"港股 HK",cn:"A股 CN"},p=d.paper;
    const paper=p?`<div class="strip">
      <div><div class="k">纸面权益</div><div class="v">${(+p.equity).toLocaleString()}</div></div>
      <div><div class="k">累计收益</div><div class="v ${p.ret>=0?'up':'down'}">${p.ret>=0?'+':''}${p.ret}%</div></div>
      <div><div class="k">持仓/成交</div><div class="v">${Object.keys(p.positions).length}只 / ${p.n_trades}笔</div></div>
      <div><div class="k">权益曲线</div>${p.curve&&p.curve.length>1?spark(p.curve,140,38):'<span style="color:var(--dim)">—</span>'}</div></div>`
     :'<div class="panel"><div class="muted">还没纸面账户 · 去「组合」页一键调仓建仓</div></div>';
    const cards=Object.entries(d.markets).map(([m,x])=>{const avC=x.avg>=0?'up':'down';
      const sig=x.sig?`<div style="display:flex;gap:5px;margin-top:10px">
        <span class="badge b-hold">${x.sig.hold}持</span><span class="badge b-cash">${x.sig.cash}空</span><span class="badge b-wait">${x.sig.wait}观</span></div>`
       :'<div class="pos" style="margin-top:10px">信号未算</div>';
      return `<div class="card" data-mkt="${m}"><div class="c-top"><span class="sym">${names[m]}</span><span class="pos">${x.n}只</span></div>
        <div class="price ${x.avg!=null?avC:''}" style="font-size:21px">${x.avg!=null?(x.avg>=0?'+':'')+x.avg+'%':'—'}</div><div class="pos">平均涨跌</div>
        ${x.top_g?`<div class="row2" style="margin-top:8px"><span class="pos">领涨 <b class="up">${x.top_g.sym} +${x.top_g.chg}%</b></span><span class="pos">领跌 <b class="down">${x.top_l.sym} ${x.top_l.chg}%</b></span></div>`:''}
        ${sig}</div>`;}).join("");
    el.innerHTML=`${paper}<div class="grid" style="margin-top:14px">${cards}</div>`;}
  catch(e){el.innerHTML='<div class="muted">概况加载慢或失败 <span class="btn btn2" style="cursor:pointer;padding:5px 12px" onclick="loadOverview()">重试</span></div>';
    setTimeout(()=>{if($("ov").querySelector(".btn"))loadOverview();},2500);}}

/* ---- 组合页 ---- */
async function renderPortfolio(){const p=window._paper||await (await fetch("/api/paper")).json();window._paper=p;
  const el=$("pf");if(!p){el.innerHTML='<div class="panel"><div class="muted">还没有纸面账户 · 点上面「一键调仓」建仓</div></div>';return;}
  const q=quotes;const held=Object.entries(p.positions||{});
  const vals=held.map(([s,qty])=>[s,q[s]?q[s].price*qty:0]);const tot=vals.reduce((a,x)=>a+x[1],0)||1;
  const items=vals.filter(x=>x[1]>0).map(([s,v],i)=>({sym:s,w:v/tot,color:PAL[i%PAL.length]}));
  const up=p.ret>=0;
  const posRows=held.map(([s,qty],i)=>{const v=q[s]?q[s].price*qty:0;
    return `<tr><td><span style="color:${items[i]?items[i].color:'#888'}">●</span> ${s}</td><td>${(+qty).toFixed(0)}</td><td>${v?v.toLocaleString(undefined,{maximumFractionDigits:0}):'—'}</td><td>${v?(v/tot*100).toFixed(0)+'%':'—'}</td></tr>`;}).join("")||'<tr><td colspan=4 class="muted">空仓</td></tr>';
  const trades=(p.trades||[]).slice().reverse().map(t=>`<tr><td>${t.time||''}</td><td>${t.qty>0?'买':'卖'} ${t.symbol}</td><td>${Math.abs(t.qty).toFixed(0)}</td><td>${t.price}</td></tr>`).join("")||'<tr><td colspan=4 class="muted">暂无成交</td></tr>';
  el.innerHTML=`
   <div class="strip">
     <div><div class="k">总权益</div><div class="v">${(+p.equity).toLocaleString()}</div></div>
     <div><div class="k">现金</div><div class="v">${(+p.cash).toLocaleString()}</div></div>
     <div><div class="k">累计收益</div><div class="v ${up?'up':'down'}">${up?'+':''}${p.ret}%</div></div>
     <div><div class="k">持仓/成交</div><div class="v">${held.length}只 / ${p.n_trades}笔</div></div>
     <div><div class="k">权益曲线</div>${p.curve&&p.curve.length>1?spark(p.curve,150,40):'<div class="v" style="color:var(--dim)">—</div>'}</div>
   </div>
   <div style="display:flex;gap:16px;flex-wrap:wrap">
     <div class="panel" style="flex:0 0 auto">${items.length?donut(items):'<div class="muted">空仓</div>'}</div>
     <div class="panel" style="flex:1;min-width:280px"><div class="sub">当前持仓</div>
       <table><tr><th>标的</th><th>股数</th><th>市值</th><th>权重</th></tr>${posRows}</table></div>
   </div>
   <div class="panel"><div class="sub">最近成交</div>
     <table><tr><th>时间</th><th>方向</th><th>股数</th><th>价</th></tr>${trades}</table></div>`;}

/* ---- 可信度页 ---- */
async function runCred(){const el=$("cred");
  el.innerHTML='<div class="muted"><span class="spin"></span> 体检中:给每只票训模型+扫阈值算 DSR/PBO,约 1–2 分钟…</div>';
  try{const d=await (await fetch("/api/credibility?market="+market)).json();
    if(!d.rows||!d.rows.length){el.innerHTML='<div class="muted">数据不足</div>';return;}
    const v=d.mean_pbo>=0.5?'🔴 整体过拟合严重':(d.mean_pbo>=0.3?'🟡 有一定过拟合风险':'✅ 过拟合可控');
    const rows=d.rows.map(r=>{const dc=r.dsr>0.95?'up':(r.dsr<0.5?'down':''),pc=r.pbo<0.2?'up':(r.pbo>=0.5?'down':'');
      return `<tr><td>${r.sym}</td><td>${r.best_th}</td><td class="${dc}">${(r.dsr*100).toFixed(0)}%</td><td class="${pc}">${(r.pbo*100).toFixed(0)}%</td></tr>`;}).join("");
    el.innerHTML=`<div class="sub">DSR 显著(&gt;95%)的 <b>${d.sig}/${d.n}</b> · 平均 PBO <b>${(d.mean_pbo*100).toFixed(0)}%</b> · ${v}<br>
      DSR=扣除多重检验后真夏普&gt;0 的概率(&gt;95%才显著);PBO=样本内最优在样本外跌破中位的概率(越低越好)</div>
      <table><tr><th>标的</th><th>最优阈值</th><th>DSR</th><th>PBO</th></tr>${rows}</table>`;}
  catch(e){el.innerHTML='<div class="muted" style="color:var(--red)">体检失败</div>';}}

/* ---- 因子页 ---- */
async function runFactors(){const s=$("f-sym").value.trim().toUpperCase();const el=$("fac");
  el.innerHTML='<div class="muted"><span class="spin"></span> 计算因子 IC…</div>';
  try{const d=await (await fetch(`/api/factors?symbol=${s}&market=${market}`)).json();
    const rows=d.map(r=>{const c=r.RankIC>0?'up':'down';
      return `<tr><td>${r.factor}</td><td>${r.IC}</td><td class="${c}">${r.RankIC}</td></tr>`;}).join("");
    el.innerHTML=`<div class="sub">${market.toUpperCase()}:${s} · 预测未来5天 · 按 |RankIC| 排序</div>
      <table><tr><th>因子</th><th>IC</th><th>RankIC</th></tr>${rows}</table>`;}
  catch(e){el.innerHTML='<div class="muted" style="color:var(--red)">失败(代码或数据)</div>';}}

/* ---- 消息面页 ---- */
async function runNews(){const s=$("n-sym").value.trim().toUpperCase();const el=$("news");
  el.innerHTML='<div class="muted"><span class="spin"></span> 抓新闻+打分…</div>';
  try{const d=await (await fetch(`/api/news?symbol=${s}&market=${market}`)).json();
    if(!d.n){el.innerHTML='<div class="muted">没抓到新闻(免费源覆盖有限,尤其港/A股)</div>';return;}
    const mk=d.mean>0.1?'🟢偏多':(d.mean<-0.1?'🔴偏空':'🟡中性');
    const items=d.items.map(it=>{const m=it.sent>0.1?'🟢':(it.sent<-0.1?'🔴':'⚪');
      return `<div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--line);font-size:13px">
        <span style="width:44px;color:var(--dim)">${m}${it.sent>=0?'+':''}${it.sent}</span>
        <span style="width:76px;color:var(--dim)">${it.date}</span><span>${it.title}</span></div>`;}).join("");
    el.innerHTML=`<div class="sub">${market.toUpperCase()}:${s} · 打分器 ${d.scorer} · 综合情绪 <b>${d.mean>=0?'+':''}${d.mean}</b> ${mk}(${d.n}条)</div>${items}`;}
  catch(e){el.innerHTML='<div class="muted" style="color:var(--red)">失败</div>';}}

/* ---- 个股页 ---- */
function renderAna(){const el=$("ana");if(!lastData){el.innerHTML='<div class="muted">输入代码,点深挖</div>';return;}
  const d=lastData,s=lastSym,cs=d.map(x=>x.c),last=cs[cs.length-1],hi=Math.max(...cs),lo=Math.min(...cs);
  const ret=((last/cs[0]-1)*100).toFixed(1),rr=cs.slice(1).map((v,i)=>v/cs[i]-1);
  const vol=(Math.sqrt(rr.reduce((a,x)=>a+x*x,0)/rr.length)*Math.sqrt(252)*100).toFixed(0);
  let pk=cs[0],mdd=0;cs.forEach(v=>{if(v>pk)pk=v;mdd=Math.min(mdd,v/pk-1)});
  const sg=(signals&&signals[s])?`<div><div class="k">信号 P(涨)</div><div class="v">${signals[s].p.toFixed(2)}</div></div>`:'';
  const stats=`<div class="strip">
    <div><div class="k">收盘</div><div class="v">${last}</div></div>
    <div><div class="k">120日涨跌</div><div class="v ${ret>=0?'up':'down'}">${ret>=0?'+':''}${ret}%</div></div>
    <div><div class="k">区间高/低</div><div class="v" style="font-size:15px">${hi} / ${lo}</div></div>
    <div><div class="k">年化波动</div><div class="v">${vol}%</div></div>
    <div><div class="k">最大回撤</div><div class="v down">${(mdd*100).toFixed(0)}%</div></div>${sg}</div>`;
  el.innerHTML=`<div class="sub">${market.toUpperCase()}:${s} · 近120日</div>${stats}${chart(d,chartType)}`;}
async function runAnalyze(sym){const s=(sym||$("a-sym").value).trim().toUpperCase();$("a-sym").value=s;lastSym=s;
  $("ana").innerHTML='<div class="muted"><span class="spin"></span> 加载K线…</div>';
  try{const d=await (await fetch(`/api/chart?symbol=${s}&market=${market}`)).json();
    if(d.error||!d.length){$("ana").innerHTML='<div class="muted" style="color:var(--red)">没数据(代码不对?)</div>';lastData=null;return;}
    lastData=d;renderAna();}
  catch(e){$("ana").innerHTML='<div class="muted" style="color:var(--red)">失败</div>';}}
function setChart(t){chartType=t;$("ct-candle").classList.toggle("on2",t==="candle");$("ct-line").classList.toggle("on2",t==="line");renderAna();}
function setMA(n){const m=maCfg.find(x=>x.n===n);m.on=!m.on;$("ma-"+n).classList.toggle("on2",m.on);renderAna();}

/* ---- 横截面选股页 ---- */
function setCrossModel(m){crossModel=m;$("cm-composite").classList.toggle("on2",m==="composite");$("cm-ml").classList.toggle("on2",m==="ml");}
async function loadCross(refresh){const el=$("cross");
  if(market!=="cn"&&market!=="hk"){el.innerHTML='<div class="muted">横截面选股目前支持 <b>A股(CN)</b> 和 <b>港股(HK)</b> —— 点左下角切换(美股数据待接)。</div>';return;}
  const isML=crossModel==="ml";
  el.innerHTML=`<div class="muted"><span class="spin"></span> ${isML?"训练 ML 排名模型":"计算稳健因子组合"} + 回测…${isML?"约30秒":""}</div>`;
  async function poll(){
    let d;try{d=await (await fetch("/api/cross?market="+market+"&model="+crossModel+(refresh?"&refresh=1":""))).json();}
    catch(e){el.innerHTML='<div class="muted" style="color:var(--red)">连接失败</div>';return;}
    refresh=false;
    if(d.status==="computing"){el.innerHTML=`<div class="muted"><span class="spin"></span> ${d.stage||"计算中…"}</div>`;setTimeout(poll,2000);return;}
    const x=d.data;
    if(!x||x.error){el.innerHTML=`<div class="muted" style="color:var(--red)">${x&&x.error?x.error:"失败"}</div>`;return;}
    const s=x.strat,dsrTag=x.dsr>0.95?'✅ 显著':'🔴 未过0.95',mlbl=x.model==="ml"?"ML排名(LightGBM)":"稳健因子组合";
    const cards=`<div class="strip">
      <div><div class="k">策略年化</div><div class="v up">${s.年化}%</div></div>
      <div><div class="k">超额年化</div><div class="v ${s.超额年化>=0?'up':'down'}">${s.超额年化>=0?'+':''}${s.超额年化}%</div></div>
      <div><div class="k">夏普</div><div class="v">${s.夏普}</div></div>
      <div><div class="k">Sortino</div><div class="v">${s.Sortino}</div></div>
      <div><div class="k">Calmar</div><div class="v">${s.Calmar}</div></div>
      <div><div class="k">信息比IR</div><div class="v">${s['信息比IR']}</div></div>
      <div><div class="k">换手率</div><div class="v">${s['换手率%']}%</div></div>
      <div><div class="k">最大回撤</div><div class="v down">${s.最大回撤}%</div></div>
      <div><div class="k">胜基准</div><div class="v">${x.winrate}%</div></div>
      <div><div class="k">DSR</div><div class="v ${x.dsr>0.95?'up':''}">${(x.dsr*100).toFixed(0)}%</div></div></div>`;
    const strat=x.equity.map(p=>p.s),bench=x.equity.map(p=>p.b);
    const icrows=x.ic.map(r=>{const c=r.IC>=0?'up':'down';return `<tr><td>${r.factor}</td><td class="${c}">${r.IC}</td><td>${r.ICIR}</td></tr>`;}).join("");
    const vpos=x.valid&&x.valid.length&&x.valid.every(v=>v.excess>0);
    const vrows=(x.valid||[]).map(v=>`<tr><td>${v.market}</td><td>${v.universe}只</td><td class="${v.excess>=0?'up':'down'}">${v.excess>=0?'+':''}${v.excess}%</td><td>${v.sharpe}</td></tr>`).join("");
    const validPanel=`<div class="panel" style="flex:1;min-width:260px"><div class="sub">🌏 跨市场验证(稳健组合)</div>
      <table><tr><th>市场</th><th>股票池</th><th>超额年化</th><th>夏普</th></tr>${vrows}</table>
      <div style="font-size:12px;margin-top:8px;color:${vpos?'var(--grn)':'var(--red)'}">${vpos?'✅ 两地超额均为正 —— 跨市场稳健':'🔴 有市场为负'}</div></div>`;
    const verdict=x.model==="ml"
      ? `<div style="font-size:13px;line-height:1.75">DSR=<b>${(x.dsr*100).toFixed(0)}%</b> ${dsrTag}。⚠️ 这个 ML 模型 A股漂亮但<b>港股翻车(超额−10%)</b>——大概率过拟合了 A股小盘 regime,<b>不建议用</b>,看它是为了对照。</div>`
      : `<div style="font-size:13px;line-height:1.75">固定配方、<b>零训练</b>(整段样本外),DSR=<b>${(x.dsr*100).toFixed(0)}%</b> ${dsrTag},且<b>跨市场都为正</b>。但边际不大、仍有幸存者偏差——<b>真但弱,当研究基线,别重仓</b>。</div>`;
    el.innerHTML=`<div class="sub">${market.toUpperCase()} · ${mlbl} · ${x.universe}只池 · top-20 · 样本外${x.periods}期 ${x.start}~${x.end}</div>
      ${cards}${lines2(strat,bench)}
      <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:12px">
        ${validPanel}
        <div class="panel" style="flex:1;min-width:260px"><div class="sub">横截面因子 RankIC(前8)</div>
          <table><tr><th>因子</th><th>IC</th><th>ICIR</th></tr>${icrows}</table></div>
        <div class="panel" style="flex:1;min-width:260px"><div class="sub">⚠️ 诚实判决</div>${verdict}</div>
      </div>`;
  }
  poll();}

/* ---- 前瞻曲线页 ---- */
function navchart(curve,base,w=760,h=300){const pL=58,pR=16,pT=16,pB=26,iw=w-pL-pR,ih=h-pT-pB;
  const navs=curve.map(p=>p.nav),all=navs.concat([base]);
  const mn=Math.min(...all),mx=Math.max(...all),rg=(mx-mn)||1,Y=v=>pT+ih-(v-mn)/rg*ih;
  const n=curve.length,X=i=>n<2?pL+iw/2:pL+iw*i/(n-1);
  let grid="";for(let i=0;i<=4;i++){const v=mn+rg*i/4,y=Y(v);
    grid+=`<line x1="${pL}" y1="${y.toFixed(1)}" x2="${w-pR}" y2="${y.toFixed(1)}" stroke="#262b36"/>`;
    grid+=`<text x="${pL-7}" y="${(y+3.5).toFixed(1)}" text-anchor="end" font-size="10.5" fill="#8b93a1">${Math.round(v).toLocaleString()}</text>`;}
  const by=Y(base);const bl=`<line x1="${pL}" y1="${by.toFixed(1)}" x2="${w-pR}" y2="${by.toFixed(1)}" stroke="#6b7280" stroke-width="1" stroke-dasharray="4 4"/>
    <text x="${w-pR-2}" y="${(by-4).toFixed(1)}" text-anchor="end" font-size="10.5" fill="#9ca3af">初始 ${Math.round(base).toLocaleString()}</text>`;
  const last=navs[n-1],col=last>=base?'#22c55e':'#ef4444';
  const pts=curve.map((p,i)=>`${X(i).toFixed(1)},${Y(p.nav).toFixed(1)}`).join(" ");
  const line=n<2?"":`<polyline fill="none" stroke="${col}" stroke-width="2" points="${pts}"/>`;
  const dots=curve.map((p,i)=>`<circle cx="${X(i).toFixed(1)}" cy="${Y(p.nav).toFixed(1)}" r="${n<8?3:2}" fill="${col}"/>`).join("");
  let xl="";const idx=n<=6?curve.map((_,i)=>i):[0,(n/3)|0,(2*n/3)|0,n-1];
  idx.forEach(i=>{xl+=`<text x="${X(i).toFixed(1)}" y="${h-8}" text-anchor="middle" font-size="10" fill="#8b93a1">${curve[i].d.slice(5)}</text>`;});
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;background:#12151b;border-radius:8px">${grid}${bl}${line}${dots}${xl}
    <line x1="${pL}" y1="${pT}" x2="${pL}" y2="${h-pB}" stroke="#3a4150"/>
    <line x1="${pL}" y1="${h-pB}" x2="${w-pR}" y2="${h-pB}" stroke="#3a4150"/></svg>`;}
function setForwardModel(m){fwdModel=m;$("fm-composite").classList.toggle("on2",m==="composite");$("fm-ml").classList.toggle("on2",m==="ml");renderForward();}
async function renderForward(){const el=$("forward");
  if(market!=="cn"&&market!=="hk"&&market!=="us"){el.innerHTML='<div class="muted">前瞻曲线支持 CN/HK/US —— 左下角切换市场。</div>';return;}
  let d;try{d=await (await fetch(`/api/forward?market=${market}&model=${fwdModel}`)).json();}
  catch(e){el.innerHTML='<div class="muted" style="color:var(--red)">连接失败</div>';return;}
  const running=d.running?`<div class="muted" style="margin-bottom:10px"><span class="spin"></span> ${d.stage||"推进中…"}</div>`:"";
  if(d.run_error){el.innerHTML=`${running}<div class="muted" style="color:var(--red)">推进失败:${d.run_error}<br>(前瞻推进需联网拉最新数据,本机网络或数据源不通时会失败;可命令行 <code>quantmill forward run --market ${market}</code> 排障)</div>`;return;}
  if(d.empty){el.innerHTML=`${running}<div class="muted">还没有前瞻记录(${market.toUpperCase()} · ${fwdModel==="ml"?"ML排名":"稳健组合"})。点上面「推进一步」,今天就建仓、写下第一个净值点。</div>`;return;}
  const up=d.ret>=0;
  const strip=`<div class="strip">
    <div><div class="k">起始</div><div class="v" style="font-size:15px">${d.inception}</div></div>
    <div><div class="k">现值</div><div class="v">${Math.round(d.nav).toLocaleString()}</div></div>
    <div><div class="k">累计收益</div><div class="v ${up?'up':'down'}">${up?'+':''}${d.ret}%</div></div>
    <div><div class="k">最大回撤</div><div class="v down">${d.max_dd}%</div></div>
    <div><div class="k">净值点</div><div class="v">${d.points}</div></div>
    <div><div class="k">当前敞口</div><div class="v ${d.exposure<1?'down':''}">${(d.exposure*100).toFixed(0)}%</div></div></div>`;
  const posrows=d.positions.map(p=>`<tr><td>${p.sym}</td><td>${p.w}%</td></tr>`).join("")||'<tr><td colspan=2 class="muted">空仓</td></tr>';
  const chartBlock=d.points<2
    ? `<div class="panel" style="text-align:center;color:var(--dim)">只有 1 个净值点 —— 明天(或下次)再来点一次「推进一步」,曲线才会长出来。前瞻的意义就是真实时间要一天天过去。</div>`
    : navchart(d.curve,d.base);
  el.innerHTML=`${running}<div class="sub">${market.toUpperCase()} · ${fwdModel==="ml"?"ML排名":"稳健组合"} · 起始 ${d.inception} · 上次换仓 ${d.last_rebalance||'—'} · <b style="color:var(--grn)">只前进不回看</b></div>
    ${strip}${chartBlock}
    <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:12px">
      <div class="panel" style="flex:0 0 auto;min-width:200px"><div class="sub">当前目标持仓(${d.positions.length}只)</div>
        <table><tr><th>标的</th><th>权重</th></tr>${posrows}</table></div>
      <div class="panel" style="flex:1;min-width:280px"><div class="sub">⚠️ 怎么读这条线</div>
        <div style="font-size:13px;line-height:1.75">这是纸面、不回看的<b>前瞻</b>净值:虚线是初始本金,绿/红线是实际净值,历史点<b>绝不改写</b>。<br>
        它能不能兑现回测里那点微弱 alpha,要看它<b>几个月后</b>的样子——现在点数少,别急着下结论。<br>
        每天/每周固定点一次「推进一步」即可(同一天重复点=更新今天,不新增点)。</div></div>
    </div>`;}
async function runForwardStep(){const b=$("runfwd");b.disabled=true;$("fwdmsg").textContent="推进中:取最新面板+现价…(需联网,首次较慢)";
  try{const r=await (await fetch(`/api/forward/run?market=${market}&model=${fwdModel}`,{method:"POST"})).json();
    if(r.status==="already_running")toast("已经在推进了,稍候");
    if(!fwdPolling){fwdPolling=true;const poll=async()=>{
      let d;try{d=await (await fetch(`/api/forward?market=${market}&model=${fwdModel}`)).json();}catch(e){d={};}
      if(d.running){if(view==="forward")renderForward();setTimeout(poll,2500);}
      else{fwdPolling=false;b.disabled=false;$("fwdmsg").textContent="";
        if(view==="forward")renderForward();
        toast(d.run_error?("推进失败:"+d.run_error.slice(0,40)):"已追加今日净值点 ✓");}};
      setTimeout(poll,1500);}}
  catch(e){b.disabled=false;$("fwdmsg").textContent="";toast("推进失败");}}

/* ---- 导航 / 市场 ---- */
function setView(v){view=v;document.querySelectorAll(".nav").forEach(n=>n.classList.toggle("on",n.dataset.v===v));
  document.querySelectorAll(".view").forEach(s=>s.classList.toggle("on",s.id==="v-"+v));
  if(v==="portfolio")renderPortfolio();if(v==="overview")loadOverview();if(v==="forward")renderForward();}
function setMarket(m){market=m;quotes={};signals=null;
  document.querySelectorAll(".mt").forEach(t=>t.classList.toggle("on",t.dataset.m===m));
  loadQuotes();loadSignals();if(view==="portfolio")renderPortfolio();if(view==="overview")loadOverview();
  if(view==="forward")renderForward();
  $("cred").innerHTML='<div class="muted">点上面按钮开始体检</div>';}

document.querySelector(".side").addEventListener("click",e=>{
  if(e.target.dataset.v)setView(e.target.dataset.v);
  if(e.target.dataset.m)setMarket(e.target.dataset.m);});
$("sort").addEventListener("change",e=>{sortBy=e.target.value;renderGrid();});
$("reb").addEventListener("click",()=>rebalance("reb","rebmsg"));
$("reb2").addEventListener("click",()=>rebalance("reb2","reb2msg",$("pf-method").value));
$("ov").addEventListener("click",e=>{const c=e.target.closest("[data-mkt]");if(c){setMarket(c.dataset.mkt);setView("markets");}});
function lines2(a,b,w=760,h=300){const pL=50,pR=14,pT=14,pB=22,iw=w-pL-pR,ih=h-pT-pB;
  const all=a.concat(b),mn=Math.min(...all),mx=Math.max(...all),rg=(mx-mn)||1,Y=v=>pT+ih-(v-mn)/rg*ih;
  const poly=(arr,col,wd)=>{const n=arr.length;const pts=arr.map((v,i)=>`${(pL+iw*i/(n-1)).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
    return `<polyline fill="none" stroke="${col}" stroke-width="${wd}" points="${pts}"/>`;};
  let grid="";for(let i=0;i<=4;i++){const v=mn+rg*i/4,y=Y(v);
    grid+=`<line x1="${pL}" y1="${y.toFixed(1)}" x2="${w-pR}" y2="${y.toFixed(1)}" stroke="#262b36"/>`;
    grid+=`<text x="${pL-7}" y="${(y+3.5).toFixed(1)}" text-anchor="end" font-size="10.5" fill="#8b93a1">${v.toFixed(2)}x</text>`;}
  return `<svg viewBox="0 0 ${w} ${h}" style="width:100%;background:#12151b;border-radius:8px">${grid}
    ${poly(b,'#8b93a1',1.5)}${poly(a,'#22c55e',2)}
    <text x="${w-pR-4}" y="18" text-anchor="end" font-size="12" fill="#22c55e">■ 策略</text>
    <text x="${w-pR-4}" y="34" text-anchor="end" font-size="12" fill="#8b93a1">■ 等权基准</text>
    <line x1="${pL}" y1="${pT}" x2="${pL}" y2="${h-pB}" stroke="#3a4150"/>
    <line x1="${pL}" y1="${h-pB}" x2="${w-pR}" y2="${h-pB}" stroke="#3a4150"/></svg>`;}
async function runBacktest(){const el=$("bt"),method=$("pf-method").value;
  el.innerHTML='<div class="panel"><div class="muted"><span class="spin"></span> 跑组合回测:逐只算样本外信号+回测,约 1–2 分钟…</div></div>';
  try{const d=await (await fetch(`/api/backtest?market=${market}&method=${method}`)).json();
    if(d.error){el.innerHTML=`<div class="panel"><div class="muted" style="color:var(--red)">${d.error}</div></div>`;return;}
    const row=(k,l)=>`<tr><td>${l}</td><td>${d.sm[k]}</td><td>${d.bm[k]}</td></tr>`;
    const beat=d.sm.total_return>d.bm.total_return&&d.sm.sharpe>d.bm.sharpe,dd=d.sm.max_drawdown>d.bm.max_drawdown;
    const v=beat?'✅ 收益+夏普都赢等权':(dd?'🟡 回撤更小但没多赚(避险价值)':'🔴 没赢过无脑等权(诚实结果)');
    el.innerHTML=`<div class="panel"><div class="sub">${market.toUpperCase()} · ${d.method} · ${d.period} · ${v}</div>
      ${lines2(d.strat,d.bench)}
      <table style="margin-top:12px"><tr><th>指标</th><th>信号组合</th><th>等权基准</th></tr>
      ${row('total_return','总收益%')}${row('ann_return','年化%')}${row('sharpe','夏普')}${row('max_drawdown','最大回撤%')}${row('ann_vol','年化波动%')}</table></div>`;}
  catch(e){el.innerHTML='<div class="panel"><div class="muted" style="color:var(--red)">回测失败</div></div>';}}
$("runbt").addEventListener("click",runBacktest);
$("runcross").addEventListener("click",()=>loadCross(true));
$("cm-composite").addEventListener("click",()=>setCrossModel("composite"));
$("cm-ml").addEventListener("click",()=>setCrossModel("ml"));
$("runfwd").addEventListener("click",runForwardStep);
$("fm-composite").addEventListener("click",()=>setForwardModel("composite"));
$("fm-ml").addEventListener("click",()=>setForwardModel("ml"));
$("export").addEventListener("click",()=>{window.open("/api/export?market="+market);toast("已导出快照 HTML");});
let autoTimer=null;
$("autosig").addEventListener("change",e=>{clearInterval(autoTimer);
  if(e.target.checked){autoTimer=setInterval(()=>loadSignals(true),600000);toast("已开自动刷新信号(每10分钟)");}
  else toast("已关自动刷新");});
$("refsig").addEventListener("click",()=>loadSignals(true));
$("wladd").addEventListener("click",wlAdd);
$("wl-in").addEventListener("keydown",e=>{if(e.key==="Enter")wlAdd();});
$("gsearch").addEventListener("keydown",e=>{if(e.key==="Enter"){const v=e.target.value.trim().toUpperCase();
  if(v){$("a-sym").value=v;setView("analyze");runAnalyze(v);e.target.value="";}}});
$("runcred").addEventListener("click",runCred);
$("runfac").addEventListener("click",runFactors);
$("runnews").addEventListener("click",runNews);
$("runana").addEventListener("click",()=>runAnalyze());
$("ct-candle").addEventListener("click",()=>setChart("candle"));
$("ct-line").addEventListener("click",()=>setChart("line"));
[5,10,20,60].forEach(n=>$("ma-"+n).addEventListener("click",()=>setMA(n)));
$("grid").addEventListener("click",e=>{const rm=e.target.dataset.rm;if(rm){wlRemove(rm);return;}
  const c=e.target.closest(".card");
  if(c&&c.dataset.sym){$("a-sym").value=c.dataset.sym;setView("analyze");runAnalyze(c.dataset.sym);}});

document.body.dataset.theme=localStorage.getItem("qm-theme")||"";
$("theme").addEventListener("click",()=>{const l=document.body.dataset.theme!=="light";
  document.body.dataset.theme=l?"light":"";localStorage.setItem("qm-theme",l?"light":"");});
loadOverview();loadPaperData();loadQuotes();loadSignals();
setInterval(()=>{if(view==="markets")loadQuotes();else if(view==="overview")loadOverview();},20000);
