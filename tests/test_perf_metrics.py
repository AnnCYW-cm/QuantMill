# -*- coding: utf-8 -*-
"""标准绩效指标 + IC 衰减测试(离线,合成数据)。"""
import numpy as np
import pandas as pd
import pytest

from quantmill.evaluation.metrics import (calmar, information_ratio, sortino,
                                          turnover_from_sets,
                                          turnover_from_weights)


def test_sortino_ignores_upside_vol():
    """全正收益 → 无下行波动 → Sortino=nan;有下行时为正。"""
    assert np.isnan(sortino(pd.Series([0.01] * 50), 252))
    assert sortino(pd.Series([0.02, -0.01] * 50), 252) > 0


def test_sortino_higher_than_sharpe_when_downside_small():
    from quantmill.evaluation.metrics import _ann_return
    rng = np.random.RandomState(0)
    r = pd.Series(np.where(rng.rand(500) < 0.5, 0.02, -0.005))   # 上行大、下行小
    sharpe = _ann_return(r, 252) / (r.std(ddof=1) * np.sqrt(252))
    assert sortino(r, 252) > sharpe                               # 只罚下行 → 高于夏普


def test_calmar_finite():
    r = pd.Series([0.01, -0.05, 0.02, 0.03, -0.02, 0.04] * 20)
    assert np.isfinite(calmar(r, 252))


def test_information_ratio_positive_when_beating_bench():
    r = pd.Series([0.01, -0.01, 0.02] * 30)
    assert information_ratio(r + 0.005, r, 252) > 0              # 稳定跑赢 → IR>0


def test_turnover_from_sets():
    assert turnover_from_sets([["A", "B", "C"], ["A", "B", "C"]]) == 0.0
    assert abs(turnover_from_sets([["A", "B", "C"], ["A", "B", "D"]]) - 1 / 3) < 1e-9
    assert turnover_from_sets([["A", "B"], ["C", "D"]]) == 1.0


def test_turnover_from_weights():
    idx = pd.date_range("2023-01-02", periods=4, freq="B")
    w = pd.DataFrame([[0.5, 0.5, 0], [0.5, 0.5, 0], [0, 0.5, 0.5], [0, 0.5, 0.5]],
                     index=idx, columns=["A", "B", "C"])
    assert abs(turnover_from_weights(w) - 0.5) < 1e-9            # 第3天换半仓


# ---- IC 衰减 ----
def _decay_panel(n_days=120, n_syms=30, decay=0.7):
    """信号短期强、随 horizon 衰减的面板:次日收益 ≈ 今日因子。"""
    rng = np.random.RandomState(1)
    dates = pd.date_range("2023-01-02", periods=n_days, freq="B")
    frames = []
    for s in range(n_syms):
        fac = rng.randn(n_days)
        rets = np.zeros(n_days)
        rets[1:] = decay * fac[:-1] * 0.01 + 0.003 * rng.randn(n_days - 1)
        close = 100 * np.cumprod(1 + rets)
        frames.append(pd.DataFrame({"date": dates, "symbol": f"S{s}",
                                    "mom": fac, "close": close}))
    return pd.concat(frames).set_index(["date", "symbol"]).sort_index()


def test_ic_decay_decreases_with_horizon():
    from quantmill.cross.ic import ic_decay
    d = ic_decay(_decay_panel(), "mom", horizons=(1, 5, 20))
    assert list(d["horizon"]) == [1, 5, 20]
    ic1 = abs(d.loc[d["horizon"] == 1, "IC"].iloc[0])
    ic20 = abs(d.loc[d["horizon"] == 20, "IC"].iloc[0])
    assert ic1 > ic20                                            # 短期强、长期衰减
    assert {"IC", "ICIR", "pos%", "days"} <= set(d.columns)


def test_ic_decay_requires_close():
    from quantmill.cross.ic import ic_decay
    with pytest.raises(ValueError):
        ic_decay(_decay_panel().drop(columns=["close"]), "mom")
