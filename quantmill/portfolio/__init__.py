"""
portfolio —— 组合层 | Portfolio layer
======================================
把"每只票的信号"变成"一个组合的仓位 + 一条组合资金曲线"——从"选股"到"策略"的分水岭。
Turns per-stock signals into portfolio weights + one portfolio equity curve.

  optimizer  配置器:等权 / TopK / 逆波动 | allocators
  backtest   组合级回测引擎 | portfolio-level backtest
  report     组合报告(策略 vs 等权基准)| portfolio report

⚠️ 单市场、单币种(混美/港/A 需处理日历+汇率,后话)。
"""

from __future__ import annotations

import pandas as pd

from quantmill import config
from quantmill.credibility.validate import compute_proba
from quantmill.portfolio.backtest import backtest_portfolio, portfolio_metrics
from quantmill.portfolio.optimizer import ALLOCATORS
from quantmill.portfolio.report import generate_portfolio_report
from quantmill.portfolio.rules import market_rules

__all__ = [
    "build_panels", "run_portfolio", "backtest_portfolio",
    "portfolio_metrics", "ALLOCATORS", "generate_portfolio_report",
]


def build_panels(symbols, market, start=config.START, end=None,
                 horizon=config.HORIZON):
    """
    把一组同市场股票的样本外信号与每日收益拼成两张对齐面板。
    Build aligned (dates × symbols) signal and return panels for one market's names.
    返回:(signal_panel, return_panel),只保留所有票都有信号的公共区间。
    """
    sig, ret = {}, {}
    for sym in symbols:
        try:
            feat_df, proba = compute_proba(sym, market, start, end, horizon)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {market}:{sym} 跳过:{type(e).__name__} {e}")
            continue
        sig[sym] = proba
        ret[sym] = feat_df["Close"].pct_change()
        print(f"  ✓ {market}:{sym}  {len(proba.dropna())} 个信号")

    if len(sig) < 2:
        raise ValueError("有效股票不足 2 只,无法组合 | need >=2 valid symbols")

    sig_panel = pd.DataFrame(sig)
    ret_panel = pd.DataFrame(ret)
    # 公共区间:所有票都有样本外信号的日期 | dates where every name has an OOS signal
    common = sig_panel.dropna(how="any").index
    sig_panel = sig_panel.loc[common]
    ret_panel = ret_panel.reindex(common).fillna(0.0)  # 缺失收益(停牌/假日)记 0
    return sig_panel, ret_panel


def run_portfolio(market, symbols=None, method="topk", k=None,
                  start=config.START, end=None, horizon=config.HORIZON,
                  rebalance=None, commission=config.COMMISSION, max_weight=0.4,
                  vol_target=None):
    """
    跑一个单市场组合:信号组合 vs 等权基准,出报告。
    Run a single-market portfolio: signal portfolio vs equal-weight benchmark, with a report.
    """
    if symbols is None:
        from quantmill.watchlist import load_watchlist
        symbols = load_watchlist().get(market, [])
    if len(symbols) < 2:
        raise ValueError(f"{market} 市场股票不足 2 只 | need >=2 names in {market}")

    print("=" * 60)
    print(f"构建 {market.upper()} 组合面板({len(symbols)} 只,算样本外信号,较慢)")
    print("=" * 60)
    sig_panel, ret_panel = build_panels(symbols, market, start, end, horizon)

    n = ret_panel.shape[1]
    if k is None:
        k = max(1, round(n / 2))            # 默认持有一半 | default hold half
    if rebalance is None:
        rebalance = horizon                  # 默认按预测周期再平衡 | rebalance = horizon

    rules = market_rules(market)          # 涨跌停/印花税/T+1 | market trading rules
    plim, scost = rules["price_limit"], rules["sell_cost"]
    if plim:
        print(f"[制度] {market.upper()} 涨跌停 ±{plim:.0%}、卖出印花税 {scost:.2%}、"
              f"T+{rules['t_plus']}(rebalance={rebalance}天,天然满足)")
    vt = f"、波动率目标 {vol_target:.0%}" if vol_target else ""
    print(f"[配置] {method}{vt}")

    strat = backtest_portfolio(sig_panel, ret_panel, method=method, k=k,
                               rebalance=rebalance, commission=commission,
                               max_weight=max_weight, vol_target=vol_target,
                               price_limit=plim, sell_cost=scost)
    bench = backtest_portfolio(sig_panel, ret_panel, method="equal",
                               rebalance=rebalance, commission=commission,
                               price_limit=plim, sell_cost=scost)
    sm, bm = portfolio_metrics(strat), portfolio_metrics(bench)

    print("\n" + "-" * 48)
    print(f"组合({method}, 持仓 top-{k}, 每 {rebalance} 天再平衡)vs 等权基准:")
    print("-" * 48)
    print(f"{'指标':<12}{'信号组合':>12}{'等权基准':>12}")
    for label, key in [("总收益%", "total_return"), ("年化%", "ann_return"),
                       ("夏普", "sharpe"), ("最大回撤%", "max_drawdown"),
                       ("年化波动%", "ann_vol")]:
        print(f"{label:<12}{sm[key]:>12}{bm[key]:>12}")
    beat = sm["total_return"] > bm["total_return"] and sm["sharpe"] > bm["sharpe"]
    smaller_dd = sm["max_drawdown"] > bm["max_drawdown"]   # 负数,更大=更浅
    if beat:
        concl = "✅ 收益+夏普都赢过等权基准——信号选股确实加了分"
    elif smaller_dd:
        concl = "🟡 收益/夏普没赢,但回撤更小——信号价值在避险/降波,而非多赚"
    else:
        concl = "🔴 没赢过「无脑等权持有整个池」——信号选股在组合层面没加分(诚实结果)"
    print("\n结论:", concl)

    meta = {"market": market, "n_symbols": n, "method": method, "k": k,
            "rebalance": rebalance,
            "period": f"{ret_panel.index[0].date()} ~ {ret_panel.index[-1].date()}"}
    path = generate_portfolio_report(strat, bench, sm, bm, meta)
    print(f"\n📄 组合报告已生成:{path}")
    return sm, bm
