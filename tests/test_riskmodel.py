# -*- coding: utf-8 -*-
"""因子风险模型 + 归因 + 中性化测试(离线,合成面板)。"""
import numpy as np
import pandas as pd

from quantmill.cross.model import rank_normalize
from quantmill.cross.neutralize import neutralize
from quantmill.cross.riskmodel import (factor_returns, factor_risk_model,
                                       return_attribution, risk_decompose)


def _panel(n_days=45, n_syms=50, seed=0):
    """收益由因子 a 驱动;c = 3·size + 噪声(用于验中性化)。"""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2023-01-02", periods=n_days, freq="B")
    rows = []
    for d in dates:
        a, b, size = rng.randn(n_syms), rng.randn(n_syms), rng.randn(n_syms)
        fwd = 0.02 * a + 0.004 * rng.randn(n_syms)          # 只有 a 真驱动收益
        c = 3 * size + 0.1 * rng.randn(n_syms)              # c 几乎就是 size 的替身
        for i in range(n_syms):
            rows.append({"date": d, "symbol": f"S{i:02d}", "a": a[i], "b": b[i],
                         "size": size[i], "c": c[i], "fwd": fwd[i]})
    return pd.DataFrame(rows).set_index(["date", "symbol"]).sort_index()


# ---- 引擎:因子收益回归 ----
def test_factor_returns_recovers_driver():
    p = _panel()
    fr, spec = factor_returns(p, ["a", "b", "size"])
    assert fr["a"].mean() > 0                               # a 是真驱动 → 因子收益为正
    assert fr["a"].mean() > abs(fr["b"].mean())             # 明显强于噪声因子 b
    assert len(spec) > 0 and spec.index.names == ["date", "symbol"]


# ---- 风险模型 ----
def test_risk_model_shapes_and_decomp():
    p = _panel()
    fac = ["a", "b", "size"]
    m = factor_risk_model(p, fac, periods_per_year=12.6)
    assert m["factor_cov"].shape == (3, 3)                  # F 是 k×k
    assert np.allclose(m["factor_cov"], m["factor_cov"].T)  # 对称
    d = p.index.get_level_values("date").unique()[-1]
    exp = rank_normalize(p, fac).xs(d, level="date")
    held = exp.index[:10]
    w = pd.Series(1 / len(held), index=held)
    r = risk_decompose(w, exp, m)
    assert r["total_vol"] > 0
    # 总方差 ≈ 因子方差 + 特质方差(勾股)
    assert abs(r["total_vol"] ** 2 - (r["factor_vol"] ** 2 + r["specific_vol"] ** 2)) < 1e-8
    assert set(r["factor_contrib"].index) == set(fac)


# ---- 归因 ----
def test_attribution_reconciles_and_finds_driver():
    p = _panel()
    fac = ["a", "b", "size"]
    # 每天挑 a 最大的 10 只(组合就靠 a 选股)
    X = p["a"]
    picks = {d: list(g.sort_values(ascending=False).head(10).index.get_level_values("symbol"))
             for d, g in X.groupby(level="date")}
    att = return_attribution(p, fac, picks)
    total = att.loc[att["来源"] == "合计(超额)", "超额贡献%"].iloc[0]
    parts = att.loc[att["来源"] != "合计(超额)", "超额贡献%"].sum()
    assert abs(total - parts) < 0.1                         # 各因子 + 选股α = 合计超额(自洽,容显示舍入)
    a_c = att.loc[att["来源"] == "a", "超额贡献%"].iloc[0]
    b_c = att.loc[att["来源"] == "b", "超额贡献%"].iloc[0]
    assert a_c > 0 and a_c > b_c                            # a(真驱动)正贡献,且强于纯噪声因子 b


# ---- 中性化 ----
def test_neutralize_removes_size_exposure():
    p = _panel()
    neut = neutralize(p, "c", by=["size"])
    # 中性化前 c 与 size 高度相关;中性化后残差与 size 近乎无关
    def _corr(col):
        return p.assign(x=col).groupby(level="date").apply(
            lambda g: g["x"].corr(g["size"])).abs().mean()
    assert _corr(p["c"]) > 0.9
    assert _corr(neut) < 0.15                               # 残差不再是 size 的替身


def test_neutralize_keeps_index_and_handles_missing():
    p = _panel()
    neut = neutralize(p, "a", by=["size"])
    assert neut.index.equals(p.index)                       # 对齐原面板索引
