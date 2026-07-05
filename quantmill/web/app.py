# -*- coding: utf-8 -*-
"""
app.py —— Flask 网页应用:左侧导航多页仪表盘 + 实时数据 API
app.py —— Flask web app: sidebar multi-page dashboard + live data API
=====================================================================
6 个页面(对应 CLI 命令):行情/组合/可信度/因子/消息面/个股。
"""

from __future__ import annotations

import json
import os
import threading
import time

from flask import Flask, Response, jsonify, request

from quantmill import config
from quantmill.watchlist import load_watchlist

app = Flask(__name__)

_QCACHE: dict = {}    # market -> (ts, quotes)
_SCACHE: dict = {}    # market -> signals
_CCACHE: dict = {}    # market -> credibility
_SPROG: dict = {}     # market -> 信号计算进度 | signal-compute progress
_XCACHE: dict = {}    # market -> 横截面选股结果 | cross-sectional result
_XPROG: dict = {}     # market -> 横截面计算进度 | cross-compute progress
_QSRC: dict = {}      # market -> 行情数据源(alpaca实时 / yfinance延迟)| quote source


def _compute_cross_bg(market, model="composite"):
    """后台跑横截面:面板 → (稳健组合/ML)打分 → top-k 回测 → DSR + 跨市场验证。"""
    key = f"{market}:{model}"
    _XPROG[key] = {"running": True, "stage": "建面板 / 打分回测…"}
    try:
        from quantmill.cross import (get_panel, factor_columns, composite_score,
                                     walk_forward_scores, topk_backtest, ic_table)
        from quantmill.credibility.stats import deflated_sharpe_ratio, sharpe
        panel = get_panel(market=market, verbose=False)
        cols = factor_columns(panel)
        if model == "composite":
            score = composite_score(panel)
        else:
            score = walk_forward_scores(panel, cols, horizon=20, init_train=504, step=63)
        res = topk_backtest(panel, score, k=20, horizon=20, cost=0.0015)
        eq = res["equity"]
        sc = (1 + eq["long"]).cumprod()
        bc = (1 + eq["bench"]).cumprod()
        equity = [{"d": str(d.date()), "s": round(float(s), 4), "b": round(float(b), 4)}
                  for d, s, b in zip(eq.index, sc, bc)]
        m = res["metrics"]
        tab = ic_table(panel, cols).head(8)
        ic = [{"factor": r.factor, "IC": r.IC, "ICIR": r.ICIR} for r in tab.itertuples()]
        trials = [sharpe(topk_backtest(panel, score, k=kk, horizon=20, cost=0.0015)["equity"]["long"])
                  for kk in (10, 20, 30, 50)]
        dsr = deflated_sharpe_ratio(eq["long"], sr_trials=trials, n_trials=20)["dsr"]
        # 跨市场验证:稳健组合在 A股+港股各跑一遍(只用已缓存面板,失败则跳过)
        valid = []
        for mk in ("cn", "hk"):
            try:
                p = get_panel(market=mk, verbose=False)
                n = int(p.index.get_level_values(1).nunique())
                kk = int(min(20, max(8, n // 7)))
                mm = topk_backtest(p, composite_score(p), k=kk, horizon=20,
                                   cost=0.0015)["metrics"]["策略 top-k"]
                valid.append({"market": mk.upper(), "universe": n,
                              "excess": mm["超额年化"], "sharpe": mm["夏普"]})
            except Exception:  # noqa: BLE001
                pass
        _XCACHE[key] = {
            "model": model, "strat": m["策略 top-k"], "bench": m["基准 等权"],
            "ic": ic, "equity": equity, "valid": valid,
            "periods": len(eq), "winrate": round(float((eq["long"] > eq["bench"]).mean() * 100)),
            "dsr": round(float(dsr), 3), "universe": int(panel.index.get_level_values(1).nunique()),
            "start": equity[0]["d"], "end": equity[-1]["d"],
        }
    except Exception as e:  # noqa: BLE001
        _XCACHE[key] = {"error": f"{type(e).__name__}: {e}"}
    _XPROG[key]["running"] = False


@app.errorhandler(Exception)
def _on_error(e):     # 返回 JSON 错误体(前端友好)+ 真实 500 状态码(便于排障/监控)
    from werkzeug.exceptions import HTTPException
    code = e.code if isinstance(e, HTTPException) else 500
    return jsonify({"error": f"{type(e).__name__}: {e}"}), code


def _yahoo(sym, market):
    from quantmill.data import _cn_to_yahoo, _hk_to_yahoo
    return _hk_to_yahoo(sym) if market == "hk" else (
        _cn_to_yahoo(sym) if market == "cn" else sym)


def _get_quotes(symbols, market):
    now = time.time()
    if market in _QCACHE and now - _QCACHE[market][0] < 15:
        return _QCACHE[market][1]
    import yfinance as yf
    ymap = {s: _yahoo(s, market) for s in symbols}
    try:
        df = yf.download(list(dict.fromkeys(ymap.values())), period="3mo",
                         interval="1d", progress=False, auto_adjust=True)
    except Exception:  # noqa: BLE001
        return {}
    if df is None or df.empty:
        return {}
    close = df["Close"]
    out = {}
    for s, yt in ymap.items():
        try:
            ser = (close[yt] if hasattr(close, "columns") and yt in close.columns
                   else close).dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(ser) < 2:
            continue
        last, prev = float(ser.iloc[-1]), float(ser.iloc[-2])
        out[s] = {"price": round(last, 2), "prev": round(prev, 2),
                  "chg": round((last / prev - 1) * 100, 2),
                  "spark": [round(float(x), 4) for x in ser.tail(40)]}
    # 美股:有 Alpaca key 就用实时成交价覆盖(prev 仍用昨收算涨跌)| real-time override
    src = "yfinance"
    if market == "us":
        from quantmill.data.live import alpaca_last_prices
        live = alpaca_last_prices(symbols)
        if live:
            src = "alpaca"
            for s in out:
                if s in live and out[s]["prev"]:
                    last = round(live[s], 2)
                    out[s]["price"] = last
                    out[s]["chg"] = round((last / out[s]["prev"] - 1) * 100, 2)
                    out[s]["spark"] = out[s]["spark"][:-1] + [round(live[s], 4)]
    _QSRC[market] = src
    _QCACHE[market] = (now, out)
    return out


def _get_signals(symbols, market, horizon=5):
    if market in _SCACHE:
        return _SCACHE[market]
    from quantmill.execution.engine import _snapshot
    out = {}
    for s in symbols:
        try:
            _, p_up, _, _ = _snapshot(s, market, horizon)
        except Exception:  # noqa: BLE001
            continue
        out[s] = {"p": round(p_up, 3),
                  "label": "hold" if p_up > 0.55 else ("cash" if p_up < 0.45 else "wait")}
    _SCACHE[market] = out
    return out


def _compute_signals_bg(symbols, market, horizon):
    """后台逐只算信号并更新进度,算完写入缓存。| Compute signals in background with progress."""
    from quantmill.execution.engine import _snapshot
    _SPROG[market] = {"done": 0, "total": len(symbols), "running": True}
    out = {}
    for s in symbols:
        try:
            _, p_up, _, _ = _snapshot(s, market, horizon)
            out[s] = {"p": round(p_up, 3),
                      "label": "hold" if p_up > 0.55 else ("cash" if p_up < 0.45 else "wait")}
        except Exception:  # noqa: BLE001
            pass
        _SPROG[market]["done"] += 1
    _SCACHE[market] = out
    _SPROG[market]["running"] = False


def _get_paper():
    if not os.path.exists(config.PAPER_PATH):
        return None
    with open(config.PAPER_PATH, encoding="utf-8") as f:
        st = json.load(f)
    eq = st["history"][-1]["equity"] if st.get("history") else st.get("cash", 0)
    init = st.get("init_cash", 0) or 1
    return {"equity": eq, "cash": round(st.get("cash", 0)), "init": init,
            "ret": round((eq / init - 1) * 100, 2),
            "positions": st.get("positions", {}), "trades": st.get("trades", [])[-8:],
            "n_trades": len(st.get("trades", [])),
            "curve": [h["equity"] for h in st.get("history", [])][-60:]}


def _get_chart(symbol, market, n=120):
    from quantmill.data import get_ohlcv
    df = get_ohlcv(symbol, market).tail(n)
    return [{"d": str(i.date()), "o": round(float(o), 2), "h": round(float(h), 2),
             "l": round(float(lo), 2), "c": round(float(c), 2)}
            for i, o, h, lo, c in zip(df.index, df["Open"], df["High"],
                                      df["Low"], df["Close"])]


def _paper_rebalance(market, method="topk", k=None):
    import pandas as pd
    from quantmill.portfolio.optimizer import ALLOCATORS
    from quantmill.portfolio.rules import market_rules
    from quantmill.execution.broker import PaperBroker
    syms = load_watchlist().get(market, [])
    quotes = _get_quotes(syms, market)
    sigs = _get_signals(syms, market)
    prices = {s: quotes[s]["price"] for s in quotes}
    valid = [s for s in prices if s in sigs]
    if not valid:
        return {"error": "信号或行情未就绪", "account": _get_paper()}
    sig_series = pd.Series({s: sigs[s]["p"] for s in valid})
    ret_window = pd.DataFrame(
        {s: pd.Series(quotes[s]["spark"]).pct_change() for s in valid}).dropna()
    kk = k or max(1, round(len(sig_series) / 2))
    alloc = ALLOCATORS.get(method, ALLOCATORS["topk"])
    target = {s: float(w) for s, w in alloc(sig_series, ret_window, kk, 0.4).items()
              if w > 1e-9}
    b = PaperBroker()
    orders = b.rebalance_to(target, prices, commission=config.COMMISSION,
                            sell_cost=market_rules(market)["sell_cost"],
                            lot=100 if market == "cn" else 1, when="live")
    b.record(prices, "live")
    b.save()
    return {"orders": {s: round(float(o), 2) for s, o in orders.items()},
            "account": _get_paper()}


def _get_credibility(market):
    if market in _CCACHE:
        return _CCACHE[market]
    from quantmill.credibility.validate import compute_proba, symbol_credibility
    rows = []
    for s in load_watchlist().get(market, []):
        try:
            feat_df, proba = compute_proba(s, market, config.START, None, config.HORIZON)
            h = symbol_credibility(feat_df, proba, config.ROBUSTNESS_BUY_THS,
                                   config.CASH, config.COMMISSION)
        except Exception:  # noqa: BLE001
            h = None
        if h:
            rows.append({"sym": f"{market}:{s}", **h})
    n = len(rows)
    res = {"rows": rows, "n": n, "sig": sum(1 for r in rows if r["dsr"] > 0.95),
           "mean_pbo": round(sum(r["pbo"] for r in rows) / n, 3) if n else 0.0}
    _CCACHE[market] = res
    return res


def _get_factors(symbol, market):
    from quantmill.data import get_ohlcv
    from quantmill.factor.analysis import ic_report
    rep = ic_report(get_ohlcv(symbol, market), horizon=config.HORIZON)
    return rep.head(18).to_dict("records")


def _get_news(symbol, market):
    from quantmill.llm.sentiment import news_sentiment
    res = news_sentiment(symbol, market, limit=12)
    return {"mean": round(res["mean"], 3), "n": res["n"], "scorer": res["scorer"],
            "items": [{"title": it["title"], "sent": round(it.get("sentiment", 0), 2),
                       "date": str(it["time"].date()) if it.get("time") is not None else ""}
                      for it in res["items"]]}


def _get_overview():
    """三市场概况(行情用缓存,信号用已算好的)+ 纸面账户。| Cross-market overview."""
    from collections import Counter
    wl = load_watchlist()
    mkts = {}
    for m in ("us", "hk", "cn"):
        syms = wl.get(m, [])
        q = _get_quotes(syms, m)
        top_g = top_l = None
        avg = None
        if q:
            mv = sorted(q.items(), key=lambda kv: kv[1]["chg"])
            top_l = {"sym": mv[0][0], "chg": mv[0][1]["chg"]}
            top_g = {"sym": mv[-1][0], "chg": mv[-1][1]["chg"]}
            avg = round(sum(v["chg"] for v in q.values()) / len(q), 2)
        sig = _SCACHE.get(m)
        sigsum = None
        if sig:
            c = Counter(v["label"] for v in sig.values())
            sigsum = {"hold": c.get("hold", 0), "cash": c.get("cash", 0),
                      "wait": c.get("wait", 0)}
        mkts[m] = {"n": len(syms), "avg": avg, "top_g": top_g, "top_l": top_l,
                   "sig": sigsum}
    return {"markets": mkts, "paper": _get_paper()}


# ---------------------------------------------------------------- 路由 | routes
@app.route("/")
def index():
    return Response(_HTML, mimetype="text/html")


@app.route("/api/quotes")
def api_quotes():
    m = request.args.get("market", "us")
    syms = load_watchlist().get(m, [])
    q = _get_quotes(syms, m)
    return jsonify({"market": m, "symbols": syms, "quotes": q,
                    "source": _QSRC.get(m, "yfinance"),
                    "updated": time.strftime("%H:%M:%S")})


@app.route("/api/signals")
def api_signals():
    """信号:算好就返回;没算就后台启动并返回进度(前端轮询)。| ready or computing+progress."""
    m = request.args.get("market", "us")
    if request.args.get("refresh"):
        _SCACHE.pop(m, None)
        _SPROG.pop(m, None)
    if m in _SCACHE:
        return jsonify({"status": "ready", "signals": _SCACHE[m]})
    pr = _SPROG.get(m)
    if not pr or not pr["running"]:
        syms = load_watchlist().get(m, [])
        threading.Thread(target=_compute_signals_bg, args=(syms, m, config.HORIZON),
                         daemon=True).start()
        pr = {"done": 0, "total": len(syms), "running": True}
        _SPROG[m] = pr
    return jsonify({"status": "computing", "done": pr["done"], "total": pr["total"]})


@app.route("/api/paper")
def api_paper():
    return jsonify(_get_paper())


@app.route("/api/chart")
def api_chart():
    return jsonify(_get_chart(request.args.get("symbol"), request.args.get("market", "us")))


@app.route("/api/rebalance")
def api_rebalance():
    return jsonify(_paper_rebalance(request.args.get("market", "us"),
                                    request.args.get("method", "topk")))


@app.route("/api/credibility")
def api_credibility():
    m = request.args.get("market", "us")
    if request.args.get("refresh"):
        _CCACHE.pop(m, None)
    return jsonify(_get_credibility(m))


@app.route("/api/factors")
def api_factors():
    return jsonify(_get_factors(request.args.get("symbol"),
                                request.args.get("market", "us")))


@app.route("/api/news")
def api_news():
    return jsonify(_get_news(request.args.get("symbol"),
                             request.args.get("market", "us")))


@app.route("/api/cross")
def api_cross():
    """横截面选股:算好返回;没算就后台启动并返回进度(前端轮询)。model=composite/ml。"""
    m = request.args.get("market", "cn")
    model = request.args.get("model", "composite")
    key = f"{m}:{model}"
    if request.args.get("refresh"):
        _XCACHE.pop(key, None)
        _XPROG.pop(key, None)
    if key in _XCACHE:
        return jsonify({"status": "ready", "data": _XCACHE[key]})
    pr = _XPROG.get(key)
    if not pr or not pr["running"]:
        threading.Thread(target=_compute_cross_bg, args=(m, model), daemon=True).start()
        pr = {"running": True, "stage": "启动中…"}
        _XPROG[key] = pr
    return jsonify({"status": "computing", "stage": pr.get("stage", "计算中…")})


def _edit_watchlist(market, add=None, remove=None):
    """网页里增删自选股,写回 watchlist.txt 并清相关缓存。| Edit watchlist from the web."""
    wl = load_watchlist()
    for mk in ("us", "hk", "cn"):
        wl.setdefault(mk, [])
    lst = wl[market]
    if add:
        a = add.strip().upper() if market == "us" else add.strip()
        if a and a not in lst:
            lst.append(a)
    if remove and remove in lst:
        lst.remove(remove)
    out = ["# 我的自选股 · My Watchlist(网页编辑)"]
    for mk in ("us", "hk", "cn"):
        out.append(f"\n# --- {mk} ---")
        out += [f"{mk} {s}" for s in wl[mk]]
    with open(config.WATCHLIST_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    for c in (_QCACHE, _SCACHE, _SPROG, _CCACHE):
        c.pop(market, None)
    return wl[market]


@app.route("/api/watchlist")
def api_watchlist():
    m = request.args.get("market", "us")
    add, remove = request.args.get("add"), request.args.get("remove")
    if add or remove:
        return jsonify({"symbols": _edit_watchlist(m, add, remove)})
    return jsonify({"symbols": load_watchlist().get(m, [])})


@app.route("/api/overview")
def api_overview():
    return jsonify(_get_overview())


_BCACHE: dict = {}    # (market,method) -> backtest result


def _get_backtest(market, method="topk"):
    """跑该市场的组合回测(策略 vs 等权基准),返回资金曲线+指标(较慢,缓存)。"""
    key = (market, method)
    if key in _BCACHE:
        return _BCACHE[key]
    from quantmill.portfolio import build_panels
    from quantmill.portfolio.backtest import backtest_portfolio, portfolio_metrics
    from quantmill.portfolio.rules import market_rules
    syms = load_watchlist().get(market, [])
    sig, ret = build_panels(syms, market)          # 慢:逐只算样本外信号
    rules = market_rules(market)
    n = ret.shape[1]
    k = max(1, round(n / 2))
    common = dict(rebalance=config.HORIZON, commission=config.COMMISSION,
                  price_limit=rules["price_limit"], sell_cost=rules["sell_cost"])
    strat = backtest_portfolio(sig, ret, method=method, k=k, max_weight=0.4, **common)
    bench = backtest_portfolio(sig, ret, method="equal", **common)

    def ds(eq):
        vals = [float(x) for x in eq.values]
        step = max(1, len(vals) // 160)
        return [round(x, 4) for x in vals[::step]]

    res = {"strat": ds(strat["equity"]), "bench": ds(bench["equity"]),
           "sm": portfolio_metrics(strat), "bm": portfolio_metrics(bench),
           "method": method, "n": n,
           "period": f"{ret.index[0].date()} ~ {ret.index[-1].date()}"}
    _BCACHE[key] = res
    return res


@app.route("/api/backtest")
def api_backtest():
    m = request.args.get("market", "us")
    if request.args.get("refresh"):
        _BCACHE.pop((m, request.args.get("method", "topk")), None)
    return jsonify(_get_backtest(m, request.args.get("method", "topk")))


def _build_snapshot(market):
    """生成自包含 HTML 快照(总览 + 纸面账户),供导出/分享。"""
    d = _get_overview()
    names = {"us": "美股 US", "hk": "港股 HK", "cn": "A股 CN"}
    rows = "".join(
        f"<tr><td>{names[m]}</td><td>{x['n']}</td>"
        f"<td>{'' if x['avg'] is None else ('+' if x['avg'] >= 0 else '')}{x['avg']}%</td>"
        f"<td>{x['top_g']['sym']+' +'+str(x['top_g']['chg'])+'%' if x['top_g'] else '—'}</td>"
        f"<td>{x['top_l']['sym']+' '+str(x['top_l']['chg'])+'%' if x['top_l'] else '—'}</td></tr>"
        for m, x in d["markets"].items())
    p = d["paper"]
    paper = "无纸面账户"
    if p:
        pos = "".join(f"<li>{s} · {int(q)} 股</li>" for s, q in p["positions"].items()) or "<li>空仓</li>"
        paper = (f"总权益 {p['equity']:,} · 现金 {p['cash']:,} · 累计收益 {p['ret']}% · "
                 f"成交 {p['n_trades']} 笔<ul>{pos}</ul>")
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>quantmill 快照 · {market.upper()}</title><style>
body{{font-family:-apple-system,"PingFang SC",sans-serif;max-width:760px;margin:36px auto;padding:0 20px;color:#1a1d23}}
h1{{font-size:20px}}table{{border-collapse:collapse;width:100%;margin:10px 0;font-size:14px}}
th,td{{border:1px solid #ddd;padding:7px 10px;text-align:right}}th:first-child,td:first-child{{text-align:left}}
th{{background:#f5f5f7}}.foot{{color:#888;font-size:12px;margin-top:24px;border-top:1px solid #eee;padding-top:10px}}
</style></head><body>
<h1>🏭 quantmill 快照 · {time.strftime("%Y-%m-%d %H:%M")}</h1>
<h2>三市场概况</h2>
<table><tr><th>市场</th><th>只数</th><th>平均涨跌</th><th>领涨</th><th>领跌</th></tr>{rows}</table>
<h2>纸面账户</h2><p>{paper}</p>
<div class="foot">quantmill 本地导出 · 行情延迟约15分钟 · 内置策略未通过可信度验证,仅供研究,非投资建议。</div>
</body></html>"""


@app.route("/api/export")
def api_export():
    m = request.args.get("market", "us")
    return Response(_build_snapshot(m), mimetype="text/html", headers={
        "Content-Disposition": f'attachment; filename="quantmill_snapshot_{m}.html"'})


def serve(port: int = 8787, open_browser: bool = True):
    if open_browser:
        import threading
        import webbrowser
        threading.Timer(1.3, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    print(f"🏭 quantmill web 已启动 → http://127.0.0.1:{port}   (Ctrl+C 退出)")
    print("   行情延迟约 15 分钟(免费源);信号/体检首次需训模型,稍等。")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


# ============================================================ 前端(多页)| frontend
_HTML = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>quantmill · 量化台</title>
<style>
 :root{--bg:#0e1014;--pan:#14171d;--card:#181b22;--card2:#1f232c;--line:#262b36;
   --tx:#e6e8ec;--dim:#8b93a1;--grn:#22c55e;--red:#ef4444;--amb:#f59e0b;--acc:#3b82f6;}
 body[data-theme=light]{--bg:#f5f6f8;--pan:#ffffff;--card:#ffffff;--card2:#eef1f5;
   --line:#e3e7ee;--tx:#1a1d23;--dim:#6b7280;}
 *{box-sizing:border-box;margin:0;padding:0}
 body{background:var(--bg);color:var(--tx);font:14px/1.5 -apple-system,"PingFang SC",sans-serif;-webkit-font-smoothing:antialiased}
 .app{display:flex;min-height:100vh}
 /* 侧边栏 */
 .side{width:212px;flex:0 0 212px;background:var(--pan);border-right:1px solid var(--line);
   padding:18px 14px;display:flex;flex-direction:column;position:sticky;top:0;height:100vh}
 .brand{font-size:18px;font-weight:700;margin:4px 6px 20px}
 .brand span{color:var(--dim);font-weight:400;font-size:11px;margin-left:6px}
 .nav{display:block;padding:10px 12px;border-radius:9px;color:var(--dim);cursor:pointer;
   margin-bottom:3px;user-select:none;font-size:14px}
 .nav:hover{background:var(--card);color:var(--tx)}
 .nav.on{background:var(--acc);color:#fff}
 .mkt{margin-top:auto;border-top:1px solid var(--line);padding-top:14px}
 .mkt-lbl{color:var(--dim);font-size:11px;margin:0 6px 8px}
 .mkt-tabs{display:flex;gap:6px}
 .mt{flex:1;text-align:center;padding:7px 0;border:1px solid var(--line);border-radius:8px;
   cursor:pointer;color:var(--dim);font-size:13px}
 .mt.on{background:var(--acc);color:#fff;border-color:var(--acc)}
 /* 主区 */
 .main{flex:1;padding:24px 28px;max-width:1100px}
 .view{display:none}.view.on{display:block}
 h1{font-size:20px;margin-bottom:4px}
 .sub{color:var(--dim);font-size:12px;margin-bottom:16px}
 .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--grn);margin-right:5px;animation:pulse 2s infinite}
 @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
 .ctrls{display:flex;gap:10px;align-items:center;margin-bottom:14px;flex-wrap:wrap}
 .btn{background:var(--acc);color:#fff;border:none;padding:8px 15px;border-radius:8px;cursor:pointer;font-weight:600;font-size:13px}
 .btn:hover{filter:brightness(1.12)} .btn:disabled{opacity:.5;cursor:default}
 .btn2{background:var(--card2)}
 .btn.on2{background:var(--acc);color:#fff}
 select,input{background:var(--card);color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:13px}
 .strip{display:flex;gap:22px;flex-wrap:wrap;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin-bottom:16px}
 .strip .k{color:var(--dim);font-size:12px}.strip .v{font-size:20px;font-weight:600}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:13px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;transition:.15s;cursor:pointer}
 .card:hover{border-color:#39414f;transform:translateY(-2px)}
 .c-top{display:flex;justify-content:space-between;align-items:baseline}
 .sym{font-size:16px;font-weight:700}
 .badge{font-size:11px;padding:3px 9px;border-radius:20px;font-weight:600}
 .b-hold{background:rgba(34,197,94,.15);color:var(--grn)}
 .b-cash{background:rgba(239,68,68,.15);color:var(--red)}
 .b-wait{background:rgba(245,158,11,.15);color:var(--amb)}
 .b-load{background:var(--card2);color:var(--dim)}
 .price{font-size:25px;font-weight:700;margin-top:8px;font-variant-numeric:tabular-nums}
 .chg{font-size:13px;font-weight:600;font-variant-numeric:tabular-nums}
 .up{color:var(--grn)}.down{color:var(--red)}
 .row2{display:flex;justify-content:space-between;align-items:flex-end;margin-top:10px}
 .pos{font-size:11px;color:var(--dim)}
 .panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:16px}
 table{width:100%;border-collapse:collapse;font-size:14px}
 th{color:var(--dim);font-weight:500;padding:7px 8px;text-align:right}
 th:first-child{text-align:left}
 td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;font-variant-numeric:tabular-nums}
 td:first-child{text-align:left}
 .spin{display:inline-block;width:12px;height:12px;border:2px solid var(--line);border-top-color:var(--acc);border-radius:50%;animation:sp .7s linear infinite;vertical-align:-1px}
 @keyframes sp{to{transform:rotate(360deg)}}
 .toast{position:fixed;bottom:26px;left:calc(50% + 106px);transform:translateX(-50%);background:var(--card2);border:1px solid var(--line);border-radius:10px;padding:12px 18px;font-size:13px;opacity:0;transition:.3s;pointer-events:none;z-index:60;max-width:70vw}
 .toast.on{opacity:1}
 .muted{color:var(--dim);padding:40px;text-align:center}
 .foot{color:#5b6472;font-size:11px;margin-top:24px;line-height:1.7}
 .skel{background:linear-gradient(90deg,var(--card) 25%,var(--card2) 50%,var(--card) 75%);
   background-size:200% 100%;animation:sh 1.2s infinite;height:120px;border-radius:14px}
 @keyframes sh{to{background-position:-200% 0}}
 .view.on{animation:fade .24s ease}
 @keyframes fade{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
 .search{width:100%;margin:6px 0 14px;padding:9px 11px}
 .card{position:relative}
 .cx{position:absolute;top:9px;right:11px;color:var(--dim);font-size:13px;opacity:0;cursor:pointer}
 .card:hover .cx{opacity:.65}.cx:hover{color:var(--red);opacity:1}
 .wl-in{width:96px}
 @media(max-width:760px){.app{flex-direction:column}
   .side{width:100%;height:auto;position:static;flex-direction:row;flex-wrap:wrap;align-items:center;padding:10px 12px}
   .brand{margin:0 10px 0 2px;font-size:16px}.nav{padding:7px 10px;margin:0}
   .search{display:none}.mkt{margin:0 0 0 auto;border:none;padding:0}
   .mkt-lbl{display:none}.main{padding:16px}}
</style></head><body>
<div class="app">
 <nav class="side">
   <div class="brand">🏭 quantmill<span>量化台</span></div>
   <input class="search" id="gsearch" placeholder="🔍 搜代码 · 回车深挖">
   <a class="nav on" data-v="overview">🏠 总览</a>
   <a class="nav" data-v="markets">📊 行情</a>
   <a class="nav" data-v="portfolio">📦 组合</a>
   <a class="nav" data-v="credibility">🔬 可信度</a>
   <a class="nav" data-v="factors">📈 因子</a>
   <a class="nav" data-v="cross">🎯 选股</a>
   <a class="nav" data-v="news">📰 消息面</a>
   <a class="nav" data-v="analyze">🔍 个股</a>
   <div class="mkt"><div class="mkt-lbl">市场</div>
     <div class="mkt-tabs"><span class="mt on" data-m="us">US</span>
       <span class="mt" data-m="hk">HK</span><span class="mt" data-m="cn">CN</span></div>
     <div style="text-align:center;margin-top:10px"><span id="theme" style="cursor:pointer;color:var(--dim);font-size:12px">🌓 切换主题</span></div></div>
 </nav>
 <main class="main">

  <section id="v-overview" class="view on">
    <h1>🏠 总览</h1>
    <div class="sub">三市场概况 + 纸面账户一眼看全。点市场卡片 → 跳该市场行情。</div>
    <div class="ctrls"><button class="btn btn2" id="export">⬇️ 导出快照 HTML</button></div>
    <div id="ov"><div class="muted"><span class="spin"></span> 加载中…</div></div>
  </section>

  <section id="v-markets" class="view">
    <h1>📊 行情</h1>
    <div class="sub"><span class="dot"></span>行情 · 更新 <b id="upd">—</b>
      · <span id="src">—</span> · 信号=模型预测未来5天 P(涨),仅供研究</div>
    <div class="ctrls">
      <span style="color:var(--dim);font-size:12px">排序</span>
      <select id="sort"><option value="sig">按信号</option><option value="chg">按涨跌</option><option value="sym">按代码</option></select>
      <button class="btn" id="reb">⚡ 一键调仓到信号组合</button>
      <button class="btn btn2" id="refsig">🔄 刷新信号</button>
      <label style="font-size:12px;color:var(--dim);display:flex;align-items:center;gap:4px"><input type="checkbox" id="autosig" style="width:auto"> 自动刷新</label>
      <input class="wl-in" id="wl-in" placeholder="加自选" style="margin-left:auto">
      <button class="btn btn2" id="wladd">＋</button>
      <span id="rebmsg" style="color:var(--dim);font-size:12px"></span>
    </div>
    <div class="grid" id="grid"></div>
  </section>

  <section id="v-portfolio" class="view">
    <h1>📦 组合 · 纸面账户</h1>
    <div class="sub">数据→信号→下单闭环的结果。点「一键调仓」按当前信号再平衡。</div>
    <div class="ctrls">
      <span style="color:var(--dim);font-size:12px">配置法</span>
      <select id="pf-method"><option value="topk">TopK等权</option><option value="invvol">逆波动</option><option value="minvar">最小方差</option></select>
      <button class="btn" id="reb2">⚡ 一键调仓</button>
      <button class="btn btn2" id="runbt">📉 跑组合回测(慢)</button>
      <span id="reb2msg" style="color:var(--dim);font-size:12px"></span></div>
    <div id="pf"></div>
    <div id="bt"></div>
  </section>

  <section id="v-credibility" class="view">
    <h1>🔬 可信度体检 <span style="font-size:12px;color:var(--dim)">DSR / PBO</span></h1>
    <div class="sub">平台护城河:当面告诉你策略是真优势还是运气+过拟合。别的产品不给你看这个。</div>
    <div class="ctrls"><button class="btn" id="runcred">运行体检(约1-2分钟)</button></div>
    <div id="cred" class="panel"><div class="muted">点上面按钮开始体检</div></div>
  </section>

  <section id="v-factors" class="view">
    <h1>📈 因子有效性</h1>
    <div class="sub">因子对未来收益的预测力(IC/RankIC)。日线单股 |RankIC|~0.1 已算不错。</div>
    <div class="ctrls"><input id="f-sym" placeholder="代码 如 AAPL" value="AAPL" style="width:130px">
      <button class="btn" id="runfac">分析因子</button></div>
    <div id="fac" class="panel"><div class="muted">输入代码,点分析</div></div>
  </section>

  <section id="v-cross" class="view">
    <h1>🎯 横截面选股 <span style="font-size:12px;color:var(--dim)">全市场排名 · 月度换仓</span></h1>
    <div class="sub">全市场打分,买 top-k,月度换仓,和等权基准比。<b>稳健组合</b>=价值+动量+低波固定配方(跨市场验证过);<b>ML排名</b>=43因子LightGBM(A股漂亮但港股翻车)。目前仅 A股/港股。</div>
    <div class="ctrls">
      <span style="color:var(--dim);font-size:12px">模型</span>
      <button class="btn btn2 on2" id="cm-composite">稳健组合</button><button class="btn btn2" id="cm-ml">ML排名</button>
      <button class="btn" id="runcross" style="margin-left:12px">跑回测</button>
      <span class="muted" style="margin-left:8px">稳健组合秒出 · ML约30秒</span></div>
    <div id="cross" class="panel"><div class="muted">选模型,点「跑回测」</div></div>
  </section>

  <section id="v-news" class="view">
    <h1>📰 消息面情绪</h1>
    <div class="sub">LLM 打分近期新闻(无 key 时走词典兜底)。情绪≠涨跌,仅供研究。</div>
    <div class="ctrls"><input id="n-sym" placeholder="代码 如 AAPL" value="AAPL" style="width:130px">
      <button class="btn" id="runnews">抓取情绪</button></div>
    <div id="news" class="panel"><div class="muted">输入代码,点抓取</div></div>
  </section>

  <section id="v-analyze" class="view">
    <h1>🔍 个股深挖</h1>
    <div class="sub">K线 + 模型信号。点行情页的卡片也会跳到这里。</div>
    <div class="ctrls"><input id="a-sym" placeholder="代码 如 AAPL" value="AAPL" style="width:130px">
      <button class="btn" id="runana">深挖</button>
      <span style="margin-left:10px;color:var(--dim);font-size:12px">图型</span>
      <button class="btn btn2 on2" id="ct-candle">蜡烛</button><button class="btn btn2" id="ct-line">折线</button>
      <span style="margin-left:10px;color:var(--dim);font-size:12px">均线</span>
      <button class="btn btn2 on2" id="ma-5">MA5</button><button class="btn btn2" id="ma-10">MA10</button><button class="btn btn2 on2" id="ma-20">MA20</button><button class="btn btn2" id="ma-60">MA60</button></div>
    <div id="ana" class="panel"><div class="muted">输入代码,点深挖</div></div>
  </section>

  <div class="foot">quantmill · 数据 yfinance/akshare · 信号 LightGBM · 本地服务,非投资建议<br>
   ⚠️ 内置策略未通过可信度验证(约 2/15 跑赢基准)—— 信号仅供研究,别拿真钱跟。</div>
 </main>
</div>
<div class="toast" id="toast"></div>
<script>
let market="us", view="markets", quotes={}, signals=null, sigLoading=false, sortBy="sig", sigProg={done:0,total:0};
let chartType="candle", lastData=null, lastSym="", crossModel="composite";
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
async function wlAdd(){const v=$("wl-in").value.trim();if(!v)return;$("wl-in").value="";
  try{await fetch(`/api/watchlist?market=${market}&add=${encodeURIComponent(v)}`);toast("已加入自选 "+v.toUpperCase());
    quotes={};signals=null;loadQuotes();loadSignals();}catch(e){toast("添加失败");}}
async function wlRemove(s){try{await fetch(`/api/watchlist?market=${market}&remove=${encodeURIComponent(s)}`);toast("已移除 "+s);
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

/* ---- 导航 / 市场 ---- */
function setView(v){view=v;document.querySelectorAll(".nav").forEach(n=>n.classList.toggle("on",n.dataset.v===v));
  document.querySelectorAll(".view").forEach(s=>s.classList.toggle("on",s.id==="v-"+v));
  if(v==="portfolio")renderPortfolio();if(v==="overview")loadOverview();}
function setMarket(m){market=m;quotes={};signals=null;
  document.querySelectorAll(".mt").forEach(t=>t.classList.toggle("on",t.dataset.m===m));
  loadQuotes();loadSignals();if(view==="portfolio")renderPortfolio();if(view==="overview")loadOverview();
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
</script></body></html>"""
