# -*- coding: utf-8 -*-
"""
test_risk.py —— 风控/仓位层(离线,内置样本)
test_risk.py —— risk overlay (offline, bundled sample)
"""

import pandas as pd

from quantmill.cross import composite_score, load_sample_panel
from quantmill.risk import inverse_vol_weights, risk_managed_backtest


def test_inverse_vol_weights_capped_and_normalized():
    vols = pd.Series({"a": 0.10, "b": 0.20, "c": 0.40, "d": 0.80})
    w = inverse_vol_weights(vols, max_weight=0.4)
    assert abs(w.sum() - 1.0) < 1e-9          # 归一
    assert (w <= 0.4 + 1e-9).all()            # 封顶
    assert w["a"] > w["d"]                    # 低波拿更多权重


def test_inverse_vol_all_missing_falls_back_equal():
    vols = pd.Series({"a": float("nan"), "b": float("nan")})
    w = inverse_vol_weights(vols)
    assert abs(w["a"] - 0.5) < 1e-9 and abs(w["b"] - 0.5) < 1e-9


def test_risk_managed_reduces_drawdown_and_bounds_exposure():
    panel = load_sample_panel()
    score = composite_score(panel)
    res = risk_managed_backtest(panel, score, k=6, horizon=20, cost=0.0015,
                                target_vol=0.15, max_weight=0.3, dd_limit=0.1, max_leverage=1.0)
    assert res["periods"] > 0
    assert 0 <= res["avg_exposure"] <= 1.0     # 不加杠杆:敞口在 [0,1]
    raw = res["metrics"]["等权满仓"]
    mgd = res["metrics"]["风控后"]
    assert {"最大回撤%", "年化波动%", "夏普"} <= set(mgd)
    # 风控通常压低波动(敞口≤1 + 逆波动加权)
    assert mgd["年化波动%"] <= raw["年化波动%"] + 1e-6
    # 最大回撤不应更差(数值上更接近0或相等)
    assert mgd["最大回撤%"] >= raw["最大回撤%"] - 1e-6
