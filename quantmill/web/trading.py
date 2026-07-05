# -*- coding: utf-8 -*-
"""
trading.py —— 纸面账户 / 组合 / 总览 / 导出 / 自选股
trading.py —— paper / portfolio backtest / overview / export / watchlist blueprint
=====================================================================
路由:/api/paper /api/rebalance /api/overview /api/backtest /api/export /api/watchlist。
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter

from flask import Blueprint, Response, jsonify, request

from quantmill import config
from quantmill.watchlist import load_watchlist
from quantmill.web.market import _get_quotes, _get_signals
from quantmill.web.state import _BCACHE, _CCACHE, _QCACHE, _SCACHE, _SPROG
from quantmill.web.util import get_market

bp = Blueprint("trading", __name__)


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


def _paper_rebalance(market, method="topk", k=None):
    import pandas as pd
    from quantmill.execution.broker import PaperBroker
    from quantmill.portfolio.optimizer import ALLOCATORS
    from quantmill.portfolio.rules import market_rules
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


def _get_overview():
    """三市场概况(行情用缓存,信号用已算好的)+ 纸面账户。| Cross-market overview."""
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


@bp.route("/api/paper")
def api_paper():
    return jsonify(_get_paper())


@bp.route("/api/rebalance")
def api_rebalance():
    return jsonify(_paper_rebalance(get_market(),
                                    request.args.get("method", "topk")))


@bp.route("/api/overview")
def api_overview():
    return jsonify(_get_overview())


@bp.route("/api/backtest")
def api_backtest():
    m = get_market()
    if request.args.get("refresh"):
        _BCACHE.pop((m, request.args.get("method", "topk")), None)
    return jsonify(_get_backtest(m, request.args.get("method", "topk")))


@bp.route("/api/export")
def api_export():
    m = get_market()
    return Response(_build_snapshot(m), mimetype="text/html", headers={
        "Content-Disposition": f'attachment; filename="quantmill_snapshot_{m}.html"'})


@bp.route("/api/watchlist", methods=["GET", "POST"])
def api_watchlist():
    m = get_market()
    if request.method == "POST":                   # 增删走 POST(带副作用),GET 只读
        return jsonify({"symbols": _edit_watchlist(
            m, request.form.get("add"), request.form.get("remove"))})
    return jsonify({"symbols": load_watchlist().get(m, [])})
