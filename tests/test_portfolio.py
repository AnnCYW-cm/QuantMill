# -*- coding: utf-8 -*-
"""
test_portfolio.py —— 组合配置器 / 回测 / 风险模型 / A股制度 的正确性
test_portfolio.py —— Allocators / backtest / risk model / A-share rules correctness
===================================================================================
"""

import numpy as np
import pandas as pd

from quantmill.portfolio.optimizer import (
    equal_weight_all, top_k_equal, inverse_vol, min_variance,
)
from quantmill.portfolio.backtest import backtest_portfolio, portfolio_metrics
from quantmill.portfolio.risk import shrinkage_cov, min_variance_weights, portfolio_vol
from quantmill.portfolio.rules import market_rules


def _ret_window(vols, n=60, seed=0):
    """造一段各列不同波动率的收益窗口。| Returns window with per-column vols."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({c: rng.normal(0, v, n) for c, v in vols.items()})


# ---------------------------------------------------------------- 配置器 | allocators
def test_equal_weight_all():
    sig = pd.Series({"A": 0.7, "B": 0.6, "C": np.nan})
    w = equal_weight_all(sig)
    assert w["C"] == 0.0 and abs(w["A"] - 0.5) < 1e-9 and abs(w.sum() - 1) < 1e-9


def test_top_k_equal():
    sig = pd.Series({"A": 0.7, "B": 0.6, "C": 0.4, "D": 0.3})
    w = top_k_equal(sig, k=2)
    assert set(w[w > 0].index) == {"A", "B"}
    assert abs(w["A"] - 0.5) < 1e-9 and abs(w.sum() - 1) < 1e-9 and (w >= 0).all()


def test_inverse_vol_favors_low_vol():
    """top-k 内低波动多配。| Within top-k, lower vol -> higher weight."""
    sig = pd.Series({"A": 0.7, "B": 0.6, "C": 0.4})
    rw = _ret_window({"A": 0.005, "B": 0.03, "C": 0.01})   # A 波动最低
    w = inverse_vol(sig, rw, k=2)
    assert w["C"] == 0.0                       # 不在 top-2
    assert w["A"] > w["B"] and abs(w.sum() - 1) < 1e-9


def test_max_weight_cap():
    sig = pd.Series({"A": 0.7, "B": 0.6})
    rw = _ret_window({"A": 0.001, "B": 0.05})  # A 会被逆波动配到很高
    w = inverse_vol(sig, rw, k=2, max_weight=0.5)
    assert w["A"] <= 0.5 + 1e-9 and abs(w.sum() - 1) < 1e-6


def test_inverse_vol_short_window_falls_back_equal():
    """窗口不足退化等权。| Too-short window -> equal weight."""
    sig = pd.Series({"A": 0.7, "B": 0.6})
    w = inverse_vol(sig, ret_window=None, k=2)
    assert abs(w["A"] - 0.5) < 1e-9 and abs(w["B"] - 0.5) < 1e-9


# ---------------------------------------------------------------- 风险模型 | risk model
def test_shrinkage_cov_shape_symmetric():
    rw = _ret_window({"A": 0.01, "B": 0.02, "C": 0.015})
    cov = shrinkage_cov(rw)
    assert cov.shape == (3, 3) and list(cov.columns) == ["A", "B", "C"]
    assert np.allclose(cov.to_numpy(), cov.to_numpy().T)


def test_min_variance_weights_favor_low_variance():
    """最小方差:低方差资产权重更高;和=1;长仓。| Min-var: low-variance asset gets more."""
    cov = pd.DataFrame([[0.0001, 0.0], [0.0, 0.01]],
                       index=["A", "B"], columns=["A", "B"])
    w = min_variance_weights(cov)
    assert w["A"] > w["B"] and abs(w.sum() - 1) < 1e-6 and (w >= -1e-9).all()


def test_min_variance_allocator():
    """minvar 配置器:top-k 内最小方差,低波动多配。| minvar allocator picks top-k, min-var."""
    sig = pd.Series({"A": 0.7, "B": 0.6, "C": 0.4})
    rw = _ret_window({"A": 0.005, "B": 0.03, "C": 0.02}, seed=1)
    w = min_variance(sig, rw, k=2)
    assert w["C"] == 0.0 and abs(w.sum() - 1) < 1e-6 and w["A"] > w["B"]


def test_portfolio_vol_positive():
    cov = pd.DataFrame([[0.0004, 0.0001], [0.0001, 0.0009]],
                       index=["A", "B"], columns=["A", "B"])
    pv = portfolio_vol(pd.Series({"A": 0.5, "B": 0.5}), cov)
    assert pv > 0


# ---------------------------------------------------------------- 组合回测 | backtest
def _panels(n=6):
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    ret = pd.DataFrame({"A": [0.0, 0.10, -0.05, 0.0, 0.02, 0.03][:n],
                        "B": [0.0, 0.00, 0.10, 0.0, -0.02, 0.01][:n]}, index=dates)
    sig = pd.DataFrame(0.6, index=dates, columns=["A", "B"])
    return sig, ret


def test_backtest_equal_weight_matches_manual():
    sig, ret = _panels()
    res = backtest_portfolio(sig, ret, method="equal", rebalance=1, commission=0.0)
    exp = 0.5 * (ret["A"] + ret["B"])
    assert abs(res["returns"].iloc[0]) < 1e-12
    for t in range(1, len(ret)):
        assert abs(res["returns"].iloc[t] - exp.iloc[t]) < 1e-12


def test_backtest_no_lookahead():
    """★ 改变未来收益不影响过去组合收益。| Changing future returns can't change the past."""
    sig, ret = _panels()
    r1 = backtest_portfolio(sig, ret, method="topk", k=1, rebalance=1, commission=0.001)
    ret2 = ret.copy(); ret2.iloc[-1] = [9.9, -9.9]
    r2 = backtest_portfolio(sig, ret2, method="topk", k=1, rebalance=1, commission=0.001)
    assert np.allclose(r1["returns"].iloc[:-1].to_numpy(),
                       r2["returns"].iloc[:-1].to_numpy(), equal_nan=True)


def test_vol_target_reduces_exposure():
    """★ 高波动 + 低波动率目标 -> 整体降仓(持币,gross<1)。| vol targeting scales down exposure."""
    dates = pd.date_range("2020-01-01", periods=60, freq="D")
    rng = np.random.default_rng(3)
    ret = pd.DataFrame(rng.normal(0, 0.05, (60, 2)), columns=["A", "B"], index=dates)  # 高波动
    sig = pd.DataFrame(0.6, index=dates, columns=["A", "B"])
    base = backtest_portfolio(sig, ret, method="equal", rebalance=5)
    vt = backtest_portfolio(sig, ret, method="equal", rebalance=5, vol_target=0.15)
    g_base = base["weights"].sum(axis=1).iloc[25:].mean()
    g_vt = vt["weights"].sum(axis=1).iloc[25:].mean()
    assert g_vt < g_base and g_vt < 1.0        # 降仓且持币 | scaled down, holds cash


def test_price_limit_freezes_locked_name():
    """★ 涨跌停锁死的票当日不可买入。| A limit-locked name can't be bought that day."""
    dates = pd.date_range("2020-01-01", periods=12, freq="D")
    ret = pd.DataFrame(0.0, index=dates, columns=["A", "B"])
    ret.loc[dates[5], "B"] = 0.10              # 第5天 B 涨停(+10%)
    # 信号:前5天选A,第5天起选B(想在第5天买入 B)
    sig = pd.DataFrame({"A": [0.6] * 12, "B": [0.5] * 5 + [0.9] * 7}, index=dates)
    no_pl = backtest_portfolio(sig, ret, method="topk", k=1, rebalance=5, commission=0.0)
    pl = backtest_portfolio(sig, ret, method="topk", k=1, rebalance=5, commission=0.0,
                            price_limit=0.10)
    assert no_pl["weights"].loc[dates[5], "B"] == 1.0   # 无制度:买到 B
    assert pl["weights"].loc[dates[5], "B"] == 0.0      # 有制度:涨停买不进


# ---------------------------------------------------------------- 市场制度 | market rules
def test_market_rules():
    """A股有涨跌停+印花税+T+1;美股无。| cn has price limit + stamp; us none."""
    cn, us = market_rules("cn"), market_rules("us")
    assert cn["price_limit"] == 0.10 and cn["sell_cost"] > 0 and cn["t_plus"] == 1
    assert us["price_limit"] is None and us["sell_cost"] == 0.0


def test_metrics_basic():
    sig, ret = _panels()
    m = portfolio_metrics(backtest_portfolio(sig, ret, method="equal", rebalance=1,
                                             commission=0.0))
    assert {"total_return", "sharpe", "max_drawdown", "ann_vol"}.issubset(m)
