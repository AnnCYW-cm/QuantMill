# -*- coding: utf-8 -*-
"""
engine.py —— 纸面交易闭环引擎 | Paper-trading loop engine
==========================================================
一次 run = 一步:抓最新真实价 + 算最新信号 → 目标权重 → 下单成交 → 记录权益。
天然无未来函数:只用"截止今天"的信息,和真实交易一样。

  paper_run     跑一步(再平衡到目标)| advance one step
  paper_status  看账户 | show account
  paper_reset   重置账户 | reset account
"""

from __future__ import annotations

import os

import pandas as pd

from quantmill import config
from quantmill.execution.broker import PaperBroker


def _snapshot(symbol: str, market: str, horizon: int):
    """一只票的:最新价、最新信号 P(涨)、近60日收益、数据截止日。
    Latest price, latest P(up) signal, recent returns, and as-of date for one stock."""
    from quantmill.data import get_ohlcv
    from quantmill.factor import build_dataset, make_features, FEATURE_COLS
    from quantmill.model import train_full

    df = get_ohlcv(symbol, market)
    price = float(df["Close"].iloc[-1])
    X, y, _ = build_dataset(df, horizon=horizon)
    model = train_full(X, y)
    live = make_features(df)[FEATURE_COLS].dropna()
    p_up = float(model.predict_proba(live.iloc[-1:])[0, 1])
    rets = df["Close"].pct_change()
    return price, p_up, rets, df.index[-1].date()


def _make_broker(kind: str, init_cash: float):
    """按类型建 broker:paper 本地 / alpaca 真券商(纸面端点)。| Build broker by kind."""
    if kind == "alpaca":
        from quantmill.execution.broker import AlpacaBroker
        print("[券商] Alpaca(纸面端点)")
        return AlpacaBroker(paper=True)
    from quantmill.execution.broker import PaperBroker
    return PaperBroker(init_cash=init_cash)


def paper_run(market: str = "us", symbols=None, method: str = "topk",
              k: int | None = None, horizon: int = config.HORIZON,
              init_cash: float = 100_000.0, commission: float = config.COMMISSION,
              broker_kind: str = "paper"):
    """跑一步纸面交易:再平衡到最新信号的目标组合。| Advance the paper account one step."""
    from quantmill.portfolio.optimizer import ALLOCATORS
    from quantmill.portfolio.rules import market_rules
    if symbols is None:
        from quantmill.watchlist import load_watchlist
        symbols = load_watchlist().get(market, [])
    if len(symbols) < 1:
        raise ValueError(f"{market} 无可用股票 | no symbols for {market}")

    print("=" * 60)
    print(f"纸面交易 · {market.upper()} · 抓最新价+信号({len(symbols)} 只,较慢)")
    print("=" * 60)
    prices, sigs, rets = {}, {}, {}
    asof = None
    for sym in symbols:
        try:
            p, s, r, d = _snapshot(sym, market, horizon)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {market}:{sym} 跳过:{type(e).__name__}")
            continue
        prices[sym], sigs[sym], rets[sym] = p, s, r
        asof = str(d) if asof is None else max(asof, str(d))
        print(f"  ✓ {market}:{sym}  价 {p:.2f}  P(涨) {s:.2f}")
    if not prices:
        raise RuntimeError("没抓到任何行情 | no market data")

    rules = market_rules(market)
    lot = 100 if market == "cn" else 1               # A股100股整手 | A-share 100-share lots
    n = len(sigs)
    k = k or max(1, round(n / 2))
    ret_window = pd.DataFrame(rets).dropna().tail(60)
    target = ALLOCATORS[method](pd.Series(sigs), ret_window, k, 0.4)
    target = {s: float(w) for s, w in target.items() if w > 1e-9}

    broker = _make_broker(broker_kind, init_cash)
    orders = broker.rebalance_to(target, prices, commission=commission,
                                 sell_cost=rules["sell_cost"], lot=lot, when=asof)
    broker.record(prices, when=asof)             # 真券商为 no-op | no-op for real broker
    broker.save()

    equity = broker.value(prices)
    init = getattr(broker, "init_cash", None)
    print("\n" + "-" * 48)
    print(f"账户日期 {asof} · 配置 {method}(持仓 top-{k})· 券商 {broker_kind}")
    cum = f" · 累计收益 {(equity / init - 1) * 100:+.1f}%" if init else ""
    print(f"总权益 {equity:,.0f} · 现金 {broker.cash:,.0f}{cum}")
    if orders:
        print("\n今日订单(正买负卖):")
        for s, q in orders.items():
            print(f"  {'买' if q > 0 else '卖'} {s} {abs(q):.0f} 股 @ {prices[s]:.2f}")
    print("\n当前持仓:")
    for s, q in broker.positions().items():
        print(f"  {s}  {q:.0f} 股  市值 {q * prices[s]:,.0f}  "
              f"({q * prices[s] / equity * 100:.0f}%)")
    print("\n📄 账户已存:" + os.path.relpath(broker.path))
    print("⚠️ 本地纸面(对真实最新价模拟成交),非真券商;定期 run 才是持续纸面交易。")
    return broker


def paper_status():
    """看纸面账户当前状态(不重新抓价,用最近一次快照)。| Show paper account status."""
    broker = PaperBroker()
    if not os.path.exists(broker.path):
        print("还没有纸面账户。先跑:quantmill paper run us")
        return
    print("=" * 56)
    print("纸面账户状态 | Paper account")
    print("=" * 56)
    print(f"初始资金 {broker.init_cash:,.0f} · 现金 {broker.cash:,.0f}")
    if broker.history:
        last = broker.history[-1]
        print(f"最近权益 {last['equity']:,.0f}(截止 {last['time']})· "
              f"累计 {(last['equity'] / broker.init_cash - 1) * 100:+.1f}%")
    print(f"持仓 {len(broker.pos)} 只 · 累计成交 {len(broker.trades)} 笔")
    for s, q in broker.pos.items():
        print(f"  {s}  {q:.0f} 股")
    if broker.trades:
        print("\n最近 5 笔成交:")
        for t in broker.trades[-5:]:
            print(f"  [{t['time']}] {'买' if t['qty'] > 0 else '卖'} {t['symbol']} "
                  f"{abs(t['qty']):.0f} @ {t['price']}")


def paper_reset(init_cash: float = 100_000.0):
    """重置纸面账户为初始资金、空仓。| Reset the paper account."""
    broker = PaperBroker(init_cash=init_cash)
    broker.cash, broker.init_cash = init_cash, init_cash
    broker.pos, broker.history, broker.trades = {}, [], []
    broker.save()
    print(f"纸面账户已重置:初始资金 {init_cash:,.0f}、空仓。")
